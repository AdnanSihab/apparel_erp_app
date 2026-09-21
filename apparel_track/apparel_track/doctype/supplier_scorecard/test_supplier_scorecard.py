# Copyright (c) 2026, Adnan and contributors
# For license information, please see license.txt

from frappe.tests import UnitTestCase

from apparel_track.apparel_track.doctype.supplier_scorecard.supplier_scorecard import SupplierScorecard


class UnitTestSupplierScorecard(UnitTestCase):
	def test_reliability_score(self):
		score = SupplierScorecard.get_reliability_score
		self.assertEqual(score(7, 14), 50)
		self.assertEqual(score(7, 1.667), 100)  # faster than promised is capped
		self.assertEqual(score(7, 0), 100)  # delivered on the order date
		self.assertEqual(score(0, 5), 0)  # no promise recorded yet
