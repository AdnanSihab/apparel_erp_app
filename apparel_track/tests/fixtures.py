# Copyright (c) 2026, Adnan and contributors
# For license information, please see license.txt

"""Builders shared by the Apparel Track tests and the demo data script."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase
from frappe.utils import add_days, nowdate

COMPANY = "Apparel Tracking"


class ApparelTestCase(UnitTestCase):
	"""Runs every test inside one transaction and rolls it back afterwards.

	The app's code commits (the reorder job commits after each item), so commits are
	disabled while the tests run. Nothing a test creates is left on the site.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._no_commit = patch.object(frappe.db, "commit", lambda *args, **kwargs: None)
		cls._no_commit.start()

	@classmethod
	def tearDownClass(cls):
		cls._no_commit.stop()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		self.suffix = frappe.generate_hash(length=6).upper()

	def tearDown(self):
		frappe.db.rollback()


def warehouse(name: str, company: str = COMPANY) -> str:
	"""'Stores' -> 'Stores - AT'."""
	return f"{name} - {frappe.get_cached_value('Company', company, 'abbr')}"


def make_item_group(name: str) -> str:
	if not frappe.db.exists("Item Group", name):
		frappe.get_doc(
			{"doctype": "Item Group", "item_group_name": name, "parent_item_group": "All Item Groups"}
		).insert(ignore_permissions=True)
	return name


def make_item(item_code: str, **kwargs):
	if frappe.db.exists("Item", item_code):
		return frappe.get_doc("Item", item_code)
	values = {
		"doctype": "Item",
		"item_code": item_code,
		"item_name": kwargs.pop("item_name", item_code),
		"item_group": "Raw Material",
		"stock_uom": "Meter",
		"is_stock_item": 1,
		"is_purchase_item": 1,
		"include_item_in_manufacturing": 1,
		"valuation_rate": 100,
	}
	values.update(kwargs)
	return frappe.get_doc(values).insert(ignore_permissions=True)


def make_season(season_name: str) -> str:
	if not frappe.db.exists("Season", season_name):
		frappe.get_doc({"doctype": "Season", "season_name": season_name}).insert(ignore_permissions=True)
	return season_name


def make_batch(item_code: str, batch_id: str, dye_lot: str | None = None, roll_length: float = 0):
	if frappe.db.exists("Batch", batch_id):
		return frappe.get_doc("Batch", batch_id)
	return frappe.get_doc(
		{
			"doctype": "Batch",
			"batch_id": batch_id,
			"item": item_code,
			"custom_dye_lot_number": dye_lot,
			"custom_roll_length_meters": roll_length,
		}
	).insert(ignore_permissions=True)


def make_storage_bin(bin_id: str, warehouse_name: str, item_code: str | None = None, barcode: str | None = None):
	if frappe.db.exists("Storage Bin", bin_id):
		return frappe.get_doc("Storage Bin", bin_id)
	return frappe.get_doc(
		{
			"doctype": "Storage Bin",
			"bin_id": bin_id,
			"warehouse": warehouse_name,
			"current_item": item_code,
			"max_capacity": 1000,
			"barcode_qr_code": barcode or bin_id,
		}
	).insert(ignore_permissions=True)


def make_stock_entry(
	entry_type: str,
	item_code: str,
	qty: float,
	source: str | None = None,
	target: str | None = None,
	batch_no: str | None = None,
	rate: float = 100,
	posting_date: str | None = None,
	submit: bool = True,
	**header,
):
	"""Material Receipt (target only), Material Transfer (source and target) or Material Issue (source only)."""
	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": entry_type,
			"company": COMPANY,
			"items": [
				{
					"item_code": item_code,
					"qty": qty,
					"s_warehouse": source,
					"t_warehouse": target,
					"basic_rate": rate,
					"batch_no": batch_no,
					"use_serial_batch_fields": 1 if batch_no else 0,
				}
			],
			**header,
		}
	)
	if posting_date:
		entry.set_posting_time = 1
		entry.posting_date = posting_date
	entry.insert(ignore_permissions=True)
	if submit:
		entry.submit()
	return entry


def make_supplier(supplier_name: str) -> str:
	if not frappe.db.exists("Supplier", supplier_name):
		frappe.get_doc(
			{"doctype": "Supplier", "supplier_name": supplier_name, "supplier_group": "Raw Material"}
		).insert(ignore_permissions=True)
	return supplier_name


def make_purchase_order(supplier: str, items: list[tuple[str, float, float]], order_date: str, warehouse_name: str):
	"""items: [(item_code, qty, rate), ...]."""
	po = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"supplier": supplier,
			"company": COMPANY,
			"transaction_date": order_date,
			"schedule_date": add_days(order_date, 7),
			"set_warehouse": warehouse_name,
			"items": [
				{
					"item_code": item_code,
					"qty": qty,
					"rate": rate,
					"warehouse": warehouse_name,
					"schedule_date": add_days(order_date, 7),
				}
				for item_code, qty, rate in items
			],
		}
	)
	po.insert(ignore_permissions=True)
	po.submit()
	return po


def receive_purchase_order(purchase_order: str, posting_date: str | None = None):
	"""Submit a Purchase Receipt for the whole order; this fires the scorecard hook."""
	from erpnext.buying.doctype.purchase_order.mapper import make_purchase_receipt

	pr = make_purchase_receipt(purchase_order)
	pr.set_posting_time = 1
	pr.posting_date = posting_date or nowdate()
	pr.insert(ignore_permissions=True)
	pr.submit()
	return pr


def set_reorder_rule(item_code: str, warehouse_name: str, reorder_qty: float, safety_stock: float = 0):
	"""Add an Item Reorder rule. The reorder level itself is calculated by the app on save."""
	item = frappe.get_doc("Item", item_code)
	item.set("reorder_levels", [])
	item.append(
		"reorder_levels",
		{
			"warehouse_group": warehouse("All Warehouses"),
			"warehouse": warehouse_name,
			"warehouse_reorder_qty": reorder_qty,
			"material_request_type": "Purchase",
			"custom_safety_stock_qty": safety_stock,
		},
	)
	item.save(ignore_permissions=True)
	return item


def open_auto_requests(item_code: str, warehouse_name: str) -> list[str]:
	return frappe.get_all(
		"Material Request",
		filters={
			"custom_auto_generated": 1,
			"docstatus": 1,
			"status": ["not in", ["Stopped", "Cancelled", "Ordered", "Received"]],
			"name": ["in", frappe.get_all(
				"Material Request Item",
				filters={"item_code": item_code, "warehouse": warehouse_name},
				pluck="parent",
			) or [""]],
		},
		pluck="name",
	)


def stock_qty(item_code: str, warehouse_name: str) -> float:
	return frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse_name}, "actual_qty") or 0
