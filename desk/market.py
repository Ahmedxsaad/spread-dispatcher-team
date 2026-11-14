"""What dealers accept. The chance that a dealer takes our price is a logistic curve in the log of
the price as the dealer sees it: over the list price, and divided by the dealer's trust, 1% for
each order that we delivered to it on time. The curve's slope and each lane's level hold in every
world (analysis/fit.py). Today's level does not: the world's price level, the day's factor, a
price war or an outage move it. The desk learns it from each quote that wins or loses."""
from __future__ import annotations

import math
from typing import Optional

from .clock import DAY, HOUR, clock
from .model import FITTED

LEVEL_SHIFT = {4: -4.2, 5: -4.2, 6: -4.2, 7: -1.4}  # the competitor is near the list price up to level 6, and 25% above it at level 7, against 40% at level 8


OUTAGE_Z = 4.0  # how sure the detector must be: on 80 exploration weeks, 4 false alarms in 320 ordinary days
OUTAGE_SHIFT = (1.2, 3.0)  # the level inside the region rises by this much, in the curve's units: a backup about 30% dearer than the competitor


class Market:
    def __init__(self, level: int, day_sd: float = 1.3, regions: Optional[dict] = None, outages: bool = True, dealer_sd: float = 0.0, slope_scale: float = 1.0):
        fitted = FITTED["dealer"]
        # Each morning the competitor moves its prices for each dealer by what we won there. So each dealer
        # has a level of its own on top of the day's, learned from that dealer's answers alone.
        self.dealer_sd = dealer_sd  # 0: no level by dealer
        self.dealers: dict[str, list[float]] = {}  # dealer -> [mean, variance] of its own level
        # The outage (from level 6): on one working day, from 08:00 to 18:00, the competitor is down in one region, a
        # town and the places within 80 km. Dealers there pay a backup that is dearer, so they take higher prices from us.
        self.regions = regions if outages and level >= 6 else None  # town -> the places of its region
        self.today: list[tuple[str, float, bool]] = []  # (pickup place, score without the level, won) of today's judged quotes in working hours
        self.outage: Optional[tuple[int, set, float]] = None  # (day, places, shift) once found; a week has one
        self.slope, self.only_later = fitted["slope"] * slope_scale, fitted["only_later"]
        self.pickup, self.delivery = fitted["pickup"], fitted["delivery"]
        self.mean = fitted["level"] + LEVEL_SHIFT.get(level, 0.0)  # our belief about today's level: a mean and a variance
        self.var = fitted["level_sd"] ** 2
        self.day_var = day_sd ** 2
        self.day = 0

    def lane(self, request: dict) -> float:
        leg = request["legs"][0]
        return self.pickup.get(leg["pickup"]["placeId"], 0.0) + self.delivery.get(leg["delivery"]["placeId"], 0.0)

    def base(self, request: dict, markup: float, trust: int, only_later: bool) -> float:
        """The score without today's level."""
        return self.lane(request) - self.slope * math.log(markup / (1 + trust / 100)) + self.only_later * only_later

    def in_outage(self, request: dict, at: int) -> float:
        """The rise of the level for this request: its pickup lies in the region that is down now."""
        if self.outage and self.outage[0] == at // DAY and 8 * HOUR <= at % DAY < 18 * HOUR and request["legs"][0]["pickup"]["placeId"] in self.outage[1]:
            return self.outage[2]
        return 0.0

    def of_dealer(self, request: dict) -> list[float]:
        return self.dealers.get(request["dealerId"], [0.0, self.dealer_sd ** 2])

    def score(self, request: dict, markup: float, trust: int, only_later: bool, at: int = 0) -> float:
        return self.mean + self.of_dealer(request)[0] + self.base(request, markup, trust, only_later) + self.in_outage(request, at)

    def chance(self, request: dict, markup: float, trust: int, only_later: bool, at: int = 0) -> float:
        # The level is uncertain: a wider belief flattens the curve (the probit approximation of a logistic-normal mean).
        z = self.score(request, markup, trust, only_later, at) / math.sqrt(1 + math.pi * (self.var + self.of_dealer(request)[1]) / 8)
        return 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))

    def learn(self, request: dict, markup: float, trust: int, only_later: bool, won: bool, day: int, at: int = 0) -> None:
        """One step of Bayes for the level, from one quote that the dealer judged."""
        if day > self.day:  # a new day has a new day factor: the belief widens
            self.var += self.day_var * (day - self.day)
            self.day, self.today = day, []
            for belief in self.dealers.values():  # and the competitor has moved its prices for each dealer
                belief[1] = min(self.dealer_sd ** 2, belief[1] + (self.dealer_sd / 2) ** 2)
        z = self.score(request, markup, trust, only_later, at)
        p = 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))
        # One answer says something about the sum of the day's level and the dealer's: each moves by its share of the doubt.
        dealer = self.dealers.setdefault(request["dealerId"], [0.0, self.dealer_sd ** 2])
        doubt = self.var + dealer[1]
        step = (won - p) / (1 + doubt * p * (1 - p))
        shrink = p * (1 - p) / (1 + doubt * p * (1 - p))
        self.mean, dealer[0] = self.mean + self.var * step, dealer[0] + dealer[1] * step
        self.var, dealer[1] = self.var * (1 - self.var * shrink), dealer[1] * (1 - dealer[1] * shrink)
        if self.regions and day % 7 < 5 and 8 * HOUR <= at % DAY < 18 * HOUR and self.outage is None:
            self.today.append((request["legs"][0]["pickup"]["placeId"], self.base(request, markup, trust, only_later), won))
            if len(self.today) >= 30 and len(self.today) % 5 == 0:
                self.find_outage(day, at)

    def find_outage(self, day: int, at: int) -> None:
        """Looks for a region whose dealers took our prices far more often today than the dealers
        elsewhere. The day's level comes from the requests outside the region, so a day that is
        dear or cheap everywhere, such as a price war, does not look like an outage."""
        best = None
        for town, region in self.regions.items():
            inside = [(base, won) for place, base, won in self.today if place in region]
            outside = [(base, won) for place, base, won in self.today if place not in region]
            if len(inside) < 10 or len(outside) < 10:
                continue
            level = fit_level(outside, self.mean)
            expected = [sigmoid(level + base) for base, _ in inside]
            z = (sum(won for _, won in inside) - sum(expected)) / math.sqrt(sum(p * (1 - p) for p in expected) + 1e-9)
            if z > OUTAGE_Z and (best is None or z > best[0]):
                best = (z, town, level, fit_level(inside, level) - level)
        if best:
            z, town, level, shift = best
            shift = max(OUTAGE_SHIFT[0], min(OUTAGE_SHIFT[1], shift))
            self.outage = (day, self.regions[town], shift)
            self.mean = level  # the wins inside the region had pulled the belief up
            print(f"{clock(at)} the competitor seems down around {town}: dealers there take our prices far more often than elsewhere (z {z:.1f}); their level is raised by {shift:.1f} until 18:00")


def sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))


def fit_level(quotes: list, start: float) -> float:
    """The level that makes the expected number of wins equal the wins: a few Newton steps."""
    level = start
    for _ in range(8):
        chances = [sigmoid(level + base) for base, _ in quotes]
        slope = sum(p * (1 - p) for p in chances)
        if slope < 1e-6:
            break
        level += max(-2.0, min(2.0, (sum(won for _, won in quotes) - sum(chances)) / slope))
    return level
