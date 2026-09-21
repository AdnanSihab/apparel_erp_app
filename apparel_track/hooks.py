app_name = "apparel_track"
app_title = "Apparel Track"
app_publisher = "Adnan"
app_description = "Optimizing Inventory Tracking and the Reorder Process in an Apparel Supply Chain."
app_email = "adnan.al.sayeed.sihab@gmail.com"
app_license = "mit"

# Apps
# ------------------

required_apps = ["frappe/erpnext"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "apparel_track",
# 		"logo": "/assets/apparel_track/logo.png",
# 		"title": "Apparel Track",
# 		"route": "/apparel_track",
# 		"has_permission": "apparel_track.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/apparel_track/css/apparel_track.css"
app_include_js = "/assets/apparel_track/js/apparel_track.js"

# include js, css files in header of web template
# web_include_css = "/assets/apparel_track/css/apparel_track.css"
# web_include_js = "/assets/apparel_track/js/apparel_track.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "apparel_track/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "apparel_track/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "apparel_track.utils.jinja_methods",
# 	"filters": "apparel_track.utils.jinja_filters"
# }

# Installation
# ------------

after_install = "apparel_track.apparel_track.custom_field_setup.setup_apparel_customizations"

# Uninstallation
# ------------

# before_uninstall = "apparel_track.uninstall.before_uninstall"
# after_uninstall = "apparel_track.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "apparel_track.utils.before_app_install"
# after_app_install = "apparel_track.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "apparel_track.utils.before_app_uninstall"
# after_app_uninstall = "apparel_track.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "apparel_track.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "apparel_track.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Stock Entry": {
		"on_submit": "apparel_track.apparel_track.stock_automation.process_inventory_on_submit",
	},
	"Purchase Receipt": {
		"on_submit": "apparel_track.apparel_track.stock_automation.on_purchase_receipt_submit",
	},
	"Item": {
		"validate": "apparel_track.apparel_track.reorder_engine.update_item_reorder_levels",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"apparel_track.apparel_track.tasks.daily_reorder_check",
	],
}

after_migrate = "apparel_track.apparel_track.setup.after_migrate"

# Testing
# -------

# before_tests = "apparel_track.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "apparel_track.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
	# lets a Storage Bin barcode be scanned like a warehouse, without editing ERPNext core
	"erpnext.stock.utils.scan_barcode": "apparel_track.apparel_track.barcode.scan_barcode",
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "apparel_track.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["apparel_track.utils.before_request"]
# after_request = ["apparel_track.utils.after_request"]

# Job Events
# ----------
# before_job = ["apparel_track.utils.before_job"]
# after_job = ["apparel_track.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"apparel_track.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
export_python_type_annotations = True

# Require all whitelisted methods to have type annotations
require_type_annotated_api_methods = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

