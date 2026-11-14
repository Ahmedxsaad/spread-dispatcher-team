import unittest
from collections import Counter
from unittest.mock import Mock

from desk.desk import Desk, Plan, SETTINGS


class RescueSafetyTest(unittest.TestCase):
    def quote(self, baseline, rescued):
        desk = object.__new__(Desk)
        desk.level = 8
        desk.set = {**SETTINGS, "trust_rescue_ordinary_safety": True}
        desk.facts, desk.plans, desk.asked, desk.tally = {}, {}, {}, Counter()
        desk.books = Mock(trust=Counter({"dealer": 5}))
        desk.trust_point, desk.pending = Mock(return_value=0), Mock(return_value=0)
        desk.plan = Mock(side_effect=lambda r, o, t, retry: rescued if retry else baseline)
        desk.limit_now = desk.limit_early = desk.limit_later = 1000
        desk.due_now, desk.minutes = Counter(), {("a", "b"): 40}
        desk.journal = None
        desk.market = Mock()
        desk.market.price_curve.return_value = lambda m: 0.75
        req = {"id":"r","dealerId":"dealer","respondBy":500,
               "legs":[{"pickup":{"placeId":"a"}, "delivery":{"placeId":"b"}}],
               "options":[{"kind":"fast","listPriceCents":10000}]}
        return desk.prices(req,False), desk.plan.call_count

    def test_only_new_offers_must_clear_the_ordinary_chance(self):
        weak = Plan(1, .83, 4000, 2000, 4000)
        safe = Plan(1, .84, 4000, 2000, 4000)
        self.assertEqual(self.quote(None, weak), ({"fast":30000}, 2))
        self.assertLess(self.quote(None, safe)[0]["fast"], 30000)
        quote, calls = self.quote(weak, None)
        self.assertLess(quote["fast"], 30000)
        self.assertEqual(calls, 1)
