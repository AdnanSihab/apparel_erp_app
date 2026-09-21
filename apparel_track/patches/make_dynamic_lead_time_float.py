import frappe


def execute():
	"""Measured lead times are averages (e.g. 1.667 days); an Int field truncated them."""
	name = frappe.db.get_value(
		"Custom Field", {"dt": "Item Reorder", "fieldname": "custom_dynamic_lead_time_days"}
	)
	if not name or frappe.db.get_value("Custom Field", name, "fieldtype") == "Float":
		return

	# Custom Field.validate refuses any fieldtype change, but widening Int to Float is lossless
	frappe.db.set_value("Custom Field", name, "fieldtype", "Float")
	frappe.clear_cache(doctype="Item Reorder")
	frappe.db.updatedb("Item Reorder")
