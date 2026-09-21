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

	bin_id = f"{warehouse}-{item_code}-BIN"
	if frappe.db.exists("Storage Bin", bin_id):
		return frappe.get_doc("Storage Bin", bin_id)

	bin = frappe.get_doc(
		{
			"doctype": "Storage Bin",
			"bin_id": bin_id,
			"warehouse": warehouse,
			"current_item": item_code,
			"max_capacity": 10000,
			# every bin gets a scannable code; it can be replaced with the printed rack label
			"barcode_qr_code": bin_id,
		}
	)
	bin.insert(ignore_permissions=True)
	return bin


def update_storage_bin_on_stock_entry(stock_entry_name: str):
	"""Assign a storage bin in the target warehouse for stock coming into a warehouse."""
	entry = frappe.get_doc("Stock Entry", stock_entry_name)
	if entry.stock_entry_type not in ["Material Receipt", "Material Transfer", "Manufacture"]:
		return

	for item in entry.items:
		target_warehouse = item.t_warehouse or entry.to_warehouse
		if not item.item_code or not target_warehouse:
			continue

		bin_doc = get_default_bin_for_item(item.item_code, target_warehouse)
		if bin_doc.current_item != item.item_code:
			bin_doc.current_item = item.item_code
			bin_doc.save(ignore_permissions=True)


def update_batch_tracking_from_stock_entry(stock_entry_name: str):
	"""Fill in missing dye lot and roll length on batches booked in by a Material Receipt."""
	entry = frappe.get_doc("Stock Entry", stock_entry_name)
	if entry.stock_entry_type != "Material Receipt":
		return

	for item in entry.items:
		if not item.batch_no:
			continue
		batch = frappe.get_doc("Batch", item.batch_no)
		if batch.custom_dye_lot_number and batch.custom_roll_length_meters:
			continue
		if not batch.custom_dye_lot_number:
			batch.custom_dye_lot_number = batch.name
		if not batch.custom_roll_length_meters:
			batch.custom_roll_length_meters = flt(item.transfer_qty) or 0
		batch.save(ignore_permissions=True)


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
