import unittest
from collections import Counter
from unittest.mock import Mock

from desk import notes
from desk.clock import DAY, LAST_REQUEST
from desk.desk import Desk, SETTINGS


class TrustDeadlineTest(unittest.TestCase):
    def test_noted_order_keeps_real_pickup_cutoff_after_quote(self):
        desk = object.__new__(Desk)
        desk.facts = {"r": notes.Facts(deliver_by=1000)}
        desk.now, desk.ends_at = 500, 14000
        desk.last_pickup = Mock(side_effect=lambda order, deadline: deadline - 80)
        leg = {"pickup": {"hours": None}, "delivery": {"hours": None}}
        order = {"id": "r", "deadline": 1200, "lastPickupAt": 1100, "legs": [leg]}
        self.assertEqual(desk.stage(order), (0, 920))

    def test_future_trust_cost_ends_after_last_dealer_request(self):
        desk = object.__new__(Desk)
        desk.now, desk.set = 600, SETTINGS.copy()
        desk.books = Mock(trust=Counter({"D01": 20}), dealer_requests=Counter())
        self.assertGreater(desk.late_cost("D01", 10000), 6000)
        self.assertEqual(desk.late_cost("D01", 10000, deadline=7*1440), 6000)

    def test_after_close_rescue_uses_the_effective_deadline(self):
        desk = object.__new__(Desk)
        desk.now = 0
        desk.set = {**SETTINGS, "trust_after_close": True}
        desk.short_days = set()
        desk.facts = {}
        desk.last_pickup = Mock(side_effect=lambda order, deadline: deadline - 60)
        desk.late_cost = Mock(return_value=500)
        desk.best_fee = Mock(return_value="plan")
        leg = {"pickup": {"window": {"from": 0}, "hours": None}, "delivery": {"hours": None}}
        request = {"id": "r", "dealerId": "D", "legs": [leg], "referenceFeeCents": 1000}
        option = {"kind": "next_day", "deadline": LAST_REQUEST, "listPriceCents": 2000}
        self.assertIsNone(desk.plan(request, option, 0, delivery_horizon=True))
        self.assertEqual(desk.plan(request, option, 0), "plan")  # a normal real option is unaffected
        desk.facts["r"] = notes.Facts(ready_at=DAY)
        self.assertEqual(desk.plan(request, option, 0, delivery_horizon=True), "plan")
        desk.late_cost.assert_called_with("D", 2000, LAST_REQUEST + DAY)
        desk.facts["r"] = notes.Facts(ready_at=DAY, deliver_by=LAST_REQUEST)
        self.assertIsNone(desk.plan(request, option, 0, delivery_horizon=True))
        self.assertIsNone(desk.plan({**request, "legs": [leg, leg]}, option, 0, delivery_horizon=True))
