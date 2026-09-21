# Copyright (c) 2026, Adnan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.utils import flt


def get_item_reorder_record(item_code: str, warehouse: str | None = None):
	"""Return the first Item Reorder row configured for the item and warehouse."""
	item = frappe.get_doc("Item", item_code)
	for row in item.reorder_levels:
		if warehouse and row.warehouse != warehouse:
			continue
		return row
	return None


def get_bin_stock_for_item(item_code: str, warehouse: str | None = None):
	"""Return available stock from bin ledger for a given item and warehouse."""
	stock = frappe.db.get_value(
		"Bin",
		{"item_code": item_code, "warehouse": warehouse} if warehouse else {"item_code": item_code},
		"actual_qty",
	)
	return flt(stock or 0)


def get_average_daily_usage(item_code: str, days: int = 30):
	"""Return average consumed quantity per day from submitted material issues."""
	start_date = frappe.utils.add_days(frappe.utils.nowdate(), -days)
	consumed = frappe.db.sql(
		"""
		select coalesce(sum(sed.qty), 0)
		from `tabStock Entry Detail` sed
		join `tabStock Entry` se on se.name = sed.parent
		where se.docstatus = 1
			and se.stock_entry_type = 'Material Issue'
			and sed.item_code = %s
			and se.posting_date >= %s
		""",
		(item_code, start_date),
	)[0][0]
	return flt(consumed) / days


def get_average_supplier_lead_time(item_group: str | None):
	"""Return the current measured lead time for an item group."""
	if not item_group:
		return 0
	return flt(
		frappe.db.sql(
			"""
			select avg(actual_average_lead_time_days)
			from `tabSupplier Scorecard`
			where item_group = %s
			""",
			(item_group,),
		)[0][0]
		or 0
	)


def calculate_reorder_level(lead_time_days: int | float, daily_usage: float, safety_stock: float = 0):
	"""Reorder level = lead time demand + safety stock."""
	if lead_time_days < 0:
		lead_time_days = 0
	return flt(daily_usage * float(lead_time_days)) + flt(safety_stock)


def update_item_reorder_levels(doc, method):
	"""Validate and auto-compute reorder level for Item Reorder child rows."""
	if not getattr(doc, "reorder_levels", None):
		return

	for row in doc.reorder_levels:
		lead_time = get_average_supplier_lead_time(doc.item_group)
		safety = flt(getattr(row, "custom_safety_stock_qty", 0) or 0)
		daily_usage = get_average_daily_usage(doc.name)
		row.custom_dynamic_lead_time_days = lead_time
		row.custom_daily_usage = daily_usage
		row.warehouse_reorder_level = calculate_reorder_level(lead_time, daily_usage, safety)
		if flt(row.warehouse_reorder_qty) <= 0:
			row.warehouse_reorder_qty = flt(row.warehouse_reorder_level) or 1
		if row.warehouse_reorder_level < 0:
			row.warehouse_reorder_level = 0


def create_material_request_for_reorder(item_code: str, warehouse: str, reorder_qty: float, generated_by: str = "Auto-Reorder Script"):
	"""Create a Material Request if one is not already pending."""
	pending = frappe.db.sql(
		"""
		select mri.name
		from `tabMaterial Request Item` mri
		join `tabMaterial Request` mr on mr.name = mri.parent
		where mr.docstatus in (0, 1)
			and mr.material_request_type = 'Purchase'
			and mri.item_code = %s
			and mri.warehouse = %s
			and coalesce(mri.stock_qty, mri.qty) > coalesce(mri.ordered_qty, 0)
		limit 1
		""",
		(item_code, warehouse),
	)
	if pending:
		return None

	mr = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": "Purchase",
			"company": frappe.db.get_value("Warehouse", warehouse, "company"),
			"schedule_date": frappe.utils.add_days(frappe.utils.nowdate(), 7),
			"custom_generated_by": generated_by,
			"custom_auto_generated": 1,
			"items": [{
				"item_code": item_code,
				"qty": reorder_qty,
				"warehouse": warehouse,
				"schedule_date": frappe.utils.add_days(frappe.utils.nowdate(), 7),
			}],
		}
	)
	mr.insert(ignore_permissions=True)
	mr.submit()
	frappe.db.commit()
	return mr


def process_reorder_engine_for_warehouse(warehouse: str | None = None):
	"""Scan Item Reorder rows and create missing Material Requests."""
	items = frappe.get_all("Item", filters={"is_stock_item": 1}, fields=["name"], limit_page_length=0)
	for item in items:
		item_doc = frappe.get_doc("Item", item.name)
		if item_doc.reorder_levels:
			update_item_reorder_levels(item_doc, None)
			item_doc.save(ignore_permissions=True)
		for row in item_doc.reorder_levels:
			if warehouse and row.warehouse != warehouse:
				continue
			actual_qty = get_bin_stock_for_item(item_doc.name, row.warehouse)
			if actual_qty > flt(row.warehouse_reorder_level):
				continue
			if flt(row.warehouse_reorder_qty) <= 0:
				continue
			create_material_request_for_reorder(
				item_code=item_doc.name,
				warehouse=row.warehouse,
				reorder_qty=row.warehouse_reorder_qty,
			)


def process_reorder_engine():
	"""Daily job entry point for the reorder engine."""
	process_reorder_engine_for_warehouse()


def update_supplier_scorecards():
	"""Refresh scorecards for all suppliers based on recent purchase receipts."""
	receipts = frappe.get_all(
		"Purchase Receipt",
		filters={"docstatus": 1},
		fields=["name", "supplier", "posting_date"],
		order_by="posting_date desc",
	)
	for receipt in receipts:
		frappe.get_doc("Purchase Receipt", receipt.name).run_method("_update_supplier_scorecard")
		frappe.db.commit()
