# Copyright (c) 2026, Adnan and contributors
# For license information, please see license.txt

import frappe


def ensure_custom_field(doctype_name: str, fieldname: str, fieldtype: str, label: str, **kwargs):
	"""Create a custom field if it doesn't already exist."""
	if frappe.db.exists("Custom Field", {"dt": doctype_name, "fieldname": fieldname}):
		return
	if fieldname in {field.fieldname for field in frappe.get_meta(doctype_name).fields}:
		return

	field = frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": doctype_name,
			"fieldname": fieldname,
			"label": label,
			"fieldtype": fieldtype,
			"insert_after": kwargs.get("insert_after"),
			"options": kwargs.get("options"),
			"default": kwargs.get("default"),
			"reqd": kwargs.get("reqd", 0),
			"read_only": kwargs.get("read_only", 0),
			"depends_on": kwargs.get("depends_on"),
			"in_list_view": kwargs.get("in_list_view", 0),
			"fetch_from": kwargs.get("fetch_from"),
			"allow_on_submit": kwargs.get("allow_on_submit", 0),
		}
	)
	field.insert(ignore_permissions=True)
	frappe.db.commit()


def ensure_supplier_scorecard_doctype():
	"""Create the Supplier Scorecard custom document if missing."""
	if frappe.db.exists("DocType", "Supplier Scorecard"):
		fields = [
			("item_group", "Link", "Item Category / Group", "Item Group", None, 0),
			("promised_lead_time_days", "Int", "Promised Lead Time (Days)", None, 0, 0),
			("actual_average_lead_time_days", "Float", "Actual Average Lead Time (Days)", None, 0, 0),
			("receipts_counted", "Int", "Receipts Counted", None, 0, 1),
			("reliability_score", "Percent", "Reliability Score", None, 0, 0),
			("last_updated_on", "Date", "Last Updated On", None, None, 0),
			("remarks", "Text Editor", "Remarks", None, None, 0),
		]
		for fieldname, fieldtype, label, options, default, read_only in fields:
			ensure_custom_field(
				"Supplier Scorecard",
				fieldname,
				fieldtype,
				label,
				options=options,
				default=default,
				read_only=read_only,
			)
		return

	doc = frappe.get_doc(
		{
			"doctype": "DocType",
			"module": "Apparel Track",
			"custom": 1,
			"is_submittable": 0,
			"istable": 0,
			"name": "Supplier Scorecard",
			"fields": [
				{
					"fieldname": "supplier",
					"fieldtype": "Link",
					"label": "Supplier",
					"options": "Supplier",
					"reqd": 1,
				},
				{
					"fieldname": "item_group",
					"fieldtype": "Link",
					"label": "Item Category / Group",
					"options": "Item Group",
				},
				{
					"fieldname": "promised_lead_time_days",
					"fieldtype": "Int",
					"label": "Promised Lead Time (Days)",
					"default": 0,
				},
				{
					"fieldname": "actual_average_lead_time_days",
					"fieldtype": "Float",
					"label": "Actual Average Lead Time (Days)",
					"default": 0,
				},
				{
					"fieldname": "receipts_counted",
					"fieldtype": "Int",
					"label": "Receipts Counted",
					"default": 0,
					"read_only": 1,
				},
				{
					"fieldname": "reliability_score",
					"fieldtype": "Percent",
					"label": "Reliability Score",
					"default": 0,
				},
				{
					"fieldname": "last_updated_on",
					"fieldtype": "Date",
					"label": "Last Updated On",
				},
				{
					"fieldname": "remarks",
					"fieldtype": "Text Editor",
					"label": "Remarks",
				},
			],
			"permissions": [
				{
					"role": "System Manager",
					"read": 1,
					"write": 1,
					"create": 1,
					"delete": 1,
					"submit": 0,
					"cancel": 0,
					"email": 1,
					"print": 1,
					"share": 1,
					"export": 1,
					"report": 1,
				},
			],
		}
	)
	doc.insert(ignore_permissions=True)
	frappe.db.commit()


def ensure_supplier_performance_dashboard():
	"""Create the native dashboard used by the supplier performance route."""
	dashboard = frappe.db.exists("Dashboard", "Supplier Performance")
	if dashboard:
		dashboard = frappe.get_doc("Dashboard", dashboard)
	else:
		dashboard = frappe.get_doc(
		{
			"doctype": "Dashboard",
			"dashboard_name": "Supplier Performance",
			"is_default": 0,
			"charts": [],
		}
	)

	charts = [
		("Supplier Promised Lead Time", "promised_lead_time_days", "#1677ff"),
		("Supplier Actual Lead Time", "actual_average_lead_time_days", "#e8590c"),
		("Supplier Reliability", "reliability_score", "#2f9e44"),
	]
	valid_chart_names = {chart[0] for chart in charts}
	for linked_chart in dashboard.charts:
		if linked_chart.chart not in valid_chart_names:
			frappe.delete_doc("Dashboard Chart Link", linked_chart.name, ignore_permissions=True)
	dashboard.reload()
	linked_charts = {chart.chart for chart in dashboard.charts}
	for chart_name, value_field, color in charts:
		if not frappe.db.exists("Dashboard Chart", chart_name):
			frappe.get_doc(
				{
					"doctype": "Dashboard Chart",
					"chart_name": chart_name,
					"chart_type": "Group By",
					"document_type": "Supplier Scorecard",
					"group_by_based_on": "supplier",
					"group_by_type": "Average",
					"aggregate_function_based_on": value_field,
					"type": "Bar",
					"color": color,
					"filters_json": "[]",
					"is_public": 1,
				}
			).insert(ignore_permissions=True)
		if chart_name not in linked_charts:
			dashboard.append("charts", {"chart": chart_name})
			dashboard.save(ignore_permissions=True)
		linked_charts.add(chart_name)
	frappe.db.commit()


def ensure_supplier_performance_page():
	"""Remove the legacy page so search resolves to the native dashboard."""
	page_name = "supplier-performance-dashboard"
	if frappe.db.exists("Page", page_name):
		frappe.delete_doc("Page", page_name, ignore_permissions=True)
	frappe.db.commit()


def ensure_supplier_performance_workspace_link():
	"""Keep the supplier performance dashboard available from the Buying workspace."""
	workspace = frappe.db.exists("Workspace", "Buying")
	if not workspace:
		return

	workspace = frappe.get_doc("Workspace", workspace)
	links = [link for link in workspace.links if link.label != "Supplier Performance"]
	changed = len(links) != len(workspace.links)
	if changed:
		workspace.set("links", links)

	for shortcut in workspace.shortcuts:
		if shortcut.label == "Supplier Performance" and (
			shortcut.type != "Dashboard" or shortcut.url or shortcut.link_to != "Supplier Performance"
		):
			shortcut.type = "Dashboard"
			shortcut.url = None
			shortcut.link_to = "Supplier Performance"
			changed = True

	# Buying is a standard ERPNext workspace: in developer mode every save is exported
	# back into ERPNext's own files, so only save when something actually changed
	if changed:
		workspace.save(ignore_permissions=True)
		frappe.db.commit()


def disable_erpnext_auto_reorder():
	"""The app's reorder engine replaces ERPNext's own, which reads the same Item Reorder rules.

	With both switched on every shortage would get two Material Requests, and ERPNext's
	copy carries no auto-generated flag and skips the duplicate guard.
	"""
	if frappe.db.get_single_value("Stock Settings", "auto_indent"):
		frappe.db.set_single_value("Stock Settings", "auto_indent", 0)
		frappe.db.commit()


def ensure_item_attributes():
	"""Create the colour and size values used by apparel item variants."""
	# value -> abbreviation; ERPNext builds variant item codes from the abbreviations
	for attribute_name, values in {
		"Colour": {"Black": "BLA", "Blue": "BLU", "Green": "GRE", "Red": "RED", "White": "WHI"},
		"Size": {"Extra Small": "XS", "Small": "S", "Medium": "M", "Large": "L", "Extra Large": "XL"},
	}.items():
		attribute = frappe.db.exists("Item Attribute", attribute_name)
		if attribute:
			continue
		frappe.get_doc(
			{
				"doctype": "Item Attribute",
				"attribute_name": attribute_name,
				"item_attribute_values": [
					{"attribute_value": value, "abbr": abbr} for value, abbr in values.items()
				],
			}
		).insert(ignore_permissions=True)
	frappe.db.commit()


def ensure_warehouse_tree():
	"""Create the operational warehouse groups for each existing company."""
	for company in frappe.get_all("Company", pluck="name"):
		root = frappe.db.get_value("Warehouse", {"company": company, "is_group": 1, "parent_warehouse": ""}, "name")
		if not root:
			continue
		for warehouse_name in ["Stores", "Work In Progress", "Finished Goods", "Goods In Transit"]:
			if frappe.db.exists("Warehouse", {"warehouse_name": warehouse_name, "company": company}):
				continue
			frappe.get_doc(
				{
					"doctype": "Warehouse",
					"warehouse_name": warehouse_name,
					"company": company,
					"parent_warehouse": root,
					"is_group": 0,
				}
			).insert(ignore_permissions=True)
	frappe.db.commit()


def install_apparel_metadata():
	"""Create all custom fields and core apparel metadata needed by the workflow."""
	ensure_custom_field(
		"Item",
		"custom_season",
		"Link",
		"Season",
		options="Season",
		insert_after="stock_uom",
	)
	ensure_custom_field(
		"Item",
		"custom_shrinkage_percentage",
		"Float",
		"Shrinkage Percentage",
		insert_after="inspection_required_before_delivery",
	)
	ensure_custom_field(
		"Batch",
		"custom_dye_lot_number",
		"Data",
		"Dye Lot Number",
		insert_after="disabled",
	)
	ensure_custom_field(
		"Batch",
		"custom_roll_length_meters",
		"Float",
		"Roll Length Meters",
		insert_after="custom_dye_lot_number",
	)
	ensure_custom_field(
		"Stock Entry",
		"custom_production_order_ref",
		"Link",
		"Production Order Ref",
		options="Work Order",
		insert_after="stock_entry_type",
	)
	ensure_custom_field(
		"Stock Entry",
		"custom_wastage_scrap_qty",
		"Float",
		"Wastage / Scrap Qty",
		insert_after="custom_production_order_ref",
	)
	ensure_custom_field(
		"Item Reorder",
		"custom_dynamic_lead_time_days",
		"Float",
		"Dynamic Lead Time Days",
		insert_after="warehouse",
	)
	ensure_custom_field(
		"Item Reorder",
		"custom_safety_stock_qty",
		"Float",
		"Safety Stock Qty",
		insert_after="custom_dynamic_lead_time_days",
	)
	ensure_custom_field(
		"Item Reorder",
		"custom_daily_usage",
		"Float",
		"Daily Usage",
		insert_after="custom_safety_stock_qty",
	)
	ensure_custom_field(
		"Material Request",
		"custom_generated_by",
		"Select",
		"Generated By",
		options="Manual\nAuto-Reorder Script",
		insert_after="material_request_type",
	)
	ensure_custom_field(
		"Material Request",
		"custom_auto_generated",
		"Check",
		"Auto Generated",
		insert_after="custom_generated_by",
		read_only=1,
	)
	ensure_custom_field(
		"Pick List",
		"last_scanned_warehouse",
		"Link",
		"Last Scanned Warehouse",
		options="Warehouse",
		insert_after="scan_barcode",
		read_only=1,
	)
	ensure_supplier_scorecard_doctype()
	ensure_supplier_performance_dashboard()
	ensure_supplier_performance_page()
	ensure_supplier_performance_workspace_link()
	ensure_item_attributes()
	disable_erpnext_auto_reorder()
	ensure_warehouse_tree()


def after_migrate():
	"""Run after app migration to ensure all custom metadata is present."""
	try:
		install_apparel_metadata()
		doc = frappe.get_doc("DocType", "Item")
		if not doc.fields:
			return
		frappe.clear_cache()
	except Exception:
		frappe.log_error("Apparel Track setup failed on migration")
		raise
