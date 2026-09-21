# Copyright (c) 2026, Adnan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.utils import flt


def get_default_bin_for_item(item_code: str, warehouse: str):
	"""Find the storage bin for an item in a warehouse, creating one if missing."""
	bin_name = frappe.db.get_value("Storage Bin", {"warehouse": warehouse, "current_item": item_code})
	if bin_name:
		return frappe.get_doc("Storage Bin", bin_name)

	bin = frappe.get_doc(
		{
			"doctype": "Storage Bin",
			"bin_id": f"{warehouse}-{item_code}-BIN",
			"warehouse": warehouse,
			"current_item": item_code,
			"max_capacity": 10000,
		}
	)
	bin.insert(ignore_permissions=True)
	frappe.db.commit()
	return bin


def update_storage_bin_on_stock_entry(stock_entry_name: str):
	"""Synchronize storage bin data with Stock Entry movements."""
	entry = frappe.get_doc("Stock Entry", stock_entry_name)
	if not entry.items:
		return

	for item in entry.items:
		if not item.item_code or not entry.to_warehouse:
			continue

		if entry.stock_entry_type in ["Material Receipt", "Material Transfer", "Manufacture"]:
			bin_doc = get_default_bin_for_item(item.item_code, entry.to_warehouse)
			bin_doc.current_item = item.item_code
			bin_doc.save(ignore_permissions=True)

		if entry.from_warehouse and entry.stock_entry_type in ["Material Issue", "Material Transfer"]:
			bin_doc = get_default_bin_for_item(item.item_code, entry.from_warehouse)
			bin_doc.current_item = item.item_code
			bin_doc.save(ignore_permissions=True)

	frappe.db.commit()


def update_batch_tracking_from_stock_entry(stock_entry_name: str):
	"""Attach manufacturer batch metadata to stock entries and calculate roll lengths."""
	entry = frappe.get_doc("Stock Entry", stock_entry_name)
	for item in entry.items:
		if not item.batch_no:
			continue
		batch = frappe.get_doc("Batch", item.batch_no)
		if not batch.custom_dye_lot_number:
			batch.custom_dye_lot_number = batch.name
		if not batch.custom_roll_length_meters:
			batch.custom_roll_length_meters = flt(item.qty) or 0
		batch.save(ignore_permissions=True)
	frappe.db.commit()


def process_inventory_on_submit(doc, method):
	"""ERPNext hook method: when stock entry is submitted, propagate bin and batch tracking."""
	if doc.doctype != "Stock Entry":
		return
	update_storage_bin_on_stock_entry(doc.name)
	update_batch_tracking_from_stock_entry(doc.name)


def on_purchase_receipt_submit(doc, method):
	"""Update supplier scorecard when purchase receipt is submitted."""
	from apparel_track.apparel_track.doctype.supplier_scorecard.supplier_scorecard import SupplierScorecard
	SupplierScorecard.update_supplier_lead_time_from_receipt(doc.name)
