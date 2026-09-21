# Copyright (c) 2026, Adnan and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import add_days, nowdate

from apparel_track.apparel_track.reorder_engine import process_reorder_engine


def daily_reorder_check():
	"""Scheduled daily trigger for apparel reorder logic."""
	process_reorder_engine()


@frappe.whitelist()
def get_apparel_dashboard_data(days: int = 30, dead_stock_days: int = 30) -> dict:
	"""Build dashboard data from stock, reorder, and supplier transaction history."""
	days = max(int(days or 30), 1)
	dead_stock_days = max(int(dead_stock_days or 30), 1)
	start_date = add_days(nowdate(), -days)
	stock_value_by_warehouse = frappe.db.sql(
		"""
		select warehouse, sum(actual_qty * valuation_rate) as stock_value
		from `tabBin`
		where actual_qty > 0
		group by warehouse
		order by stock_value desc
		""",
		as_dict=True,
	)
	dead_stock_ageing = frappe.db.sql(
		"""
		select b.item_code, b.warehouse, b.actual_qty,
			max(sle.posting_date) as last_movement_date,
			datediff(%s, max(sle.posting_date)) as age_days
		from `tabBin` b
		left join `tabStock Ledger Entry` sle
			on sle.item_code = b.item_code and sle.warehouse = b.warehouse
		where b.actual_qty > 0 and (sle.is_cancelled = 0 or sle.name is null)
		group by b.item_code, b.warehouse, b.actual_qty
		having last_movement_date is null or age_days >= %s
		order by age_days desc
		""",
		(nowdate(), dead_stock_days),
		as_dict=True,
	)
	reorder_triggers = frappe.db.sql(
		"""
		select transaction_date, count(*) as request_count
		from `tabMaterial Request`
		where docstatus < 2 and custom_auto_generated = 1
			and transaction_date >= %s
		group by transaction_date
		order by transaction_date
		""",
		(start_date,),
		as_dict=True,
	)
	supplier_reliability = frappe.get_all(
		"Supplier Scorecard",
		fields=[
			"supplier",
			"item_group",
			"promised_lead_time_days",
			"actual_average_lead_time_days",
			"reliability_score",
		],
		order_by="reliability_score asc",
	)
	return {
		"critical_stockouts": frappe.db.count("Bin", {"actual_qty": 0}),
		"pending_material_requests": frappe.db.count(
			"Material Request",
			{"docstatus": 1, "status": ["in", ["Pending", "Partially Ordered"]]},
		),
		"stock_value_by_warehouse": stock_value_by_warehouse,
		"dead_stock_ageing": dead_stock_ageing,
		"reorder_triggers": reorder_triggers,
		"supplier_reliability": supplier_reliability,
	}


@frappe.whitelist()
def get_supplier_performance_data() -> list:
	"""Return supplier-level promised and actual lead-time performance."""
	return frappe.db.sql(
		"""
		select supplier,
			count(*) as scorecards_counted,
			avg(promised_lead_time_days) as promised_lead_time_days,
			avg(actual_average_lead_time_days) as actual_average_lead_time_days,
			avg(reliability_score) as reliability_score,
			max(last_updated_on) as last_updated_on
		from `tabSupplier Scorecard`
		group by supplier
		order by reliability_score asc, supplier
		""",
		as_dict=True,
	)
