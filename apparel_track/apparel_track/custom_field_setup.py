# Copyright (c) 2026, Adnan and contributors
# For license information, please see license.txt

import frappe


def install_custom_fields():
	"""Backwards-compatible helper for adding custom Apparel Track fields."""
	from apparel_track.apparel_track.setup import install_apparel_metadata

	install_apparel_metadata()


def setup_apparel_customizations():
	"""Entry point called from hooks to ensure custom fields are installed."""
	install_custom_fields()
