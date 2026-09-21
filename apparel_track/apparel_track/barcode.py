# Copyright (c) 2026, Adnan and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from erpnext.stock.utils import scan_barcode as erpnext_scan_barcode


@frappe.whitelist()
def scan_barcode(search_value: str, ctx: dict | str | None = None) -> dict:
	"""ERPNext barcode scan, extended so a Storage Bin barcode resolves to the bin's warehouse."""
	result = erpnext_scan_barcode(search_value, ctx)
	if result:
		return result

	warehouse = frappe.db.get_value("Storage Bin", {"barcode_qr_code": search_value}, "warehouse")
	if warehouse and not frappe.get_cached_value("Warehouse", warehouse, "disabled"):
		return {"warehouse": warehouse}

	return {}
