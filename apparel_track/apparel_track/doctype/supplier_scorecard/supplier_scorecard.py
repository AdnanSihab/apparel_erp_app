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

		if not pr.posting_date:
			return

		# one delivery per purchase order and item group, however many lines it has
		deliveries = set()
		for item in pr.items:
			if not item.purchase_order:
				continue
			item_group = item.item_group or frappe.db.get_value("Item", item.item_code, "item_group")
			if item_group:
				deliveries.add((item_group, item.purchase_order))

		for item_group, purchase_order in sorted(deliveries):
			po_date = frappe.db.get_value("Purchase Order", purchase_order, "transaction_date")
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
			record.reliability_score = SupplierScorecard.get_reliability_score(
				record.promised_lead_time_days, record.actual_average_lead_time_days
			)
			record.save(ignore_permissions=True)

	@staticmethod
	def get_reliability_score(promised_days, actual_days) -> float:
		"""Promised lead time / measured average lead time, as a percentage capped at 100."""
		promised = flt(promised_days)
		if not promised:
			return 0
		actual = flt(actual_days)
		if actual <= 0:
			# delivered on the order date: faster than any promise
			return 100
		return min(flt(promised / actual * 100), 100)

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
		record.supplier = supplier
		record.item_group = item_group
		return record
