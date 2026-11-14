import unittest
from unittest.mock import patch

from desk import notes
from desk.clock import DAY, HOUR
from desk.desk import Desk, Plan


class BeforeWeekendWaitingCapTest(unittest.TestCase):
    def setUp(self):
        places = [{"id": name, "lat": 60, "lon": 25} for name in ("A", "B")]
        roads = [{"from": "A", "to": "B", "minutes": 60, "km": 70}]
        self.desk = Desk(8, {"before_weekend_waiting_cap": True}, {"places": places, "roads": roads},
                         [], 4 * DAY + 10 * HOUR, 10 * DAY)
        def stop(place):
            return {"placeId": place, "hours": None, "privateAddress": False, "window": {"from": 0, "to": 9 * DAY}}
        self.leg = {"pickup": stop("A"), "delivery": stop("B"), "car": {"electric": False, "premium": False}}
        self.desk.books.requests["new"] = {"id": "new", "arrivedAt": self.desk.now, "respondBy": 10 * DAY}

    def waiting(self, name, until):
        self.desk.books.orders[name] = {"id": name, "legs": [self.leg], "deliveredAt": [None],
                                        "deadline": until + HOUR, "lastPickupAt": until}

    def full(self):
        self.desk.books.unquoted = ["new"]
        with patch.object(self.desk, "prices", return_value=None) as prices:
            self.desk.quote_requests()
        return prices.call_args.args[1]

    def test_first_friday_filters_only_stage_zero_monday_pickups(self):
        self.desk.set["max_waiting"] = 1
        self.waiting("car", 7 * DAY - 1)
        self.assertTrue(self.full())
        self.waiting("car", 7 * DAY)
        self.assertFalse(self.full())
        self.assertEqual(self.desk.load(), 1)
        self.desk.facts["car"] = notes.Facts(deliver_by=7 * DAY)
        self.assertTrue(self.full())  # a one-hour drive requires pickup on Sunday
        self.desk.facts["car"] = notes.Facts(deliver_by=self.desk.now - HOUR)
        self.assertGreater(self.desk.stage(self.desk.books.orders["car"])[0], 0)
        self.assertTrue(self.full())
        self.desk.facts.clear()
        for day in (3, 5, 7):
            self.desk.now = day * DAY + 10 * HOUR
            with self.subTest(day=day):
                self.assertTrue(self.full())
        self.desk.now = 4 * DAY + 10 * HOUR
        self.desk.set["before_weekend_waiting_cap"] = False
        self.assertTrue(self.full())

    def test_pending_quotes_and_off_app_orders(self):
        self.desk.set.update(max_waiting=2, pair_hold=[30, 10])
        self.waiting("held", 7 * DAY)
        self.waiting("monday", 7 * DAY)
        self.waiting("friday", 4 * DAY + 20 * HOUR)
        self.desk.judging = {"a", "b"}
        self.desk.plans["a"] = {"next_day": Plan(0.85, 0.96, 5000, 7 * DAY)}
        with patch.object(self.desk, "waits_for_partner", side_effect=lambda o: o["id"] == "held"):
            self.assertTrue(self.full())  # one Friday car plus two half-orders
            self.assertEqual(self.desk.load(), 3)
            self.assertAlmostEqual(self.desk.due_now[7], 2.6)
            self.desk.judging.remove("b")
            self.assertFalse(self.full())

    def test_twenty_urgent_orders_still_close_admission(self):
        for n in range(59):
            self.waiting(f"future-{n}", 7 * DAY + HOUR)
        for n in range(19):
            self.waiting(f"due-{n}", self.desk.now + 2 * HOUR)
        self.assertEqual(self.desk.urgent(), 19)
        self.assertFalse(self.full())
        self.waiting("twentieth", self.desk.now + 2 * HOUR)
        self.assertEqual(self.desk.urgent(), 20)
        self.assertTrue(self.full())
