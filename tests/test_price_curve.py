"""Compare the prepared grid with the published scalar probability formulas."""
import math
import unittest

from desk.desk import MARKUPS, SETTINGS
from desk.market import EventMarket, Market, RegimeMarket, sigmoid


class PriceCurveTest(unittest.TestCase):
    def test_grid_with_learning_day_changes_and_an_outage(self):
        for kind in (Market, EventMarket, RegimeMarket):
            state = kind(8, tilt=SETTINGS["tilt"], places=SETTINGS["places"], dealer_sd=0.3,
                         minutes={("helsinki", "turku"): 120}, regions={"helsinki": {"helsinki"}})
            for index, minute in enumerate((470, 500, 1069, 1081, 1940, 3380)):
                request = {"id": str(index), "dealerId": "A", "arrivedAt": minute - 15,
                           "legs": [{"pickup": {"placeId": "helsinki"}, "delivery": {"placeId": "turku"}}]}
                trust = index * 5
                if type(state) is Market:
                    state.outage = (minute // 1440, {"helsinki"}, 1.7)
                for later in (False, True):
                    curve = state.price_curve(request, trust, later, minute)
                    for markup in MARKUPS:
                        base = state.base(request, markup, trust, later)
                        if isinstance(state, EventMarket):
                            expected = sum(w * sigmoid((level + base) / flat) for w, level, flat in state.asked[1])
                        elif isinstance(state, RegimeMarket):
                            expected = sum(w * sigmoid((k[1] + base) / math.sqrt(1 + math.pi * k[2] / 8))
                                           for w, k in zip(state.weights(minute), state.kinds))
                        else:
                            doubt = state.var + state.of_dealer(request)[1] + sum(
                                belief[1] * weight ** 2 for belief, weight in state.of_week(request))
                            expected = sigmoid(state.score(request, markup, trust, later, minute) / math.sqrt(1 + math.pi * doubt / 8))
                        self.assertEqual(curve(markup), expected)
                        self.assertEqual(state.chance(request, markup, trust, later, minute), expected)
                state.learn(request, 1.52, trust, False, index % 2 == 0, minute // 1440, minute)


if __name__ == "__main__":
    unittest.main()
