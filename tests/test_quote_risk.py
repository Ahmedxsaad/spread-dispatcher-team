import unittest

from desk.clock import DAY
from desk.desk import Desk, Plan
from desk.notes import Facts


class QuoteRiskTest(unittest.TestCase):
    def quote(self, enabled=True, *, level=8, premium=False, private=False, charge=False, note=False, guarded=False):
        places = [{"id": name, "lat": 60.0, "lon": 24.0} for name in ("from", "to")]
        roads = [{"from": "from", "to": "to", "minutes": 180, "km": 280}]
        d = Desk(level, {"ordinary_quote_risk_half": enabled}, {"places": places, "roads": roads}, [], 540, 10 * DAY)
        d.due_now.clear()
        d.limit_now = d.limit_early = d.limit_later = 0.5 if guarded else 100
        r = {"id": "req", "dealerId": "dealer", "respondBy": 555,
             "legs": [{"car": {"premium": premium, "electric": charge, "chargePercent": 10},
                       "pickup": {"placeId": "from", "privateAddress": private}, "delivery": {"placeId": "to", "privateAddress": False}}],
             "options": [{"kind": kind, "listPriceCents": 10000} for kind in ("same_day", "next_day")]}
        original = {"same_day": Plan(0.85, 0.9, 9500, 1200, 5000), "next_day": Plan(0.95, 0.95, 9500, 2400, 5000)}
        d.plan = lambda req, option, at: original[option["kind"]]
        if note:
            d.facts["req"] = Facts(manual=True)
        prices = d.prices(r, full=False)
        if not guarded:
            self.assertEqual(d.plans["req"], original)
        return prices

    def test_only_eligible_options_change_price_and_plans_stay_intact(self):
        reference = self.quote(enabled=False)
        adjusted = self.quote()
        self.assertLess(adjusted["same_day"], reference["same_day"])
        self.assertEqual(adjusted["next_day"], reference["next_day"])
        for args in ({"level": 7}, {"premium": True}, {"private": True}, {"charge": True}, {"note": True}, {"guarded": True}):
            with self.subTest(args=args):
                self.assertEqual(self.quote(**args), self.quote(enabled=False, **args))
