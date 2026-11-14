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
LANE_LENGTH = (4.6814, 0.8868)  # the log of a lane's road minutes: its mean and spread over the requests of 80 exploration weeks


class Market:
    def __init__(self, level: int, day_sd: float = 1.3, regions: Optional[dict] = None, outages: bool = True, dealer_sd: float = 0.0, slope_scale: float = 1.0,
                 minutes: Optional[dict] = None, tilt: tuple = (0.0, 0.0), places: tuple = (0.0, 0.0)):
        fitted = FITTED["dealer"]
        # The competitor's prices have parts that are new in each world and move during the week (the handbook). Once a
        # week its price list changes shape, so short and long lanes move in opposite directions. Some mornings its
        # prices for cars leaving a place, or arriving there, move a step. So on top of the day's level the desk learns
        # this week's tilt by the lane's length, and this week's level of each pickup place and of each delivery place.
        self.minutes = minutes or {}  # (pickup place, delivery place) -> road minutes
        self.own = {"tilt": tilt, "from": places, "to": places}  # part -> (how far it lies from zero, the share of it that holds overnight)
        self.parts: dict[tuple, list[float]] = {}  # (part, place) -> [mean, variance]
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

    def of_week(self, request: dict) -> list[tuple[list[float], float]]:
        """This week's own parts that count for the request: each belief with its weight in the score."""
        leg = request["legs"][0]
        pickup, delivery = leg["pickup"]["placeId"], leg["delivery"]["placeId"]
        length = (math.log(max(1, self.minutes.get((pickup, delivery), 108))) - LANE_LENGTH[0]) / LANE_LENGTH[1]
        return [(self.parts.setdefault((part, place), [0.0, self.own[part][0] ** 2]), weight)
                for part, place, weight in (("tilt", "", length), ("from", pickup, 1.0), ("to", delivery, 1.0)) if self.own[part][0] > 0]

    def score(self, request: dict, markup: float, trust: int, only_later: bool, at: int = 0) -> float:
        own = sum(belief[0] * weight for belief, weight in self.of_week(request))
        return self.mean + self.of_dealer(request)[0] + own + self.base(request, markup, trust, only_later) + self.in_outage(request, at)

    def chance(self, request: dict, markup: float, trust: int, only_later: bool, at: int = 0) -> float:
        # The level is uncertain: a wider belief flattens the curve (the probit approximation of a logistic-normal mean).
        doubt = self.var + self.of_dealer(request)[1] + sum(belief[1] * weight ** 2 for belief, weight in self.of_week(request))
        z = self.score(request, markup, trust, only_later, at) / math.sqrt(1 + math.pi * doubt / 8)
        return 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))

    def learn(self, request: dict, markup: float, trust: int, only_later: bool, won: bool, day: int, at: int = 0) -> None:
        """One step of Bayes for the level, from one quote that the dealer judged."""
        if day > self.day:  # a new day has a new day factor: the belief widens
            self.var += self.day_var * (day - self.day)
            self.day, self.today = day, []
            for belief in self.dealers.values():  # and the competitor has moved its prices for each dealer
                belief[1] = min(self.dealer_sd ** 2, belief[1] + (self.dealer_sd / 2) ** 2)
            for (part, _), belief in self.parts.items():  # each of the week's parts keeps a share of what it learned, and its doubt grows back
                sd, keep = self.own[part]
                belief[0], belief[1] = belief[0] * keep, keep ** 2 * belief[1] + (1 - keep ** 2) * sd ** 2
        z = self.score(request, markup, trust, only_later, at)
        p = 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))
        # One answer says something about the sum of the day's level and the other parts: each moves by its share of the doubt.
        dealer = self.dealers.setdefault(request["dealerId"], [0.0, self.dealer_sd ** 2])
        live = [(dealer, 1.0)] + self.of_week(request)
        doubt = self.var + sum(belief[1] * weight ** 2 for belief, weight in live)
        step = (won - p) / (1 + doubt * p * (1 - p))
        shrink = p * (1 - p) / (1 + doubt * p * (1 - p))
        self.mean, self.var = self.mean + self.var * step, self.var * (1 - self.var * shrink)
        for belief, weight in live:
            belief[0], belief[1] = belief[0] + belief[1] * weight * step, belief[1] * (1 - belief[1] * weight ** 2 * shrink)
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


WAR_STEP = math.log(0.8)  # on the day of its price war the competitor quotes 20% under its prices: this much on the log of the price
OUTAGE_STEP = math.log(1.3)  # the backup of a region where the competitor is down costs about 30% more
SURE = 0.4  # no case weighs more than this before the day's first answer: the desk may have missed the event on an earlier day


class EventMarket(Market):
    """The day's level with the week's two unannounced events. A week of level 8 has one price war day, when the
    competitor quotes 20% lower everywhere, and one outage day, when it is down in one region and the dealers
    there pay a backup that is 30% dearer: both from 08:00 to 18:00, and not on the same day. Each morning the
    desk holds one belief about the day's level for each case: a calm day, the war, or the outage around each
    town. Each answer weighs the cases by how well they foretold it, and moves each case's level by one step of
    Bayes. A price is judged against the mix. So a war or an outage shows after a handful of answers, and the
    level of a calm day, from which the next morning starts, is not dragged along by it."""

    def __init__(self, level: int, calm_sd: float = 0.7, **kwargs):
        areas = kwargs.get("regions") or {}
        super().__init__(level, **{**kwargs, "outages": False})
        self.day_var = calm_sd ** 2  # a calm day strays less from the day before than a day that may hold an event
        self.areas = areas  # town -> the places within 80 km of it
        self.war_left, self.outage_left = level >= 8, level >= 6  # each comes once a week
        self.cases: list[list] = []  # today's cases: [weight, mean of the level, its variance, "calm", "war" or the town of the outage]
        self.day = -1
        self.asked: tuple = ()  # the last request whose cases were laid out, and that layout: a price is judged many times for one request

    def mix(self) -> tuple[float, float]:
        """The level of a calm day over today's cases: its mean and its variance."""
        total = sum(case[0] for case in self.cases)
        mean = sum(case[0] * case[1] for case in self.cases) / total
        return mean, sum(case[0] * (case[2] + (case[1] - mean) ** 2) for case in self.cases) / total

    def start(self, day: int) -> None:
        """A new day: what yesterday was, the level of a calm day carried over, and today's cases."""
        if self.cases:
            total = sum(case[0] for case in self.cases)
            if sum(case[0] for case in self.cases if case[3] == "war") > total / 2:
                self.war_left = False
            if sum(case[0] for case in self.cases if case[3] not in ("calm", "war")) > total / 2:
                self.outage_left = False
            self.mean, self.var = self.mix()
            self.var += self.day_var * (day - self.day)
            for belief in self.dealers.values():
                belief[1] = min(self.dealer_sd ** 2, belief[1] + (self.dealer_sd / 2) ** 2)
            for (part, _), belief in self.parts.items():
                sd, keep = self.own[part]
                belief[0], belief[1] = belief[0] * keep, keep ** 2 * belief[1] + (1 - keep ** 2) * sd ** 2
        self.day, self.asked = day, ()
        working, left = day % 7 < 5, max(1, 5 - day % 7)
        war = min(SURE, 1 / left) if self.war_left and working else 0.0
        outage = min(SURE, 1 / left) * (1 - war) if self.outage_left and working and self.areas else 0.0
        self.cases = [[1 - war - outage, self.mean, self.var, "calm"]]
        if war:
            self.cases.append([war, self.mean, self.var, "war"])
        if outage:
            self.cases += [[outage / len(self.areas), self.mean, self.var, town] for town in self.areas]

    def shifts(self, request: dict) -> list[float]:
        """What each of today's cases adds to the level for this request."""
        if not 8 * HOUR <= request["arrivedAt"] % DAY < 18 * HOUR:
            return [0.0] * len(self.cases)
        pickup = request["legs"][0]["pickup"]["placeId"]
        return [0.0 if kind == "calm" else self.slope * WAR_STEP if kind == "war" else self.slope * OUTAGE_STEP if pickup in self.areas[kind] else 0.0 for _, _, _, kind in self.cases]

    def chance(self, request: dict, markup: float, trust: int, only_later: bool, at: int = 0) -> float:
        if request["arrivedAt"] // DAY > self.day:
            self.start(request["arrivedAt"] // DAY)
        if not self.asked or self.asked[0] != request["id"]:
            own = self.of_week(request)
            total = sum(case[0] for case in self.cases)
            doubt = self.of_dealer(request)[1] + sum(belief[1] * weight ** 2 for belief, weight in own)
            rest = self.of_dealer(request)[0] + sum(belief[0] * weight for belief, weight in own)
            self.asked = (request["id"], [(case[0] / total, case[1] + shift + rest, math.sqrt(1 + math.pi * (case[2] + doubt) / 8)) for case, shift in zip(self.cases, self.shifts(request))])
        base = self.base(request, markup, trust, only_later)
        return sum(weight * sigmoid((level + base) / flat) for weight, level, flat in self.asked[1])

    def learn(self, request: dict, markup: float, trust: int, only_later: bool, won: bool, day: int, at: int = 0) -> None:
        if request["arrivedAt"] // DAY > self.day:
            self.start(request["arrivedAt"] // DAY)
        dealer = self.dealers.setdefault(request["dealerId"], [0.0, self.dealer_sd ** 2])
        live = [(dealer, 1.0)] + self.of_week(request)
        rest = sum(belief[0] * weight for belief, weight in live) + self.base(request, markup, trust, only_later)
        doubt = sum(belief[1] * weight ** 2 for belief, weight in live)
        moves = []
        for case, shift in zip(self.cases, self.shifts(request)):
            score = case[1] + shift + rest
            foretold = sigmoid(score / math.sqrt(1 + math.pi * (case[2] + doubt) / 8))
            case[0] *= foretold if won else 1 - foretold  # the case that foretold the answer better weighs more
            p = sigmoid(score)
            step = (won - p) / (1 + (case[2] + doubt) * p * (1 - p))
            shrink = p * (1 - p) / (1 + (case[2] + doubt) * p * (1 - p))
            case[1], case[2] = case[1] + case[2] * step, case[2] * (1 - case[2] * shrink)
            moves.append((step, shrink))
        total = sum(case[0] for case in self.cases) or 1.0
        for case in self.cases:
            case[0] /= total
        step = sum(case[0] * move[0] for case, move in zip(self.cases, moves))
        shrink = sum(case[0] * move[1] for case, move in zip(self.cases, moves))
        for belief, weight in live:  # the week's parts move by the step of the mix
            belief[0], belief[1] = belief[0] + belief[1] * weight * step, belief[1] * (1 - belief[1] * weight ** 2 * shrink)
        self.mean, self.var = self.mix()
        self.asked = ()


WEEKDAY = [-0.27, 0.25, 0.30, 0.04, -0.32]  # a weekday's level against the week's own, over 400 exploration days
NORMAL_SD = 0.75  # how far an ordinary day lies from its week's level
WAR = (-2.75, 0.5)  # a price war day: the competitor quotes 20% lower, which is this much on the curve, give or take
WORLD_SD = 0.9  # how far a week's level lies from the level of all weeks


class RegimeMarket(Market):
    """The day's level as one of two kinds of day. An ordinary day lies near the week's own level,
    which the desk learns over the week. A price war day lies 20% lower; a week has one. Each
    morning the desk holds both beliefs, weighs them by how well they explain the dealers' answers,
    and updates each by one step of Bayes. So a few quotes tell it which kind of day it is, and
    the morning after a price war it does not start from the war's level."""

    def __init__(self, level: int, **kwargs):
        super().__init__(level, **kwargs)
        self.week = [self.mean, WORLD_SD ** 2]  # the belief about the week's own level
        self.kinds: list[list[float]] = []  # today's beliefs, ordinary then war: [weight, mean, variance]
        self.war_seen = level < 8  # below level 8 there is no price war
        self.day = -1

    def start(self, day: int) -> None:
        if self.kinds:  # what yesterday taught about the week
            ordinary, war = self.kinds
            if war[0] > 0.5:
                self.war_seen = True
            elif war[0] < 0.2:  # a day that could be either kind teaches nothing about the week
                seen, noise = ordinary[1] - WEEKDAY[self.day % 7 % 5], NORMAL_SD ** 2 + ordinary[2]
                gain = self.week[1] / (self.week[1] + noise)
                self.week = [self.week[0] + gain * (seen - self.week[0]), self.week[1] * (1 - gain)]
        self.day = day
        left = max(1, 5 - day % 7)
        war = 0.0 if self.war_seen or day % 7 > 4 else 1 / left
        centre = self.week[0] + WEEKDAY[day % 7 % 5]
        self.kinds = [[1 - war, centre, self.week[1] + NORMAL_SD ** 2], [war, centre + WAR[0], self.week[1] + WAR[1] ** 2]]
        self.today = []

    def weights(self, at: int) -> list[float]:
        """A price war runs from 08:00 to 18:00: outside those hours every day is ordinary."""
        if not self.kinds:
            return []
        if not 8 * HOUR <= at % DAY < 18 * HOUR:
            return [1.0, 0.0]
        return [kind[0] for kind in self.kinds]

    @property
    def mean(self) -> float:
        return sum(kind[0] * kind[1] for kind in self.kinds) if getattr(self, "kinds", None) else self._mean

    @mean.setter
    def mean(self, value: float) -> None:
        self._mean = value

    @property
    def var(self) -> float:
        if not getattr(self, "kinds", None):
            return self._var
        mean = self.mean
        return sum(kind[0] * (kind[2] + (kind[1] - mean) ** 2) for kind in self.kinds)

    @var.setter
    def var(self, value: float) -> None:
        self._var = value

    def chance(self, request: dict, markup: float, trust: int, only_later: bool, at: int = 0) -> float:
        if not self.kinds or at // DAY != self.day:
            self.start(at // DAY)
        base = self.base(request, markup, trust, only_later)
        return sum(weight * sigmoid((kind[1] + base) / math.sqrt(1 + math.pi * kind[2] / 8)) for weight, kind in zip(self.weights(at), self.kinds))

    def learn(self, request: dict, markup: float, trust: int, only_later: bool, won: bool, day: int, at: int = 0) -> None:
        if not self.kinds or day != self.day:
            self.start(day)
        base = self.base(request, markup, trust, only_later)
        working = 8 * HOUR <= at % DAY < 18 * HOUR
        for index, kind in enumerate(self.kinds):
            if index == 1 and not working:
                continue  # an answer outside the war's hours says nothing about a war
            expected = sigmoid((kind[1] + base) / math.sqrt(1 + math.pi * kind[2] / 8))
            if working:
                kind[0] *= expected if won else 1 - expected
            p = sigmoid(kind[1] + base)
            precision = 1 / kind[2] + p * (1 - p)
            kind[1] += (won - p) / precision
            kind[2] = 1 / precision
        total = sum(kind[0] for kind in self.kinds)
        for kind in self.kinds:
            kind[0] = kind[0] / total if total > 0 else 0.5
