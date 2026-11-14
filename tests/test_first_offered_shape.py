import json
import tempfile
import unittest
from pathlib import Path

from desk.desk import Desk, MARKUPS, Plan, euros


class FirstOfferedShapeTest(unittest.TestCase):
    places = [{"id": "a", "lat": 60, "lon": 25}, {"id": "b", "lat": 61, "lon": 26}]
    roads = [{"from": "a", "to": "b", "minutes": 100, "km": 120}]
    options = [
        {"kind": "same_day", "deadline": 1000, "listPriceCents": 4500},
        {"kind": "next_day", "deadline": 2400, "listPriceCents": 3000},
        {"kind": "within_3_days", "deadline": 5200, "listPriceCents": 2500},
    ]
    request = {"id": "r", "dealerId": "d", "note": None, "arrivedAt": 500, "respondBy": 515,
               "legs": [{"pickup": {"placeId": "a"}, "delivery": {"placeId": "b"}}], "options": options}

    def desk(self, **config):
        return Desk(8, config, {"places": self.places, "roads": self.roads}, [], 500, 14280)

    def test_rejected_first_candidate_and_two_subsequent_offers_survive_restart(self):
        for use_offers in (False, True):
            with self.subTest(first_offered=use_offers), tempfile.TemporaryDirectory() as directory:
                config = {"dealer_shape": True, "dealer_shape_first_offered": use_offers}
                desk = self.desk(**config)
                # The fastest candidate reaches the pricing grid but is unprofitable. The later two pass.
                costs = {"same_day": 50000, "next_day": 1800, "within_3_days": 1400}
                desk.plan = lambda req, opt, at: Plan(1.0, .99, costs[opt["kind"]], opt["deadline"])
                journal = Path(directory) / "week.jsonl"
                empty = {"orders": [], "gigs": [], "openRequests": [], "now": 500}
                desk.rejoin([], empty, journal)
                self.addCleanup(desk.journal.close)
                arrived = {"kind": "price_request", "seq": 0, "at": 500, "request": self.request}
                desk.on_event(arrived)
                actions = desk.decide(501, quotes_only=True)
                self.assertEqual(len(actions), 1)
                action = actions[0]
                self.assertEqual((action["type"], action["requestId"]), ("quote", "r"))
                self.assertEqual(list(action["prices"]), ["next_day", "within_3_days"])

                # Independent scalar calculation takes an ordinary shaped request whose first
                # option is the required feature source, including the cheap-list-price boundary.
                oracle = self.desk(dealer_shape=True).market
                feature_request = {**self.request, "options": self.options[1:] if use_offers else self.options}
                for option in self.options[1:]:
                    kind, price = option["kind"], option["listPriceCents"]
                    _, markup = max((oracle.chance(feature_request, m, 0, True, 515) * (m * price - costs[kind]), m) for m in MARKUPS)
                    self.assertEqual(action["prices"][kind], euros(markup * desk.set["greed"] * price))

                # Journal fee keys also exist in the pre-change three-field journal format.
                entry = json.loads(journal.read_text().splitlines()[-1])
                self.assertEqual(len(entry["asked"]), 3)
                self.assertEqual(set(entry["fees"]), set(action["prices"]))
                desk.journal.close()
                # An older journal or external JSON writer may order these keys differently.
                entry["fees"] = dict(reversed(list(entry["fees"].items())))
                journal.write_text(json.dumps(entry) + "\n")
                pending = self.desk(**config)
                pending.rejoin([arrived], {**empty, "openRequests": [self.request]}, journal)
                self.addCleanup(pending.journal.close)
                picked = self.options[-1]
                won = {"seq": 1, "at": 515, "kind": "order_won", "order": {
                    "id": "r", "dealerId": "d", "option": picked["kind"],
                    "priceCents": action["prices"][picked["kind"]], "status": "waiting"}}
                desk.on_event(won)
                pending.on_event(won)
                restart = self.desk(**config)
                restart.rejoin([arrived, won], {**empty, "orders": [won["order"]], "now": 515}, journal)
                self.addCleanup(restart.journal.close)
                oracle.learn(feature_request, won["order"]["priceCents"] / picked["listPriceCents"], 0, True, True, 0, 515)
                for market in (desk.market, pending.market, restart.market):
                    self.assertEqual((market.mean, market.var, market.parts), (oracle.mean, oracle.var, oracle.parts))

    def test_old_journal_without_fees_uses_request_context(self):
        arrived = {"kind": "price_request", "seq": 0, "at": 500, "request": self.request}
        lost = {"kind": "order_lost", "seq": 1, "at": 515, "requestId": "r"}
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "week.jsonl"
            journal.write_text(json.dumps({"request": "r", "asked": [1.4, 2, True]}) + "\n")
            desk = self.desk(dealer_shape_first_offered=True)
            desk.rejoin([arrived, lost], {"orders": [], "gigs": [], "openRequests": [], "now": 515}, journal)
            self.addCleanup(desk.journal.close)
            oracle = self.desk(dealer_shape=True).market
            oracle.learn(self.request, 1.4, 2, True, False, 0, 515)
            self.assertEqual(desk.market.mean, oracle.mean)

    def test_replacement_decline_and_exploration_do_not_learn_from_superseded_plan(self):
        arrived = {"kind": "price_request", "seq": 0, "at": 500, "request": self.request}
        lost = {"kind": "order_lost", "seq": 1, "at": 515, "requestId": "r"}
        for config in ({"max_waiting": 0}, {"explore": True}):
            with self.subTest(config=config), tempfile.TemporaryDirectory() as directory:
                journal = Path(directory) / "week.jsonl"
                journal.write_text(json.dumps({"request": "r", "asked": [1.4, 2, True], "fees": {"next_day": 1.0}}) + "\n")
                cfg = {**config, "dealer_shape_first_offered": True}
                desk = self.desk(**cfg)
                empty = {"orders": [], "gigs": [], "openRequests": [], "now": 500}
                desk.rejoin([arrived], {**empty, "openRequests": [self.request]}, journal)
                initial = desk.market.mean
                published = desk.decide(501, quotes_only=True)
                self.assertEqual(len(published), 1)
                self.assertEqual(published[0]["requestId"], "r")
                self.assertNotIn("r", desk.asked)
                desk.journal.close()
                desk.on_event(lost)
                recovered = self.desk(**cfg)
                recovered.rejoin([arrived, lost], empty, journal)
                self.addCleanup(recovered.journal.close)
                self.assertEqual((desk.market.mean, recovered.market.mean), (initial, initial))


if __name__ == "__main__":
    unittest.main()
