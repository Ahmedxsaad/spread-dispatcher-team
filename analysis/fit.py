"""Fits the desk's two estimates on weeks that we played, and writes desk/fitted.json.

  python analysis/fit.py explore-v1 [more labels]

1. The chance that a car gets a driver in time and arrives on time, and the chance that its gig is
   booked at the opening fee: logistic curves on the features of desk/model.py.
2. The chance that a dealer takes a price: a logistic curve in the log of the price over the list
   price, divided by the dealer's trust (1% for each order on time), with a level for each lane
   that holds in every world. Each world-day has its own level in the fit; the desk learns that
   level during the week.
"""
from __future__ import annotations

import json
import random
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold, cross_val_predict

sys.path.insert(0, "analysis")
sys.path.insert(0, ".")
from load import orders, quotes, weeks  # noqa: E402

from desk.clock import awake_between  # noqa: E402
from desk.model import GIG_FEATURES, drivers_near, expand, gig_features  # noqa: E402


def gig_table(labels: list[str]) -> pd.DataFrame:
    tables = []
    for label in labels:
        for folder in weeks(label, 8):
            o = orders(folder)
            o = o[~o.cancelled & (o.legs == 1) & o.posted_at.notna()].copy()
            places = pd.read_csv(f"{folder}/places.csv").to_dict("records")
            roster = pd.read_csv(f"{folder}/drivers.csv").to_dict("records")
            near = drivers_near(places, roster)
            views = pd.read_csv(f"{folder}/views.csv")
            gigs = pd.read_csv(f"{folder}/gigs.csv")
            gigs["order"] = gigs.orders.str.split(" ").str[0]
            first_gig = gigs.sort_values("postedAt").groupby("order").id.first()
            # The fee of the first view of the order's first gig is its opening fee: the gigs table shows only the last schedule.
            opened = views.sort_values("at").groupby("gigId").feeCents.first()
            o["open_fee"] = o.order.map(first_gig).map(opened)
            o = o[o.open_fee.notna()]
            o["fee"] = o.open_fee / o.ref
            # Our orders without a driver at the minute of the post: every order of the week, also the ones left out above.
            every = orders(folder)
            posted, booked = every.posted_at.dropna().values, every.book_at.reindex(every.posted_at.dropna().index).fillna(1e12).values
            o["waiting"] = [int(((posted < p) & (booked > p)).sum()) for p in o.posted_at]
            o["x"] = [gig_features(awake_between(int(p), int(t)) / 60, m / 60, f, near[a], near[b], pr, pp, pd_, int(p) // 1440, w)
                      for p, t, m, f, a, b, pr, pp, pd_, w in zip(o.posted_at, o.last_pickup, o.mins, o.fee, o.pickup, o.delivery, o.premium, o.private_pickup, o.private_delivery, o.waiting)]
            in_time = (o.last_pickup - o.final_book_at) >= 0
            late_by_note = o.delivered_at > o["truth.noteDeadline"].fillna(1e12)
            o["ok"] = in_time & o.on_time & ~late_by_note
            o["at_open"] = (o.book_fee <= o.open_fee) & (o.book_at <= o.last_pickup)
            o["label"] = label
            tables.append(o)
    return pd.concat(tables, ignore_index=True)


def fit_curve(table: pd.DataFrame, target: str, products: bool = True) -> dict:
    """A logistic curve on the features, and with `products` on the products and squares of the
    continuous ones too. On weeks held out, the products find 7 in 100 more orders at the same
    on-time share (0.868 against 0.851 AUC), close to boosted trees (0.873), and stay a formula."""
    X, y = np.array([expand(x) if products else x for x in table.x]), table[target].values
    mean, scale = X.mean(axis=0), X.std(axis=0) + 1e-9
    Z = (X - mean) / scale
    groups = (table.label + table.week).values
    held_out = cross_val_predict(LogisticRegression(C=0.3, max_iter=5000), Z, y, cv=GroupKFold(8), groups=groups, method="predict_proba")[:, 1]
    model = LogisticRegression(C=0.3, max_iter=5000).fit(Z, y)
    return {"features": GIG_FEATURES, "products": products, "coef": [round(float(c), 5) for c in model.coef_[0]], "intercept": round(float(model.intercept_[0]), 5),
            "mean": [round(float(v), 6) for v in mean], "scale": [round(float(v), 6) for v in scale],
            "orders": int(len(table)), "share": round(float(y.mean()), 4), "auc_on_weeks_held_out": round(float(roc_auc_score(y, held_out)), 3)}


def fit_dealers(labels: list[str]) -> dict:
    q = pd.concat([quotes(folder).assign(label=label) for label in labels for folder in weeks(label, 8)], ignore_index=True)
    q = q[q.markup < 2.5].copy()
    q["x"] = np.log(q.markup) - np.log1p(q.trust / 100)  # the price as the dealer sees it
    q["only_later"] = (q["mode"] == "last").astype(float)  # we left out the fastest option that the dealer asked for
    days = pd.get_dummies(q.label + q.week + ":" + (q.arrivedAt // 1440).astype(str)).astype(float)
    pickups = pd.get_dummies(q["pickup.placeId"]).astype(float)
    deliveries = pd.get_dummies(q["delivery.placeId"]).astype(float)
    X = np.hstack([q[["x", "only_later"]].values, days.values, pickups.values, deliveries.values])
    model = LogisticRegression(C=1e3, max_iter=5000, fit_intercept=False).fit(X, q.won)
    coef = model.coef_[0]
    day_levels = coef[2:2 + days.shape[1]]
    pickup = pd.Series(coef[2 + days.shape[1]:2 + days.shape[1] + pickups.shape[1]], index=pickups.columns)
    delivery = pd.Series(coef[2 + days.shape[1] + pickups.shape[1]:], index=deliveries.columns)
    # Centre the town effects on the requests, so the level carries the mean.
    shift = float((pickups.values @ pickup.values + deliveries.values @ delivery.values).mean())
    pickup_mean = float((pickups.values @ pickup.values).mean())
    return {"slope": round(float(-coef[0]), 3), "only_later": round(float(coef[1]), 3),
            "level": round(float(day_levels.mean()) + shift, 3), "level_sd": round(float(day_levels.std()), 3),
            "pickup": {town: round(float(v - pickup_mean), 3) for town, v in pickup.items()},
            "delivery": {town: round(float(v - (shift - pickup_mean)), 3) for town, v in delivery.items()},
            "quotes": int(len(q)), "world_days": int(days.shape[1])}


def main() -> None:
    labels = [arg for arg in sys.argv[1:] if not arg.startswith("--")] or ["explore-v1"]
    table = gig_table(labels)
    fitted = json.load(open("desk/fitted.json")) if "--drivers-only" in sys.argv else {}
    fitted.update({"from": labels, "driver_in_time": fit_curve(table, "ok"), "booked_at_opening": fit_curve(table, "at_open")})
    if "--drivers-only" not in sys.argv:
        fitted["dealer"] = fit_dealers(labels)
    with open("desk/fitted.json", "w") as file:
        json.dump(fitted, file, indent=1)
    for name in ("driver_in_time", "booked_at_opening"):
        curve = fitted[name]
        print(f"{name}: {curve['orders']} orders, share {curve['share']:.3f}, AUC on weeks held out {curve['auc_on_weeks_held_out']}, {len(curve['coef'])} coefficients")
    dealer = fitted["dealer"]
    print(f"dealer: {dealer['quotes']} quotes on {dealer['world_days']} world-days, slope {dealer['slope']}, only later options {dealer['only_later']}, level {dealer['level']} (sd between days {dealer['level_sd']})")


if __name__ == "__main__":
    main()
