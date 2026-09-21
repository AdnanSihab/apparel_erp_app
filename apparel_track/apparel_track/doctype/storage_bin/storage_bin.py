# Copyright (c) 2026, Adnan and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class StorageBin(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		barcode_qr_code: DF.Data | None
		bin_id: DF.Data | None
		current_item: DF.Link | None
		max_capacity: DF.Float
		warehouse: DF.Link | None
	# end: auto-generated types

	_DOCTYPE_NAME = "Storage Bin"
