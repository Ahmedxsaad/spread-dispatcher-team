import unittest
from types import SimpleNamespace

from desk.desk import Desk, SETTINGS


class LateAllowanceTest(unittest.TestCase):
    def test_exact_spent_allowance_and_both_neighbors(self):
        desk = object.__new__(Desk)
        desk.set = {**SETTINGS, "guard_zero": True}
        desk.now = 4 * 1440
        desk.drop_days = {1}
        desk.first_day = 0
        desk.urgent = lambda: 0
        desk.books = SimpleNamespace(won_count=239, late_count=21)
        self.assertEqual(desk.day_limit(), 0.0)
        self.assertEqual(desk.day_limit(later=True), 0.0)
        desk.books.late_count = 20
        self.assertAlmostEqual(desk.day_limit(), 10)
        desk.books.late_count = 22
        self.assertAlmostEqual(desk.day_limit(), -10)
        desk.books.won_count = 367
        self.assertAlmostEqual(desk.day_limit(), 0.2)
