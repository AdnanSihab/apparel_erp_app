# Copyright (c) 2026, Adnan and contributors
# For license information, please see license.txt

"""Build a month of realistic knit-fabric history on the site, ready for a live walkthrough.

Everything is created in dependency order and back-dated across the last ten weeks, so
the reorder engine, the scorecard and the dashboards all have real history to read.
The fabric is left just above its reorder level: one transfer during the presentation
pushes it under, and the reorder job can then be run live.

	bench --site apparel-site execute apparel_track.tests.seed_demo_data.seed
	bench --site apparel-site execute apparel_track.tests.seed_demo_data.seed --kwargs "{'reset': True}"
	bench --site apparel-site execute apparel_track.tests.seed_demo_data.reset
"""

import frappe
from frappe.utils import add_days, flt, nowdate

from apparel_track.tests.fixtures import (
	COMPANY,
	make_batch,
	make_item,
	make_item_group,
	make_purchase_order,
	make_season,
	make_stock_entry,
	make_storage_bin,
	make_supplier,
	set_reorder_rule,
	stock_qty,
	warehouse,
)

# --------------------------------------------------------------------------
# The demonstration story
# --------------------------------------------------------------------------

SEASON = "Summer 2026"
NEXT_SEASON = "Winter 2026-27"
FABRIC_GROUP = "Knit Fabrics"
TRIM_GROUP = "Sewing Trims"

FABRIC_SUPPLIER = "Shitalakshya Knit Fabrics Ltd"
TRIM_SUPPLIER = "Buriganga Trims and Accessories"
FABRIC_PROMISED_DAYS = 6
TRIM_PROMISED_DAYS = 4

FABRIC = "AT-FAB-SJ180-WHT"  # Single Jersey 180 GSM, Optic White, sold by the metre
THREAD = "AT-TRM-THR-402"  # 40/2 polyester sewing thread, 5000 m cones
OLD_BUTTON = "AT-TRM-BTN-20L"  # a discontinued button nobody has touched in ten weeks
TEE = "AT-TEE-CREW"  # crew-neck T-shirt template
TEE_COLOURS = ["Black", "White", "Blue"]
TEE_SIZES = ["Small", "Medium", "Large", "Extra Large"]

LOT_1 = ("SJ180-L01", "DL-2231")  # batch id, dye lot
LOT_2 = ("SJ180-L02", "DL-2317")
FABRIC_RATE = 245.0

FABRIC_SAFETY_STOCK = 150
FABRIC_REORDER_QTY = 800
THREAD_SAFETY_STOCK = 12
THREAD_REORDER_QTY = 100

# The fabric history below works out to:
#   usage       = (180 + 170 + 160) m issued in 30 days = 17 m a day
#   (all consumption is dated within the last 11 days, so the 30-day usage window
#   keeps every issue, and these numbers hold, for 19 days after seeding)
#   lead time   = (9 + 7) / 2 = 8 days  ->  reliability 6 / 8 = 75 %
#   reorder at  = 17 x 8 + 150 = 286 m      stock in Stores = 600 m
LIVE_TRANSFER = 330  # leaves 270 m in Stores, under the 286 m level

BINS = [
	("ST-A01", "Stores", FABRIC, "QR-ST-A01"),
	("ST-A02", "Stores", FABRIC, "QR-ST-A02"),
	("ST-B04", "Stores", THREAD, "QR-ST-B04"),
	("ST-D09", "Stores", OLD_BUTTON, "QR-ST-D09"),
	("WIP-CT01", "Work In Progress", FABRIC, "QR-WIP-CT01"),
	("FG-P01", "Finished Goods", None, "QR-FG-P01"),
]


def day(offset):
	return add_days(nowdate(), offset)


def step(message):
	print(f"  ->  {message}")


# --------------------------------------------------------------------------
# Builders, in dependency order
# --------------------------------------------------------------------------


def build_masters():
	for season in (SEASON, NEXT_SEASON):
		make_season(season)
	step(f"Season          {SEASON}, {NEXT_SEASON}")

	make_item_group(FABRIC_GROUP)
	make_item_group(TRIM_GROUP)
	step(f"Item Group      {FABRIC_GROUP}, {TRIM_GROUP}")

	make_item(
		FABRIC,
		item_name="Single Jersey 180 GSM Optic White",
		item_group=FABRIC_GROUP,
		has_batch_no=1,
		custom_season=SEASON,
		custom_shrinkage_percentage=4.5,
		valuation_rate=FABRIC_RATE,
	)
	step(f"Item            {FABRIC}  (Meter, batch = dye lot, shrinkage 4.5 %)")
	make_item(THREAD, item_name="Polyester Sewing Thread 40/2 (5000 m cone)", item_group=TRIM_GROUP, stock_uom="Nos", valuation_rate=185)
	make_item(OLD_BUTTON, item_name="Horn Button 20L (discontinued)", item_group=TRIM_GROUP, stock_uom="Nos", valuation_rate=3)
	step(f"Item            {THREAD}, {OLD_BUTTON}")

	build_garment_variants()

	for supplier, group, promised in (
		(FABRIC_SUPPLIER, FABRIC_GROUP, FABRIC_PROMISED_DAYS),
		(TRIM_SUPPLIER, TRIM_GROUP, TRIM_PROMISED_DAYS),
	):
		make_supplier(supplier)
		if not frappe.db.exists("Supplier Scorecard", {"supplier": supplier, "item_group": group}):
			frappe.get_doc(
				{
					"doctype": "Supplier Scorecard",
					"supplier": supplier,
					"item_group": group,
					"promised_lead_time_days": promised,
				}
			).insert(ignore_permissions=True)
		step(f"Supplier        {supplier}  (scorecard: {group}, promised {promised} days)")

	for bin_id, wh, item, code in BINS:
		make_storage_bin(bin_id, warehouse(wh), item, barcode=code)
	step(f"Storage Bin     {', '.join(b[0] for b in BINS)}")

	for batch_id, dye_lot in (LOT_1, LOT_2):
		make_batch(FABRIC, batch_id, dye_lot=dye_lot, roll_length=100)
	step(f"Batch           {LOT_1[0]} (dye lot {LOT_1[1]}), {LOT_2[0]} (dye lot {LOT_2[1]})")


def build_garment_variants():
	from erpnext.controllers.item_variant import create_multiple_variants

	make_item(
		TEE,
		item_name="Crew Neck T-Shirt",
		item_group="Products",
		stock_uom="Nos",
		has_variants=1,
		variant_based_on="Item Attribute",
		attributes=[{"attribute": "Colour"}, {"attribute": "Size"}],
		custom_season=SEASON,
	)
	create_multiple_variants(TEE, {"Colour": TEE_COLOURS, "Size": TEE_SIZES})
	count = frappe.db.count("Item", {"variant_of": TEE})
	step(f"Item template   {TEE}  -> {count} colour/size variants")


def receive(supplier, lines, ordered_on, received_on, batch_no=None):
	"""Purchase Order on one date, Purchase Receipt on another; the receipt updates the scorecard."""
	from erpnext.buying.doctype.purchase_order.mapper import make_purchase_receipt

	stores = warehouse("Stores")
	po = make_purchase_order(supplier, lines, day(ordered_on), stores)
	pr = make_purchase_receipt(po.name)
	pr.set_posting_time = 1
	pr.posting_date = day(received_on)
	for row in pr.items:
		if batch_no:
			row.batch_no = batch_no
			row.use_serial_batch_fields = 1
	pr.insert(ignore_permissions=True)
	pr.submit()
	step(f"Purchase Order  {po.name}  ordered {day(ordered_on)}  ->  Purchase Receipt {pr.name} on {day(received_on)}")
	return po, pr


def build_history():
	stores, wip, fg = warehouse("Stores"), warehouse("Work In Progress"), warehouse("Finished Goods")

	make_stock_entry("Material Receipt", OLD_BUTTON, 1500, target=stores, rate=3, posting_date=day(-70))
	step(f"Stock Entry     1,500 {OLD_BUTTON} received {day(-70)}  (never used again: dead stock)")

	receive(FABRIC_SUPPLIER, [(FABRIC, 700, FABRIC_RATE)], -40, -31, batch_no=LOT_1[0])  # 9 days
	receive(FABRIC_SUPPLIER, [(FABRIC, 500, FABRIC_RATE)], -28, -21, batch_no=LOT_2[0])  # 7 days
	receive(TRIM_SUPPLIER, [(THREAD, 120, 185)], -26, -22)  # 4 days, on time

	make_stock_entry("Material Transfer", FABRIC, 600, source=stores, target=wip, batch_no=LOT_1[0], rate=FABRIC_RATE, posting_date=day(-12))
	step(f"Stock Entry     600 m of {LOT_1[0]} to the cutting floor on {day(-12)}")

	for offset, qty, wastage in ((-10, 180, 6), (-7, 170, 5.5), (-3, 160, 4)):
		make_stock_entry(
			"Material Issue", FABRIC, qty, source=wip, batch_no=LOT_1[0], rate=FABRIC_RATE,
			posting_date=day(offset), custom_wastage_scrap_qty=wastage,
		)
		step(f"Stock Entry     {qty} m cut on {day(offset)}, wastage {wastage} m")

	make_stock_entry("Material Issue", THREAD, 40, source=stores, rate=185, posting_date=day(-11))
	step(f"Stock Entry     40 thread cones issued to the sewing lines on {day(-11)}")
	build_completed_reorder_cycle()
	make_stock_entry("Material Issue", THREAD, 35, source=stores, rate=185, posting_date=day(-2))
	step(f"Stock Entry     35 thread cones issued to the sewing lines on {day(-2)}")

	build_finished_goods_flow(wip, fg)


def build_completed_reorder_cycle():
	"""What happens after the engine raises a request: procurement orders it and it is received.

	The thread request below is shaped exactly like one the daily job raises, so the Material
	Request list and the dashboard's reorder trend have a finished cycle to show.
	"""
	from erpnext.stock.doctype.material_request.mapper import make_purchase_order as po_from_request

	stores = warehouse("Stores")
	mr = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": "Purchase",
			"company": COMPANY,
			"transaction_date": day(-10),
			"schedule_date": day(-3),
			"custom_generated_by": "Auto-Reorder Script",
			"custom_auto_generated": 1,
			"items": [{"item_code": THREAD, "qty": THREAD_REORDER_QTY, "warehouse": stores, "schedule_date": day(-3)}],
		}
	).insert(ignore_permissions=True)
	mr.submit()
	step(f"Material Request {mr.name}  auto-generated on {day(-10)}, {THREAD_REORDER_QTY} cones")

	po = po_from_request(mr.name)
	po.supplier = TRIM_SUPPLIER
	po.transaction_date = day(-10)
	for row in po.items:
		row.rate = 185
		row.schedule_date = day(-3)
	po.insert(ignore_permissions=True)
	po.submit()

	from erpnext.buying.doctype.purchase_order.mapper import make_purchase_receipt

	pr = make_purchase_receipt(po.name)
	pr.set_posting_time = 1
	pr.posting_date = day(-6)  # 4 days, as promised
	pr.insert(ignore_permissions=True)
	pr.submit()
	step(f"Purchase Order  {po.name}  made from {mr.name}  ->  Purchase Receipt {pr.name} on {day(-6)}")


def build_finished_goods_flow(wip, fg):
	"""Sewn T-shirts leave the line, go to Finished Goods, and part of them is despatched."""
	sewn = [("Black", "Medium", 240), ("White", "Large", 180), ("Blue", "Small", 150)]
	rows = [(_variant(colour, size), pieces) for colour, size, pieces in sewn]

	_multi_entry("Material Receipt", rows, day(-3), target=wip)
	step(f"Stock Entry     {sum(p for _, p in rows)} T-shirts booked off the sewing line into Work In Progress")
	_multi_entry("Material Transfer", rows, day(-2), source=wip, target=fg)
	step("Stock Entry     the same T-shirts moved Work In Progress -> Finished Goods")
	despatch = [(rows[0][0], 120)]
	_multi_entry("Material Transfer", despatch, day(-1), source=fg, target=warehouse("Goods In Transit"))
	step(f"Stock Entry     120 x {rows[0][0]} despatched: Finished Goods -> Goods In Transit")


def _multi_entry(entry_type, rows, posting_date, source=None, target=None):
	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": entry_type,
			"company": COMPANY,
			"set_posting_time": 1,
			"posting_date": posting_date,
			"items": [
				{"item_code": item, "qty": qty, "s_warehouse": source, "t_warehouse": target, "basic_rate": 410}
				for item, qty in rows
			],
		}
	).insert(ignore_permissions=True)
	entry.submit()
	return entry


def _variant(colour, size):
	for name in frappe.get_all("Item", filters={"variant_of": TEE}, pluck="name"):
		values = dict(
			frappe.get_all(
				"Item Variant Attribute", filters={"parent": name}, fields=["attribute", "attribute_value"], as_list=True
			)
		)
		if values.get("Colour") == colour and values.get("Size") == size:
			return name
	frappe.throw(f"No {colour} / {size} variant of {TEE}")


def build_reorder_rules():
	stores = warehouse("Stores")
	fabric = set_reorder_rule(FABRIC, stores, FABRIC_REORDER_QTY, FABRIC_SAFETY_STOCK).reorder_levels[0]
	thread = set_reorder_rule(THREAD, stores, THREAD_REORDER_QTY, THREAD_SAFETY_STOCK).reorder_levels[0]
	step(
		f"Item Reorder    {FABRIC}: level {fabric.warehouse_reorder_level:.2f} m "
		f"({fabric.custom_daily_usage:.2f} m/day x {fabric.custom_dynamic_lead_time_days:.2f} days + {FABRIC_SAFETY_STOCK})"
	)
	step(
		f"Item Reorder    {THREAD}: level {thread.warehouse_reorder_level:.2f} cones "
		f"({thread.custom_daily_usage:.2f}/day x {thread.custom_dynamic_lead_time_days:.2f} days + {THREAD_SAFETY_STOCK})"
	)
	return fabric


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------


def seed(reset: bool = False):
	"""Create the whole demonstration in dependency order."""
	frappe.set_user("Administrator")
	if reset:
		_purge()
	elif frappe.db.exists("Item", FABRIC):
		print(f"\nDemo data already exists ({FABRIC}). Run with --kwargs \"{{'reset': True}}\" to rebuild it.\n")
		return

	print("\nBuilding the demonstration data\n")
	build_masters()
	build_history()
	rule = build_reorder_rules()
	frappe.db.commit()
	print_walkthrough(rule)


def reset():
	"""Remove everything the demonstration created."""
	frappe.set_user("Administrator")
	_purge()


def _demo_items():
	return [FABRIC, THREAD, OLD_BUTTON, *frappe.get_all("Item", filters={"variant_of": TEE}, pluck="name"), TEE]


def _cancel_and_delete(doctype, names):
	for name in names:
		try:
			doc = frappe.get_doc(doctype, name)
			if doc.docstatus == 1:
				doc.cancel()
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True, delete_permanently=True)
			step(f"removed {doctype} {name}")
		except Exception as error:
			frappe.db.rollback()
			print(f"      could not remove {doctype} {name}: {error}")
		else:
			frappe.db.commit()


def _parents(child_doctype, items):
	return list(dict.fromkeys(frappe.get_all(child_doctype, filters={"item_code": ["in", items]}, pluck="parent")))


def _purge():
	print("\nRemoving previous demonstration data\n")
	items = _demo_items()
	suppliers = [FABRIC_SUPPLIER, TRIM_SUPPLIER]

	entries = _parents("Stock Entry Detail", items)
	entries.sort(key=lambda name: str(frappe.db.get_value("Stock Entry", name, "posting_date")), reverse=True)
	_cancel_and_delete("Stock Entry", entries)
	_cancel_and_delete("Purchase Receipt", frappe.get_all("Purchase Receipt", filters={"supplier": ["in", suppliers]}, pluck="name"))
	_cancel_and_delete("Purchase Order", frappe.get_all("Purchase Order", filters={"supplier": ["in", suppliers]}, pluck="name"))
	# requests last: ERPNext refuses to cancel a request while an order made from it exists
	_cancel_and_delete("Material Request", _parents("Material Request Item", items))
	_cancel_and_delete("Supplier Scorecard", frappe.get_all("Supplier Scorecard", filters={"supplier": ["in", suppliers]}, pluck="name"))
	_cancel_and_delete("Storage Bin", [b[0] for b in BINS if frappe.db.exists("Storage Bin", b[0])])
	_cancel_and_delete("Batch", [b for b, _ in (LOT_1, LOT_2) if frappe.db.exists("Batch", b)])
	_cancel_and_delete("Item", [i for i in items if frappe.db.exists("Item", i)])
	_cancel_and_delete("Supplier", [s for s in suppliers if frappe.db.exists("Supplier", s)])
	_cancel_and_delete("Item Group", [g for g in (FABRIC_GROUP, TRIM_GROUP) if frappe.db.exists("Item Group", g)])
	_cancel_and_delete("Season", [s for s in (SEASON, NEXT_SEASON) if frappe.db.exists("Season", s)])
	print()


def print_walkthrough(rule):
	stores = warehouse("Stores")
	line = "=" * 76
	level = flt(rule.warehouse_reorder_level)
	in_stores = stock_qty(FABRIC, stores)
	card = frappe.get_doc("Supplier Scorecard", {"supplier": FABRIC_SUPPLIER, "item_group": FABRIC_GROUP})

	print(f"\n{line}\n  READY FOR THE DEMONSTRATION\n{line}\n")
	print("  Open these in order:\n")
	print(f"    1. Item                {TEE}  -> Variants tab: {len(TEE_COLOURS) * len(TEE_SIZES)} colour/size items")
	print(f"    2. Item                {FABRIC}  -> Season {SEASON}, shrinkage 4.5 %, reorder rule")
	print(f"    3. Batch               {LOT_1[0]} / {LOT_2[0]}  -> dye lots {LOT_1[1]} / {LOT_2[1]}")
	print("    4. Warehouse tree      Stores, Work In Progress, Finished Goods, Goods In Transit")
	print(f"    5. Storage Bin         ST-A01 ... FG-P01, each with a QR value (scan QR-ST-A01)")
	print(f"    6. Purchase Receipt    received from {FABRIC_SUPPLIER}")
	print(f"    7. Supplier Scorecard  promised {card.promised_lead_time_days} days, measured {flt(card.actual_average_lead_time_days):.1f}, reliability {flt(card.reliability_score):.0f} %")
	print("    8. Stock Entry         transfers and issues with cutting wastage")
	print(f"    9. Material Request    the earlier auto-generated thread request -> Purchase Order -> received")
	print("   10. Stock Balance       T-shirts: Work In Progress -> Finished Goods -> Goods In Transit")
	print("   11. /app/apparel-inventory-dashboard   stock value, reorder trend, dead stock (the 20L buttons), reliability")
	print("   12. /app/dashboard-view/Supplier Performance\n")
	print(f"  Fabric in Stores now: {in_stores:,.0f} m    reorder level: {level:,.2f} m   (healthy)\n")
	print("  Then, live:\n")
	print(f"    a. New Stock Entry -> Material Transfer, {FABRIC}, {LIVE_TRANSFER} m,")
	print(f"       batch {LOT_2[0]}, Stores -> Work In Progress, submit.")
	print(f"       Stores drops to {in_stores - LIVE_TRANSFER:,.0f} m, under the {level:,.0f} m level.")
	print("    b. In the terminal:")
	print("         bench --site apparel-site execute apparel_track.apparel_track.tasks.daily_reorder_check")
	print(f"    c. Material Request list: a new request for {FABRIC_REORDER_QTY} m, flagged Auto Generated.")
	print("    d. Run the job again: no second request (the duplicate guard).\n")
	print(f"{line}\n")
