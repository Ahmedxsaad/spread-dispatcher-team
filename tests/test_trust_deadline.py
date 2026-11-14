import unittest
from collections import Counter
from unittest.mock import Mock, call

from desk import notes
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

    def test_all_quotes_prices_each_option_once_even_with_rescue_enabled(self):
        desk = object.__new__(Desk)
        desk.level, desk.facts, desk.tally = 8, {}, Counter()
        desk.books = Mock(trust=Counter({"D": 7}))
        desk.pending = Mock(return_value=0)
        desk.trust_point = Mock(return_value=0.0)
        desk.plan = Mock(return_value=None)
        options = [{"kind": "same_day", "listPriceCents": 12000}, {"kind": "next_day", "listPriceCents": 10000}]
        for legs in ([{}], [{}, {}]):
            request = {"id": "r", "dealerId": "D", "legs": legs, "respondBy": 500, "options": options}
            for settings, horizon in [({}, False), ({"trust_all_quotes": True}, True),
                                      ({"trust_all_quotes": True, "trust_rescue": True}, True)]:
                with self.subTest(legs=len(legs), settings=settings):
                    desk.set = {**SETTINGS, **settings}
                    desk.plan.reset_mock()
                    self.assertEqual(desk.prices(request, full=False), {"same_day": 36000})
                    self.assertEqual(desk.plan.call_args_list, [call(request, option, 500, horizon) for option in options])
