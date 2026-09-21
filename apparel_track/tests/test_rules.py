# Copyright (c) 2026, Adnan and contributors
# For license information, please see license.txt

"""The two formulas the system rests on, tested without a database.

	bench --site apparel-site run-tests --module apparel_track.tests.test_rules
"""

from unittest import TestCase

from apparel_track.apparel_track.doctype.supplier_scorecard.supplier_scorecard import SupplierScorecard
from apparel_track.apparel_track.reorder_engine import calculate_reorder_level


class TestReorderLevelFormula(TestCase):
	"""Equation 6.1: reorder level = lead time demand + safety stock."""

	def test_lead_time_demand_plus_safety_stock(self):
		# 4.5 m a day for 9 days, plus 30 m of safety stock
		self.assertAlmostEqual(calculate_reorder_level(9, 4.5, 30), 70.5)

	def test_no_consumption_leaves_only_safety_stock(self):
		self.assertEqual(calculate_reorder_level(9, 0, 30), 30)

	def test_no_scorecard_yet_means_no_lead_time_demand(self):
		self.assertEqual(calculate_reorder_level(0, 4.5, 30), 30)

	def test_negative_lead_time_is_treated_as_zero(self):
		self.assertEqual(calculate_reorder_level(-3, 4.5, 30), 30)

	def test_slower_supplier_raises_the_level(self):
		promised = calculate_reorder_level(5, 4.5, 30)
		measured = calculate_reorder_level(11, 4.5, 30)
		self.assertGreater(measured, promised)
		self.assertAlmostEqual(measured - promised, 6 * 4.5)


class TestReliabilityScore(TestCase):
	"""Section 8.3: promised / measured lead time, as a percentage capped at 100."""

	score = staticmethod(SupplierScorecard.get_reliability_score)

	def test_late_supplier_scores_below_100(self):
		self.assertAlmostEqual(self.score(6, 8), 75)
		self.assertAlmostEqual(self.score(10, 16), 62.5)

	def test_on_time_supplier_scores_100(self):
		self.assertEqual(self.score(6, 6), 100)

	def test_early_supplier_is_capped_at_100(self):
		self.assertEqual(self.score(6, 2.5), 100)

	def test_same_day_delivery_scores_100(self):
		self.assertEqual(self.score(6, 0), 100)

	def test_no_promise_recorded_scores_0(self):
		self.assertEqual(self.score(0, 8), 0)
