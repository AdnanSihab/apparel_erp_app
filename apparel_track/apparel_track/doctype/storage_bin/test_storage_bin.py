# Copyright (c) 2026, Adnan and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]



class IntegrationTestStorageBin(IntegrationTestCase):
	"""
	Integration tests for StorageBin.
	Use this class for testing interactions between multiple components.
	"""

	def test_barcode_resolves_to_warehouse(self):
		warehouse = frappe.get_all("Warehouse", filters={"is_group": 0}, pluck="name", limit=1)
		if not warehouse:
			self.skipTest("No leaf warehouse is available")

		barcode = "TEST-BIN-BARCODE"
		bin_doc = frappe.get_doc(
			{
				"doctype": "Storage Bin",
				"bin_id": "TEST-BIN",
				"warehouse": warehouse[0],
				"barcode_qr_code": barcode,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("Storage Bin", bin_doc.name, ignore_permissions=True))

		from apparel_track.apparel_track.barcode import scan_barcode

		result = scan_barcode(barcode)

		self.assertEqual(result["warehouse"], warehouse[0])
