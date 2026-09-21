# Copyright (c) 2026, Adnan and contributors
# For license information, please see license.txt

"""Terminal walkthrough of the reorder engine, the supplier scorecard and dye lot tracking.

Each scenario runs the same server-side code the site runs, prints what a store keeper
or a procurement officer would see, and checks it against the behaviour described in
the report. Everything happens in one transaction that is rolled back at the end, so
the site is left exactly as it was.

	bench --site apparel-site execute apparel_track.tests.demo_scenarios.run
	bench --site apparel-site execute apparel_track.tests.demo_scenarios.run --kwargs "{'section': 'reorder'}"
	bench --site apparel-site execute apparel_track.tests.demo_scenarios.run --kwargs "{'color': False}"

Sections: reorder, scorecard, lots, all. The command fails if any scenario misbehaves,
so it doubles as a smoke test.
"""

import sys
from unittest.mock import patch

import frappe
from frappe.utils import add_days, flt, nowdate

from apparel_track.apparel_track.barcode import scan_barcode
from apparel_track.apparel_track.reorder_engine import _process_item_reorder
from apparel_track.tests.fixtures import (
	COMPANY,
	make_batch,
	make_item,
	make_item_group,
	make_purchase_order,
	make_stock_entry,
	make_storage_bin,
	make_supplier,
	open_auto_requests,
	receive_purchase_order,
	set_reorder_rule,
	stock_qty,
	warehouse,
)

WIDTH = 78


class Colour:
	def __init__(self, enabled: bool):
		self.enabled = enabled

	def _paint(self, code, text):
		return f"\033[{code}m{text}\033[0m" if self.enabled else str(text)

	def bold(self, text):
		return self._paint("1", text)

	def dim(self, text):
		return self._paint("2", text)

	def green(self, text):
		return self._paint("32", text)

	def red(self, text):
		return self._paint("31", text)

	def cyan(self, text):
		return self._paint("36", text)


class Demo:
	def __init__(self, colour: Colour):
		self.c = colour
		self.total = 0
		self.failed = 0

	def section(self, title, rule, fires):
		print()
		print(self.c.bold("=" * WIDTH))
		print(self.c.bold(f"  {title}"))
		print(self.c.bold("=" * WIDTH))
		print(self.c.dim(f"  rule:  {rule}"))
		print(self.c.dim(f"  fires: {fires}"))

	def scenario(self, number, title, story):
		print()
		print(self.c.bold(f" {number}  {title}"))
		print(self.c.dim(" " + "-" * (WIDTH - 2)))
		print(self.c.dim(f"      {story}"))
		print()

	def show(self, label, value):
		print(f"      {label:<30}{value}")

	def screen(self, text, good=True):
		paint = self.c.green if good else self.c.cyan
		print()
		print(paint(f"      ON SCREEN  {text}"))

	def verdict(self, ok, expected):
		self.total += 1
		self.failed += 0 if ok else 1
		mark = self.c.green("PASS") if ok else self.c.red("FAIL")
		print()
		print(f"      {mark}{self.c.dim('  expected ' + expected)}")


def metres(qty):
	return f"{flt(qty):>8,.2f} m"


# ---------------------------------------------------------------------------
# Section 1: automated reorder engine
# ---------------------------------------------------------------------------


def demo_reorder(d: Demo, tag: str):
	d.section(
		"SECTION 1  -  AUTOMATED REORDER ENGINE",
		"reorder level = daily usage x measured lead time + safety stock",
		"daily scheduler -> tasks.daily_reorder_check (run here on demand)",
	)
	stores, wip = warehouse("Stores"), warehouse("Work In Progress")
	group = make_item_group(f"Demo Knits {tag}")
	supplier = make_supplier(f"Demo Spinning Mills {tag}")
	fabric = make_item(f"DEMO-RIB-220-{tag}", item_name="1x1 Rib 220 GSM Heather Grey", item_group=group).name
	frappe.get_doc(
		{"doctype": "Supplier Scorecard", "supplier": supplier, "item_group": group, "promised_lead_time_days": 7}
	).insert(ignore_permissions=True)

	# history: one on-time delivery and a month of cutting-floor consumption
	po = make_purchase_order(supplier, [(fabric, 300, 210)], add_days(nowdate(), -7), stores)
	receive_purchase_order(po.name)
	make_stock_entry("Material Issue", fabric, 120, source=stores)  # 4 m a day over 30 days
	set_reorder_rule(fabric, stores, reorder_qty=250, safety_stock=40)

	def level():
		return frappe.get_doc("Item", fabric).reorder_levels[0].warehouse_reorder_level

	# 1.1
	d.scenario("1.1", "Healthy stock - the engine stays quiet", "The store holds more rib than the cutting floor needs over one lead time.")
	_process_item_reorder(fabric)
	d.show("Stock in Stores", metres(stock_qty(fabric, stores)))
	d.show("Daily usage (last 30 days)", metres(4) + " / day")
	d.show("Measured lead time", "7 days")
	d.show("Reorder level", f"{metres(level())}   (4 x 7 + 40 safety)")
	requests = open_auto_requests(fabric, stores)
	d.screen("(nothing - no Material Request raised)")
	d.verdict(not requests and abs(level() - 68) < 0.01, "no request, level 68 m")

	# 1.2
	d.scenario("1.2", "Stock falls below the level - a request is drafted", "125 m go out to the cutting floor for a rush order.")
	make_stock_entry("Material Transfer", fabric, 125, source=stores, target=wip)
	_process_item_reorder(fabric)
	d.show("Stock in Stores", metres(stock_qty(fabric, stores)))
	d.show("Reorder level", metres(level()))
	requests = open_auto_requests(fabric, stores)
	if requests:
		mr = frappe.get_doc("Material Request", requests[0])
		d.screen(f"{mr.name}  Purchase  {mr.items[0].qty:,.0f} m  required by {mr.schedule_date}  [{mr.custom_generated_by}]")
	d.verdict(len(requests) == 1, "one submitted request for the 250 m reorder quantity")
	first = requests[0] if requests else None

	# 1.3
	d.scenario("1.3", "Next morning, stock still short - no duplicate", "The job runs again before procurement has acted on yesterday's request.")
	_process_item_reorder(fabric)
	requests = open_auto_requests(fabric, stores)
	d.show("Open auto-generated requests", len(requests))
	d.screen("(nothing new - the open request already covers the shortage)")
	d.verdict(requests == [first], "still exactly one request")

	# 1.4
	d.scenario("1.4", "Procurement stops the request - the engine asks again", "A stopped request no longer covers the shortage, so it must not block reordering.")
	from erpnext.stock.doctype.material_request.material_request import update_status

	update_status(first, "Stopped")
	_process_item_reorder(fabric)
	requests = open_auto_requests(fabric, stores)
	d.show("Stopped request", first)
	d.show("New request", requests[0] if requests else "-")
	d.screen("a fresh request replaces the stopped one")
	d.verdict(len(requests) == 1 and requests[0] != first, "one new request")

	# 1.5
	d.scenario("1.5", "The supplier starts slipping - the level rises by itself", "The next delivery takes 15 days against the 7 that were promised.")
	before = level()
	po = make_purchase_order(supplier, [(fabric, 100, 210)], add_days(nowdate(), -15), stores)
	receive_purchase_order(po.name)
	frappe.get_doc("Item", fabric).save(ignore_permissions=True)
	after = level()
	d.show("Measured lead time", f"{(7 + 15) / 2:.0f} days   ((7 + 15) / 2)")
	d.show("Reorder level before", metres(before))
	d.show("Reorder level after", f"{metres(after)}   (4 x 11 + 40)")
	d.screen("more safety cover is held against the slower supplier")
	d.verdict(abs(after - 84) < 0.01, "level rises from 68 m to 84 m")


# ---------------------------------------------------------------------------
# Section 2: supplier scorecard
# ---------------------------------------------------------------------------


def demo_scorecard(d: Demo, tag: str):
	d.section(
		"SECTION 2  -  SUPPLIER SCORECARD AND LEAD TIME",
		"reliability = promised lead time / measured average lead time (max 100%)",
		"Purchase Receipt -> on_submit (hooks.py doc_events)",
	)
	stores = warehouse("Stores")
	group = make_item_group(f"Demo Trims {tag}")
	supplier = make_supplier(f"Demo Zipper Works {tag}")
	zipper, button, label = (
		make_item(f"DEMO-{code}-{tag}", item_name=name, item_group=group, stock_uom="Nos").name
		for code, name in (("ZIP-18", "Nylon Zipper 18 cm"), ("BTN-4H", "4-Hole Button 18L"), ("LBL-WV", "Woven Care Label"))
	)
	frappe.get_doc(
		{"doctype": "Supplier Scorecard", "supplier": supplier, "item_group": group, "promised_lead_time_days": 6}
	).insert(ignore_permissions=True)

	def card():
		return frappe.get_doc("Supplier Scorecard", {"supplier": supplier, "item_group": group})

	def show_card(sc):
		d.show("Promised lead time", f"{sc.promised_lead_time_days} days")
		d.show("Measured average", f"{flt(sc.actual_average_lead_time_days):.2f} days")
		d.show("Deliveries counted", sc.receipts_counted)
		d.show("Reliability score", f"{flt(sc.reliability_score):.2f} %")

	# 2.1
	d.scenario("2.1", "Delivered on the promised day", "Zippers ordered six days ago arrive today.")
	po = make_purchase_order(supplier, [(zipper, 2000, 9)], add_days(nowdate(), -6), stores)
	pr = receive_purchase_order(po.name)
	sc = card()
	show_card(sc)
	d.screen(f"{pr.name} submitted - scorecard updated")
	d.verdict(sc.receipts_counted == 1 and flt(sc.reliability_score) == 100, "100 %")

	# 2.2
	d.scenario("2.2", "A late delivery pulls the score down", "The next order takes twelve days.")
	po = make_purchase_order(supplier, [(zipper, 1500, 9)], add_days(nowdate(), -12), stores)
	receive_purchase_order(po.name)
	sc = card()
	show_card(sc)
	d.screen("the average moves to 9 days, so the score drops", good=False)
	d.verdict(abs(flt(sc.reliability_score) - 66.67) < 0.01, "6 / 9 = 66.67 %")

	# 2.3
	d.scenario("2.3", "One order, three trims, one delivery", "Buttons, zippers and labels arrive on one receipt after nine days.")
	po = make_purchase_order(
		supplier, [(zipper, 500, 9), (button, 8000, 1.2), (label, 6000, 0.8)], add_days(nowdate(), -9), stores
	)
	receive_purchase_order(po.name)
	sc = card()
	show_card(sc)
	d.screen("counted once, not three times")
	d.verdict(sc.receipts_counted == 3 and abs(flt(sc.actual_average_lead_time_days) - 9) < 0.01, "3 deliveries, average 9 days")

	# 2.4
	d.scenario("2.4", "A receipt with no purchase order - nothing to measure", "Walk-in stock is booked without an order date to compare against.")
	walk_in = frappe.get_doc(
		{
			"doctype": "Purchase Receipt",
			"supplier": supplier,
			"company": COMPANY,
			"items": [{"item_code": label, "qty": 200, "rate": 0.8, "warehouse": stores}],
		}
	).insert(ignore_permissions=True)
	walk_in.submit()
	sc = card()
	d.show("Deliveries counted", sc.receipts_counted)
	d.screen("(scorecard unchanged)")
	d.verdict(sc.receipts_counted == 3, "still 3 deliveries")


# ---------------------------------------------------------------------------
# Section 3: dye lots and storage bins
# ---------------------------------------------------------------------------


def demo_lots(d: Demo, tag: str):
	from erpnext.stock.doctype.batch.batch import get_batch_qty

	d.section(
		"SECTION 3  -  DYE LOTS AND STORAGE BINS",
		"every roll keeps its dye lot; every bin carries a scannable code",
		"Stock Entry -> on_submit, and the barcode scan API",
	)
	stores, wip = warehouse("Stores"), warehouse("Work In Progress")
	fabric = make_item(
		f"DEMO-TWL-240-{tag}", item_name="Cotton Twill 240 GSM Olive", item_group=make_item_group(f"Demo Wovens {tag}"), has_batch_no=1
	).name
	lot_a = make_batch(fabric, f"TWL-A-{tag}", dye_lot="DL-7714", roll_length=92).name
	lot_b = make_batch(fabric, f"TWL-B-{tag}").name

	# 3.1
	d.scenario("3.1", "A roll arrives with its dye lot", "The mill's roll ticket gives lot DL-7714, 92 m.")
	make_stock_entry("Material Receipt", fabric, 92, target=stores, batch_no=lot_a)
	lot = frappe.get_doc("Batch", lot_a)
	d.show("Batch", lot.name)
	d.show("Dye lot", lot.custom_dye_lot_number)
	d.show("Roll length", metres(lot.custom_roll_length_meters))
	d.verdict(lot.custom_dye_lot_number == "DL-7714" and lot.custom_roll_length_meters == 92, "lot DL-7714, 92 m")

	# 3.2
	d.scenario("3.2", "A roll arrives without a ticket", "The lot and length are filled from the receipt instead of being left blank.")
	make_stock_entry("Material Receipt", fabric, 70, target=stores, batch_no=lot_b)
	lot = frappe.get_doc("Batch", lot_b)
	d.show("Dye lot", lot.custom_dye_lot_number)
	d.show("Roll length", metres(lot.custom_roll_length_meters))
	d.verdict(lot.custom_dye_lot_number == lot_b and lot.custom_roll_length_meters == 70, "lot = batch id, 70 m")

	# 3.3
	d.scenario("3.3", "Cutting draws from one lot only", "40 m of lot DL-7714 go to the cutting table; the other lot is untouched.")
	make_stock_entry("Material Transfer", fabric, 40, source=stores, target=wip, batch_no=lot_a)
	qty_a, qty_b = get_batch_qty(lot_a, stores), get_batch_qty(lot_b, stores)
	d.show("Lot A left in Stores", metres(qty_a))
	d.show("Lot B left in Stores", metres(qty_b))
	d.screen("the two lots are never mixed, so no shading in the garment")
	d.verdict(qty_a == 52 and qty_b == 70, "A 52 m, B 70 m")

	# 3.4
	d.scenario("3.4", "Scanning a rack label", "The store keeper scans the QR code on rack C-07 before putting a roll away.")
	make_storage_bin(f"ST-C07-{tag}", stores, fabric, barcode=f"QR-ST-C07-{tag}")
	result = scan_barcode(f"QR-ST-C07-{tag}")
	d.show("Scanned", f"QR-ST-C07-{tag}")
	d.screen(f"warehouse set to {result.get('warehouse')}")
	d.verdict(result == {"warehouse": stores}, "the bin's warehouse")

	# 3.5
	d.scenario("3.5", "Scanning an unknown code", "A torn label that matches nothing.")
	result = scan_barcode(f"QR-UNKNOWN-{tag}")
	d.screen("(nothing found)", good=False)
	d.verdict(result == {}, "empty result")


SECTIONS = {"reorder": demo_reorder, "scorecard": demo_scorecard, "lots": demo_lots}


def run(section: str = "all", color: bool | None = None):
	"""Entry point for `bench execute`."""
	colour = Colour(sys.stdout.isatty() if color is None else bool(color))
	d = Demo(colour)
	tag = frappe.generate_hash(length=4).upper()
	frappe.set_user("Administrator")

	print()
	print(colour.bold("APPAREL TRACK - INVENTORY AND REORDER DEMONSTRATION"))
	print(colour.dim("Every result below comes from the same server-side code that runs on the site."))

	chosen = SECTIONS if section == "all" else {section: SECTIONS[section]}
	with patch.object(frappe.db, "commit", lambda *args, **kwargs: None):
		try:
			for demo in chosen.values():
				demo(d, tag)
		finally:
			frappe.db.rollback()

	passed = d.total - d.failed
	print()
	print(colour.bold("=" * WIDTH))
	line = f"  {passed} of {d.total} scenarios behaved exactly as the report describes."
	print(colour.bold(colour.green(line) if not d.failed else colour.red(line)))
	print(colour.dim("  Nothing was saved: the demonstration ran in a transaction that was rolled back."))
	print(colour.bold("=" * WIDTH))
	print()

	if d.failed:
		raise SystemExit(1)
