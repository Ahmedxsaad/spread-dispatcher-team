import unittest
from unittest.mock import patch

from desk.clock import DAY, HOUR
from desk.desk import Desk, Plan


class OpeningTwoHoursTest(unittest.TestCase):
    def quote(self, arrived, config, *, level=8, drive=90, due=DAY):
        world_map = {"places": [], "roads": [{"from": "A", "to": "B", "minutes": drive, "km": 100}]}
        request = {"id": "R", "dealerId": "D", "arrivedAt": arrived, "respondBy": arrived + 15,
                   "legs": [{"pickup": {"placeId": "A"}, "delivery": {"placeId": "B"}}],
                   "options": [{"kind": "same_day", "listPriceCents": 30000}]}
        desk = Desk(level, config, world_map, [], arrived + 10, 10 * DAY)
        desk.quote_requests()
        with patch.object(desk, "plan", return_value=Plan(0.85, 0.95, 15000, due)):
            return desk.prices(request, False)

    def test_only_first_monday_arrivals_before_ten_at_level_eight(self):
        on = {"opening_two_hours": True}
        before = 10 * HOUR - 1
        self.assertEqual(self.quote(before, on), self.quote(before, {"greed": 1.03}))
        self.assertNotEqual(self.quote(before, on), self.quote(before, {}))
        for minute in (10 * HOUR, 10 * HOUR + 1, DAY + 9 * HOUR, 7 * DAY + 9 * HOUR):
            with self.subTest(minute=minute):
                self.assertEqual(self.quote(minute, on), self.quote(minute, {}))
        self.assertEqual(self.quote(before, on, level=7), self.quote(before, {}, level=7))

    def test_existing_overrides_keep_their_priority(self):
        arrived = 9 * HOUR
        for override, extra in (({"greed_short": [90, 1.10]}, {}),
                                ({"greed_long": [90, 1.10]}, {}),
                                ({"greed_later": 1.10}, {"due": 7 * DAY})):
            with self.subTest(override=override):
                self.assertEqual(self.quote(arrived, {"opening_two_hours": True, **override}, **extra),
                                 self.quote(arrived, override, **extra))
        adjusted = {"greed_load": [0.002, 4]}
        self.assertEqual(self.quote(arrived, {"opening_two_hours": True, **adjusted}),
                         self.quote(arrived, {"greed": 1.03, **adjusted}))
