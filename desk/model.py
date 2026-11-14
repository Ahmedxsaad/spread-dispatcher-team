"""The desk's two estimates, each a logistic curve fitted on weeks that we played (analysis/fit.py
writes fitted.json): the chance that a car gets a driver in time, and the chance that a dealer
takes a price. Estimation lives here; the decisions that use it live in desk.py."""
from __future__ import annotations

import json
import math
from pathlib import Path

FITTED = json.loads((Path(__file__).parent / "fitted.json").read_text()) if (Path(__file__).parent / "fitted.json").exists() else {}

GIG_FEATURES = ["log awake hours", "hours short of 6", "drive hours", "drive hours over 3", "log fee", "log drivers near pickup",
                "log drivers near delivery", "premium", "private pickup", "private delivery", "day", "log orders without a driver"]
FEE = GIG_FEATURES.index("log fee")


def gig_features(awake_hours: float, drive_hours: float, fee: float, pickup_drivers: int, delivery_drivers: int,
                 premium: bool, private_pickup: bool, private_delivery: bool, day: int, waiting: float) -> list[float]:
    """What decides whether a driver takes a gig in time: the awake hours until its last pickup,
    the length of the drive, the fee over the typical fee, how many drivers live within 100 km
    of each end, and how many of our orders already wait for a driver."""
    hours = min(max(awake_hours, 0.5), 40)
    return [math.log(hours), max(0.0, 6 - awake_hours), drive_hours, max(0.0, drive_hours - 3), math.log(fee),
            math.log1p(pickup_drivers), math.log1p(delivery_drivers), float(premium), float(private_pickup), float(private_delivery), float(day),
            math.log1p(max(0.0, waiting))]


def at_fee(x: list[float], fee: float) -> list[float]:
    """The same gig at another fee."""
    return x[:FEE] + [math.log(fee)] + x[FEE + 1:]


# The features whose products and squares a curve can use: all but the three yes-or-no ones.
CONTINUOUS = [i for i, name in enumerate(GIG_FEATURES) if name not in ("premium", "private pickup", "private delivery")]


def expand(x: list[float]) -> list[float]:
    """The features, then the product of each two continuous ones, then their squares. A curve on
    these says, for example, that a higher fee helps less when the last pickup is hours away."""
    return (x + [x[a] * x[b] for i, a in enumerate(CONTINUOUS) for b in CONTINUOUS[i + 1:]] + [x[a] ** 2 for a in CONTINUOUS])


def logistic(curve: dict, x: list[float], towns: tuple = ()) -> float:
    """The curve's chance for the features `x`. With `towns`, the pickup and the delivery place, it adds what
    the curve knows about each town beyond the features: some towns find drivers more easily than their count of drivers says."""
    if curve.get("products"):
        x = expand(x)
    if "mean" in curve:  # the curve was fitted on standardised features
        x = [(v - m) / s for v, m, s in zip(x, curve["mean"], curve["scale"])]
    z = curve["intercept"] + sum(c * v for c, v in zip(curve["coef"], x))
    if towns:
        z += curve["towns"]["shift"] + curve["towns"]["pickup"].get(towns[0], 0.0) + curve["towns"]["delivery"].get(towns[1], 0.0)
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))


def air_km(a: dict, b: dict) -> float:
    """The straight-line distance between two places of the map."""
    la1, lo1, la2, lo2 = (math.radians(v) for v in (a["lat"], a["lon"], b["lat"], b["lon"]))
    return 6371 * 2 * math.asin(math.sqrt(math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2))


def drivers_near(places: list[dict], roster: list[dict], km: float = 100) -> dict[str, int]:
    """For each place, the drivers who live within `km` of it in a straight line."""
    homes: dict[str, int] = {}
    for driver in roster:
        homes[driver["homePlaceId"]] = homes.get(driver["homePlaceId"], 0) + 1
    by_id = {place["id"]: place for place in places}
    return {place["id"]: sum(count for home, count in homes.items() if home in by_id and air_km(place, by_id[home]) <= km) for place in places}
