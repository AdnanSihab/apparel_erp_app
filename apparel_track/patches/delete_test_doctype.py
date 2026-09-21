import frappe


def execute():
	"""Remove the empty "test" scaffold DocType that was left in the Apparel Track module."""
	if frappe.db.exists("DocType", "test") and frappe.db.get_value("DocType", "test", "module") == "Apparel Track":
		frappe.delete_doc("DocType", "test", force=True, ignore_permissions=True)
