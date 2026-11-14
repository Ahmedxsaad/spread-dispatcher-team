import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from desk.desk import Desk, Plan


class LearnFastestTest(unittest.TestCase):
    def desk(self, **settings):
        desk = Desk(8, {"fast_factor": 1.31, **settings}, {"places": [{"id": "A", "lat": 60, "lon": 25}],
                    "roads": [{"from": "A", "to": "A", "minutes": 0, "km": 0}]}, [], 600, 14280)
        desk.plan = lambda request, option, at: Plan(1., .98, 1500, 900)
        desk.market.chance = lambda *args: .5
        desk.market.learn = Mock()
        return desk

    def request(self, name):
        return {"id": name, "dealerId": "dealer", "respondBy": 615, "arrivedAt": 600,
                "legs": [{"pickup": {"placeId": "A"}, "delivery": {"placeId": "A"}}],
                "options": [{"kind": "same_day", "listPriceCents": 5911},
                            {"kind": "next_day", "listPriceCents": 5023},
                            {"kind": "within_3_days", "listPriceCents": 4417}]}

    def quote(self, desk, name):
        request = self.request(name)
        desk.books.requests[name] = request
        return desk.prices(request, False)

    def test_fastest_uses_first_issued_price_after_rounding_and_fast_factor(self):
        for won in (False, True):
            with self.subTest(won=won):
                desk = self.desk(learn_fastest=True)
                desk.plan = lambda req, op, at: None if op["kind"] == "same_day" else Plan(1., .98, 1500, 900)
                prices = self.quote(desk, "r")
                self.assertEqual(list(prices), ["next_day", "within_3_days"])
                order = {"option": "within_3_days", "priceCents": prices["within_3_days"]} if won else None
                desk.learn("r", order, 615)
                self.assertNotEqual(prices["next_day"] / 5023, prices["within_3_days"] / 4417)
                desk.market.learn.assert_called_once_with(desk.books.requests["r"], prices["next_day"] / 5023,
                                                        0, True, won, 0, 615)

    def test_mixed_journal_recovers_each_quotes_original_learning_rule(self):
        for enabled_at_restart in (False, True):
            with self.subTest(enabled_at_restart=enabled_at_restart), tempfile.TemporaryDirectory() as directory:
                history = io.StringIO()
                expected = []
                for name, enabled, won in [("legacyLoss", False, False), ("legacyWin", False, True),
                                           ("newLoss", True, False), ("newWin", True, True)]:
                    desk = self.desk(learn_fastest=enabled)
                    desk.journal = history
                    prices = self.quote(desk, name)
                    entry = json.loads(history.getvalue().splitlines()[-1])
                    self.assertEqual(len(entry["asked"]), 3)
                    self.assertEqual("fastest_markup" in entry, enabled)
                    markup = entry["asked"][0]
                    order = {"option": "within_3_days", "priceCents": prices["within_3_days"]} if won else None
                    if enabled:
                        markup = prices["same_day"] / 5911
                    elif won:
                        markup = prices["within_3_days"] / 4417
                    desk.learn(name, order, 615)
                    self.assertEqual(desk.market.learn.call_args.args[1], markup)
                    expected.append((name, order, markup))
                file = Path(directory) / "journal"
                file.write_text(history.getvalue())
                restored = self.desk(learn_fastest=enabled_at_restart)
                restored.rejoin([], {"orders": [], "gigs": [], "openRequests": [], "now": 615}, file)
                self.addCleanup(restored.journal.close)
                for name, order, markup in expected:
                    restored.books.requests[name] = self.request(name)
                    restored.learn(name, order, 615)
                    self.assertEqual(restored.market.learn.call_args.args[1], markup)
