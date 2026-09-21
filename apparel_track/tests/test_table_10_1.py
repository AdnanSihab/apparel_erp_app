# Copyright (c) 2026, Adnan and contributors
# For license information, please see license.txt

"""Test cases T1 - T10 from Table 10.1 of the report, plus the follow-on checks.

Every test builds real documents on the site, asserts the expected result from the
table, and is rolled back afterwards, so the suite can be run as often as needed:

	bench --site apparel-site run-tests --module apparel_track.tests.test_table_10_1
"""

import frappe
from frappe.utils import add_days, getdate, nowdate

from apparel_track.apparel_track.barcode import scan_barcode
from apparel_track.apparel_track.reorder_engine import _process_item_reorder, get_average_daily_usage
from apparel_track.apparel_track.tasks import get_apparel_dashboard_data
from apparel_track.tests.fixtures import (
	ApparelTestCase,
	make_batch,
	make_item,
	make_item_group,
	make_purchase_order,
	make_season,
	make_stock_entry,
	make_storage_bin,
	make_supplier,
	open_auto_requests,
	receive_purchase_order,
	set_reorder_rule,
	stock_qty,
	warehouse,
)

COLOURS = ["Black", "Blue", "Green", "Red", "White"]
SIZES = ["Extra Small", "Small", "Medium", "Large", "Extra Large"]


class TestTable10_1(ApparelTestCase):
	def setUp(self):
		super().setUp()
		self.stores = warehouse("Stores")
		self.wip = warehouse("Work In Progress")
		# a fresh item group per test, so no supplier scorecard feeds a lead time in unasked
		self.group = make_item_group(f"_AT Fabric {self.suffix}")

	def fabric(self, name="Jersey", **kwargs):
		return make_item(f"_AT-{name}-{self.suffix}", item_group=self.group, **kwargs)

	# T1 ---------------------------------------------------------------------
	def test_t01_item_template_generates_variant_matrix(self):
		"""T1  Colour and size attributes generate the full variant matrix."""
		from erpnext.controllers.item_variant import create_multiple_variants

		template = make_item(
			f"_AT-TEE-{self.suffix}",
			item_group="Products",
			stock_uom="Nos",
			has_variants=1,
			variant_based_on="Item Attribute",
			attributes=[{"attribute": "Colour"}, {"attribute": "Size"}],
		)

		created = create_multiple_variants(template.name, {"Colour": COLOURS, "Size": SIZES})

		variants = frappe.get_all("Item", filters={"variant_of": template.name}, pluck="name")
		self.assertEqual(created, 25)
		self.assertEqual(len(variants), 25)
		combinations = {
			tuple(
				frappe.get_all(
					"Item Variant Attribute",
					filters={"parent": variant},
					order_by="idx",
					pluck="attribute_value",
				)
			)
			for variant in variants
		}
		self.assertEqual(combinations, {(colour, size) for colour in COLOURS for size in SIZES})

	# T2 ---------------------------------------------------------------------
	def test_t02_season_and_shrinkage_on_item(self):
		"""T2  Season and shrinkage percentage save and sit in the expected position."""
		season = make_season(f"_AT Summer {self.suffix}")
		item = self.fabric(custom_season=season, custom_shrinkage_percentage=3.5)

		item.reload()
		self.assertEqual(item.custom_season, season)
		self.assertEqual(item.custom_shrinkage_percentage, 3.5)
		# Season is named by its own name, so the Item shows "Summer ..." not a random ID
		self.assertEqual(frappe.db.get_value("Season", season, "season_name"), season)
		# season sits next to the stock unit of measure on the Item form
		self.assertEqual(
			frappe.db.get_value("Custom Field", {"dt": "Item", "fieldname": "custom_season"}, "insert_after"),
			"stock_uom",
		)

	# T3 ---------------------------------------------------------------------
	def test_t03_fabric_roll_received_with_dye_lot(self):
		"""T3  Receiving a roll creates the batch with its dye lot and roll length."""
		item = self.fabric(has_batch_no=1)
		batch = make_batch(item.name, f"_AT-LOT-{self.suffix}", dye_lot="DL-5130", roll_length=85)

		make_stock_entry("Material Receipt", item.name, 85, target=self.stores, batch_no=batch.name)

		batch.reload()
		self.assertEqual(batch.custom_dye_lot_number, "DL-5130")
		self.assertEqual(batch.custom_roll_length_meters, 85)
		self.assertEqual(stock_qty(item.name, self.stores), 85)

	def test_t03b_receipt_fills_missing_dye_lot_and_roll_length(self):
		"""T3  A batch booked in without lot details gets them from the receipt."""
		item = self.fabric(has_batch_no=1)
		batch = make_batch(item.name, f"_AT-LOT-{self.suffix}")

		make_stock_entry("Material Receipt", item.name, 64, target=self.stores, batch_no=batch.name)

		batch.reload()
		self.assertEqual(batch.custom_dye_lot_number, batch.name)
		self.assertEqual(batch.custom_roll_length_meters, 64)

	# T4 ---------------------------------------------------------------------
	def test_t04_storage_bin_with_barcode(self):
		"""T4  A bin links to its warehouse and item, and its code scans to the warehouse."""
		item = self.fabric()
		code = f"RACK-{self.suffix}"
		bin_doc = make_storage_bin(f"_AT-B{self.suffix}", self.stores, item.name, barcode=code)

		self.assertEqual(bin_doc.name, bin_doc.bin_id)
		self.assertEqual(bin_doc.warehouse, self.stores)
		self.assertEqual(bin_doc.current_item, item.name)
		self.assertEqual(scan_barcode(code), {"warehouse": self.stores})
		self.assertEqual(scan_barcode(f"NO-SUCH-CODE-{self.suffix}"), {})

	def test_t04b_receipt_assigns_a_storage_bin(self):
		"""T4  Stock booked into a warehouse is given a bin automatically, with a scannable code."""
		item = self.fabric()

		make_stock_entry("Material Receipt", item.name, 40, target=self.stores)

		bin_name = frappe.db.get_value("Storage Bin", {"warehouse": self.stores, "current_item": item.name})
		self.assertTrue(bin_name)
		self.assertTrue(frappe.db.get_value("Storage Bin", bin_name, "barcode_qr_code"))

	# T5 ---------------------------------------------------------------------
	def test_t05_transfer_stores_to_work_in_progress(self):
		"""T5  Quantities move between warehouses correctly."""
		item = self.fabric()
		make_stock_entry("Material Receipt", item.name, 150, target=self.stores)

		make_stock_entry("Material Transfer", item.name, 60, source=self.stores, target=self.wip)

		self.assertEqual(stock_qty(item.name, self.stores), 90)
		self.assertEqual(stock_qty(item.name, self.wip), 60)

	# T6 ---------------------------------------------------------------------
	def test_t06_issue_with_cutting_wastage(self):
		"""T6  Issuing material deducts stock at once and records the wastage."""
		item = self.fabric()
		make_stock_entry("Material Receipt", item.name, 150, target=self.stores)
		make_stock_entry("Material Transfer", item.name, 60, source=self.stores, target=self.wip)

		issue = make_stock_entry(
			"Material Issue", item.name, 24, source=self.wip, custom_wastage_scrap_qty=1.25
		)

		self.assertEqual(stock_qty(item.name, self.wip), 36)
		self.assertEqual(frappe.db.get_value("Stock Entry", issue.name, "custom_wastage_scrap_qty"), 1.25)
		# the issue is what the reorder engine reads as consumption
		self.assertAlmostEqual(get_average_daily_usage(item.name), 24 / 30)

	# T7 ---------------------------------------------------------------------
	def test_t07_reorder_job_above_level_creates_nothing(self):
		"""T7  Stock above the reorder level: no Material Request."""
		item = self.fabric()
		make_stock_entry("Material Receipt", item.name, 40, target=self.stores)
		set_reorder_rule(item.name, self.stores, reorder_qty=120, safety_stock=15)

		_process_item_reorder(item.name)

		self.assertEqual(frappe.get_doc("Item", item.name).reorder_levels[0].warehouse_reorder_level, 15)
		self.assertEqual(open_auto_requests(item.name, self.stores), [])

	# T8 ---------------------------------------------------------------------
	def test_t08_reorder_job_below_level_raises_request(self):
		"""T8  Stock below the reorder level: a submitted request for the reorder quantity."""
		item = self.fabric()
		make_stock_entry("Material Receipt", item.name, 6, target=self.stores)
		set_reorder_rule(item.name, self.stores, reorder_qty=120, safety_stock=15)

		_process_item_reorder(item.name)

		requests = open_auto_requests(item.name, self.stores)
		self.assertEqual(len(requests), 1)
		mr = frappe.get_doc("Material Request", requests[0])
		self.assertEqual(mr.docstatus, 1)
		self.assertEqual(mr.material_request_type, "Purchase")
		self.assertEqual(mr.custom_generated_by, "Auto-Reorder Script")
		self.assertEqual(mr.items[0].qty, 120)
		self.assertEqual(getdate(mr.schedule_date), getdate(add_days(nowdate(), 7)))

	# T9 ---------------------------------------------------------------------
	def test_t09_second_run_does_not_duplicate(self):
		"""T9  Running the job twice against the same shortage raises one request only."""
		item = self.fabric()
		make_stock_entry("Material Receipt", item.name, 6, target=self.stores)
		set_reorder_rule(item.name, self.stores, reorder_qty=120, safety_stock=15)

		_process_item_reorder(item.name)
		_process_item_reorder(item.name)

		self.assertEqual(len(open_auto_requests(item.name, self.stores)), 1)

	def test_t09b_stopped_request_does_not_block_reordering(self):
		"""T9  Once procurement stops a request, the next run raises a fresh one."""
		from erpnext.stock.doctype.material_request.material_request import update_status

		item = self.fabric()
		make_stock_entry("Material Receipt", item.name, 6, target=self.stores)
		set_reorder_rule(item.name, self.stores, reorder_qty=120, safety_stock=15)
		_process_item_reorder(item.name)
		first = open_auto_requests(item.name, self.stores)[0]

		update_status(first, "Stopped")
		_process_item_reorder(item.name)

		requests = open_auto_requests(item.name, self.stores)
		self.assertEqual(len(requests), 1)
		self.assertNotEqual(requests[0], first)

	# T10 --------------------------------------------------------------------
	def test_t10_purchase_receipt_updates_scorecard(self):
		"""T10  A receipt against an order updates the actual lead time and reliability."""
		supplier = make_supplier(f"_AT Supplier {self.suffix}")
		item = self.fabric()
		scorecard = frappe.get_doc(
			{
				"doctype": "Supplier Scorecard",
				"supplier": supplier,
				"item_group": self.group,
				"promised_lead_time_days": 6,
			}
		).insert(ignore_permissions=True)

		po = make_purchase_order(supplier, [(item.name, 300, 180)], add_days(nowdate(), -8), self.stores)
		receive_purchase_order(po.name)

		scorecard.reload()
		self.assertEqual(scorecard.receipts_counted, 1)
		self.assertEqual(scorecard.actual_average_lead_time_days, 8)
		self.assertAlmostEqual(scorecard.reliability_score, 75)  # 6 promised / 8 actual

	def test_t10b_several_lines_count_as_one_delivery(self):
		"""T10  Three lines from the same order and item group are one delivery, not three."""
		supplier = make_supplier(f"_AT Supplier {self.suffix}")
		items = [self.fabric(name) for name in ("Rib", "Fleece", "Pique")]

		po = make_purchase_order(
			supplier, [(item.name, 50, 150) for item in items], add_days(nowdate(), -5), self.stores
		)
		receive_purchase_order(po.name)

		counted = frappe.db.get_value(
			"Supplier Scorecard", {"supplier": supplier, "item_group": self.group}, "receipts_counted"
		)
		self.assertEqual(counted, 1)

	def test_t11_slow_supplier_raises_reorder_level(self):
		"""Section 6.4  Reorder level = daily usage x measured lead time + safety stock."""
		supplier = make_supplier(f"_AT Supplier {self.suffix}")
		item = self.fabric()
		frappe.get_doc(
			{
				"doctype": "Supplier Scorecard",
				"supplier": supplier,
				"item_group": self.group,
				"promised_lead_time_days": 5,
			}
		).insert(ignore_permissions=True)
		make_stock_entry("Material Receipt", item.name, 400, target=self.stores)
		make_stock_entry("Material Issue", item.name, 90, source=self.stores)  # 3 m a day over 30 days

		po = make_purchase_order(supplier, [(item.name, 100, 150)], add_days(nowdate(), -12), self.stores)
		receive_purchase_order(po.name)  # this supplier took 12 days, not 5
		item = set_reorder_rule(item.name, self.stores, reorder_qty=200, safety_stock=20)

		row = item.reorder_levels[0]
		self.assertAlmostEqual(row.custom_daily_usage, 3)
		self.assertAlmostEqual(row.custom_dynamic_lead_time_days, 12)
		self.assertAlmostEqual(row.warehouse_reorder_level, 3 * 12 + 20)

	def test_t12_dashboard_reports_stock_value_and_dead_stock(self):
		"""Section 8.4  Stock value by warehouse and dead stock ageing."""
		idle = self.fabric("Idle")
		make_stock_entry(
			"Material Receipt", idle.name, 10, target=self.stores, rate=200, posting_date=add_days(nowdate(), -45)
		)

		data = get_apparel_dashboard_data(days=30, dead_stock_days=30)

		self.assertIn(self.stores, {row.warehouse for row in data["stock_value_by_warehouse"]})
		dead = {row.item_code: row for row in data["dead_stock_ageing"]}
		self.assertIn(idle.name, dead)
		self.assertGreaterEqual(dead[idle.name].age_days, 45)

	def test_t13_erpnext_auto_reorder_is_switched_off(self):
		"""Only one engine may raise requests from the reorder rules, or every shortage gets two."""
		from apparel_track.apparel_track.setup import disable_erpnext_auto_reorder

		frappe.db.set_single_value("Stock Settings", "auto_indent", 1)
		disable_erpnext_auto_reorder()

		self.assertEqual(frappe.db.get_single_value("Stock Settings", "auto_indent"), 0)
