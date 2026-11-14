import tempfile
import unittest
from pathlib import Path

from desk.clock import DAY
from desk.desk import Desk, Plan


FRIDAY = 4 * DAY + 16 * 60


def desk(start=0, enabled=True):
    places = [{"id": s, "lat": 60, "lon": 24} for s in ["a", "b"]]
    roads = [{"from": a["id"], "to": b["id"], "minutes": 60, "km": 50} for a in places for b in places]
    # Force the waiting cap. The ordinary quote, market, per-day and urgent checks remain active.
    result = Desk(8, {"friday_capacity": enabled, "max_waiting": 0}, {"places": places, "roads": roads}, [], start, 10 * DAY)
    result.plan = lambda r, o, at: Plan(0.85, r.get("chance", 0.96), r.get("cost", 4000), o["deadline"], 3900)
    return result


def request(key, **kwargs):
    return dict({"id": key, "dealerId": "dealer", "arrivedAt": FRIDAY, "respondBy": FRIDAY + 15,
                 "legs": [{"car": {"premium": False, "electric": False}, "pickup": {"privateAddress": False, "placeId": "a"},
                           "delivery": {"privateAddress": False, "placeId": "b"}}],
                 "options": [{"kind": "next_day", "listPriceCents": 10000, "deadline": 7 * DAY + 1000}]}, **kwargs)


def quote(d, *requests, at=FRIDAY):
    for r in requests:
        d.books.requests[r["id"]] = r
        d.books.unquoted.append(r["id"])
    return {a["requestId"]: a["prices"]["next_day"] for a in d.decide(at, quotes_only=True)}


class FridayCapacityTest(unittest.TestCase):
    def test_four_unique_offers_one_new_offer_per_look(self):
        d = desk()
        result = quote(d, request("risky", chance=0.949), request("first"), request("second"))
        self.assertEqual(result["risky"], 30000)
        self.assertLess(result["first"], 30000)
        self.assertEqual(result["second"], 30000)
        for i in range(3):
            self.assertLess(quote(d, request(str(i)))[str(i)], 30000)
        retry = quote(d, request("first"), request("fifth"))
        self.assertEqual(retry["first"], result["first"])
        self.assertEqual(retry["fifth"], 30000)
        self.assertEqual(len(d.friday_offers), 4)

    def test_safety_and_original_guards(self):
        d = desk()
        late = request("wrong_day")
        late["options"][0]["deadline"] = 5 * DAY + 1000
        other = request("premium")
        other["legs"][0]["car"]["premium"] = True
        low = request("unprofitable", cost=1000000)
        for r in (late, other, low):
            self.assertEqual(quote(d, r)[r["id"]], 30000)
        self.assertEqual(quote(d, request("thursday"), at=FRIDAY - DAY)["thursday"], 30000)
        d.urgent = lambda: d.set["max_urgent"]
        self.assertEqual(quote(d, request("urgent"))["urgent"], 30000)
        d.urgent = lambda: 0
        d.day_limit = lambda **kwargs: 0.5
        self.assertEqual(quote(d, request("overlimit"))["overlimit"], 30000)
        self.assertEqual(d.friday_offers, set())
        self.assertEqual(quote(desk(enabled=False), request("ordinary"))["ordinary"], 30000)

    def test_journal_recovery_and_missing_or_corrupt_journal(self):
        snapshot = {"orders": [], "gigs": [], "openRequests": [], "now": 0}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "world.jsonl"
            d = desk()
            d.rejoin([], snapshot, path)
            quote(d, request("one"))
            d.journal.close()
            snapshot["now"] = FRIDAY
            d = desk(FRIDAY)
            d.rejoin([], snapshot, path)
            self.assertEqual(d.friday_offers, {"one"})
            self.assertLess(quote(d, request("one"), request("two"))["two"], 30000)
            self.assertEqual(len(d.friday_offers), 2)
            d.journal.close()
            for previous in ("", '{"friday_budget_open": true}\n{"broken":'):
                path.write_text(previous)
                d = desk(FRIDAY)
                d.rejoin([], snapshot, path)
                self.assertEqual(quote(d, request("closed"))["closed"], 30000)
                d.journal.close()
