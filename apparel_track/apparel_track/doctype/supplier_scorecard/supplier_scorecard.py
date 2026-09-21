# Copyright (c) 2026, Adnan and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import date_diff, flt
from frappe.model.document import Document


class SupplierScorecard(Document):
	"""Supplier delivery performance scorecard used for apparel procurement."""

	_DOCTYPE_NAME = "Supplier Scorecard"

	@staticmethod
	def update_supplier_lead_time_from_receipt(purchase_receipt_name: str):
		"""Update supplier scorecard based on purchase receipt date vs purchase order date."""
		if not purchase_receipt_name:
			return

		pr = frappe.get_doc("Purchase Receipt", purchase_receipt_name)
		if not pr.supplier:
			return

		for item in pr.items:
			if not item.purchase_order or not pr.posting_date:
				continue
			item_group = item.item_group or frappe.db.get_value("Item", item.item_code, "item_group")
			if not item_group:
				continue

			po_date = frappe.db.get_value("Purchase Order", item.purchase_order, "transaction_date")
			if not po_date:
				continue

			days_delta = max(date_diff(pr.posting_date, po_date), 0)
			record = SupplierScorecard._get_scorecard(pr.supplier, item_group)
			counted = int(record.receipts_counted or 0)
			record.actual_average_lead_time_days = (
				(flt(record.actual_average_lead_time_days) * counted) + days_delta
			) / (counted + 1)
			record.receipts_counted = counted + 1
			record.last_updated_on = frappe.utils.nowdate()
			promised = flt(record.promised_lead_time_days)
			record.reliability_score = min(
				flt(promised / record.actual_average_lead_time_days * 100)
				if promised and record.actual_average_lead_time_days
				else 0,
				100,
			)
			record.save(ignore_permissions=True)

	@staticmethod
	def _get_scorecard(supplier: str, item_group: str):
		"""Return the scorecard for one supplier and item group."""
		name = frappe.db.get_value(
			"Supplier Scorecard",
			{"supplier": supplier, "item_group": item_group},
			"name",
		)
		if name:
			return frappe.get_doc("Supplier Scorecard", name)

		record = frappe.new_doc("Supplier Scorecard")
		record.name = f"{supplier}-{item_group}"
		record.supplier = supplier
		record.item_group = item_group
		return record
