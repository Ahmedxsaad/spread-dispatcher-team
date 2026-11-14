"""Snapshot recovery must assign each unfinished car to the gig still carrying it."""
import unittest
from copy import deepcopy

from desk.clock import DAY
from desk.desk import Desk


class RecoveryTest(unittest.TestCase):
    def setUp(self):
        towns = ("A", "B")
        roads = [{"from": a, "to": b, "minutes": int(a != b) * 60, "km": int(a != b) * 70}
                 for a in towns for b in towns]
        self.desk = Desk(8, {}, {"roads": roads, "places": [{"id": a, "lat": 60, "lon": 25} for a in towns]},
                         [], 600, ends_at=10 * DAY)
        self.orders = []

    def order(self, name, delivered):
        def stop(town):
            return {"placeId": town, "hours": None, "privateAddress": False, "window": {"from": 500, "to": 2 * DAY}}

        leg = {"pickup": stop("A"), "delivery": stop("B"), "car": {"electric": False, "premium": False, "chargePercent": None}}
        legs = [deepcopy(leg) for _ in delivered]
        self.desk.books.requests[name] = {"id": name, "referenceFeeCents": 10000, "legs": legs, "dealerId": "dealer",
                                          "options": [{"kind": "next_day", "listPriceCents": 11000}]}
        order = {"id": name, "dealerId": "dealer", "option": "next_day", "priceCents": 10000, "deadline": 2 * DAY,
                 "lastPickupAt": 2 * DAY - 60, "legs": legs, "deliveredAt": delivered,
                 "status": "delivered" if all(at is not None for at in delivered) else "moving"}
        self.orders.append(order)
        return order

    def gig(self, name, keys, status="working"):
        return {"id": name, "postedAt": 500, "status": status, "audience": {}, "feeCents": 13000,
                "driverId": None if status == "open" else "driver", "schedule": [{"at": 500, "feeCents": 13000}],
                "stops": [{"kind": kind, "orderId": order, "leg": leg}
                          for order, leg in keys for kind in ("pickup", "delivery")]}

    def sync(self, gigs):
        self.desk.sync({"orders": deepcopy(self.orders), "gigs": gigs, "openRequests": [], "now": 600})

    def event(self, kind, at, gig, order, leg, **fields):
        self.desk.on_event({"seq": self.desk.last_seq + 1, "kind": kind, "at": at, "gigId": gig, "orderId": order,
                            "leg": leg, **fields})

    def test_failed_pair_member_is_reposted_after_recovery(self):
        self.order("failed", [None])
        self.order("partner", [None])
        pair = self.gig("pair", [("failed", 0), ("partner", 0)])
        self.event("visit_failed", 580, "pair", "failed", 0, reason="no_plates")
        self.sync([pair])
        self.assertEqual(self.desk.books.carrier, {("partner", 0): "pair"})
        self.event("delivered", 650, "pair", "partner", 0, placeId="B")
        self.assertEqual(self.desk.books.carrier, {})
        posts = [a for a in self.desk.decide(650) if a["type"] == "post"]
        self.assertEqual(len(posts), 1)
        pickup = posts[0]["stops"][0]
        self.assertEqual((pickup["orderId"], pickup["leg"], pickup["withPlates"]), ("failed", 0, True))

    def test_failed_car_reassigned_to_another_gig_in_any_snapshot_order(self):
        self.order("retry", [None])
        self.order("partner", [None])
        pair = self.gig("original", [("retry", 0), ("partner", 0)])
        replacement = self.gig("replacement", [("retry", 0)], "booked")
        self.event("visit_failed", 580, "original", "retry", 0, reason="closed")
        for gigs in ([pair, replacement], [replacement, pair]):
            with self.subTest(first=gigs[0]["id"]):
                self.sync(gigs)
                self.assertEqual(self.desk.books.carrier, {("partner", 0): "original", ("retry", 0): "replacement"})

    def test_delivered_leg_of_trade_in_does_not_regain_a_carrier(self):
        self.order("trade", [550, None])
        pair = self.gig("trade-gig", [("trade", 0), ("trade", 1)])
        self.sync([pair])
        self.assertEqual(self.desk.books.carrier, {("trade", 1): "trade-gig"})
        self.assertEqual(self.desk.books.gigs["trade-gig"].legs, [("trade", 1)])
        self.event("delivered", 650, "trade-gig", "trade", 1, placeId="B")
        self.assertEqual(self.desk.books.done, {"trade"})
        self.assertEqual(self.desk.books.gigs, {})
        self.assertEqual(self.desk.books.carrier, {})

    def test_sync_keeps_all_live_cars_and_ignores_finished_gigs(self):
        self.order("first", [None])
        self.order("second", [None])
        self.order("done", [550])
        keys = [("first", 0), ("second", 0)]
        for status in ("open", "booked", "working"):
            with self.subTest(status=status):
                self.sync([self.gig("active", keys, status), self.gig("ended", [("done", 0)], "done")])
                self.assertEqual(self.desk.books.carrier, dict.fromkeys(keys, "active"))
                self.assertEqual(self.desk.books.first_posted["done"], 500)
                self.assertEqual(self.desk.books.gigs["active"].legs, keys)
                self.assertEqual(self.desk.books.gigs["active"].status, status)
                self.assertEqual(set(self.desk.books.gigs), {"active"})
