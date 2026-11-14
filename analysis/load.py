"""Loads the reveal CSVs of played weeks into pandas tables, one row for each order with its story:
the request, the gig postings, the booking and the delivery. Used by the notebooks-as-scripts here."""
from __future__ import annotations

import glob
import json
import os

import numpy as np
import pandas as pd

OPTIONS = ["same_day", "next_day", "within_3_days"]


def weeks(label: str, level: int | None = None) -> list[str]:
    return sorted(p for p in glob.glob(f"results/reveals/{label}/L*") if level is None or os.path.basename(p).startswith(f"L{level}-"))


def requests(folder: str) -> pd.DataFrame:
    req = pd.read_csv(f"{folder}/requests.csv")
    legs = pd.read_csv(f"{folder}/legs.csv")
    roads = pd.read_csv(f"{folder}/roads.csv").set_index(["from", "to"])
    first = legs[legs.leg == 0].set_index("requestId")
    keep = ["pickup.placeId", "delivery.placeId", "pickup.window.from", "pickup.window.to", "pickup.privateAddress", "delivery.privateAddress",
            "car.premium", "car.electric", "car.chargePercent", "truth.pickedUpAt", "truth.deliveredAt", "truth.readyAt", "truth.noteDeadline"]
    req = req.join(first[keep], on="id")
    req["km"] = [roads.km[(a, b)] for a, b in zip(req["pickup.placeId"], req["delivery.placeId"])]
    req["mins"] = [roads.minutes[(a, b)] for a, b in zip(req["pickup.placeId"], req["delivery.placeId"])]
    req["week"] = os.path.basename(folder)
    return req


def events(folder: str, kinds: list[str], cols: list[str]) -> pd.DataFrame:
    ev = pd.read_csv(f"{folder}/events.csv", usecols=lambda c: c in set(cols) | {"seq", "at", "kind"}, low_memory=False)
    return ev[ev.kind.isin(kinds)]


def quotes(folder: str) -> pd.DataFrame:
    """One row for each request that we quoted: the markup over the list price, which options we
    offered, what the dealer did, and the dealer's count of our on-time orders at that minute."""
    req = requests(folder)
    quoted = [k for k in OPTIONS if f"{k}.quoteCents" in req]
    req["offered"] = req[[f"{k}.listPriceCents" for k in OPTIONS]].notna().sum(axis=1)
    req["quoted"] = req[[f"{k}.quoteCents" for k in quoted]].notna().sum(axis=1)
    req = req[req.quoted > 0].copy()
    first = [next(k for k in OPTIONS if pd.notna(row.get(f"{k}.quoteCents"))) for _, row in req.iterrows()]
    req["first_kind"] = first
    req["markup"] = [row[f"{k}.quoteCents"] / row[f"{k}.listPriceCents"] for k, (_, row) in zip(first, req.iterrows())]
    req["mode"] = np.where(req.quoted == req.offered, "all", np.where([row[f"{next(k for k in OPTIONS if pd.notna(row[f'{k}.listPriceCents']))}.quoteCents"] == row[f"{k2}.quoteCents"]
                                                                        for k2, (_, row) in zip(first, req.iterrows())], "first", "last"))
    req.loc[req.offered == 1, "mode"] = "single"
    req["won"] = req.outcome == "won"
    # the dealer's trust count at the minute of the decision
    ev = events(folder, ["ledger"], ["line.kind", "line.orderId"])
    dealer = req.set_index("id").dealerId
    lines = ev[ev["line.kind"].isin(["revenue", "late_refund"])].sort_values("seq")
    count, seen_late, history = {}, set(), {}
    for at, kind, order in zip(lines["at"], lines["line.kind"], lines["line.orderId"]):
        d = dealer.get(order)
        if d is None:
            continue
        if kind == "revenue":
            count[d] = min(25, count.get(d, 0) + 1)
        elif order not in seen_late:
            seen_late.add(order)
            count[d] = max(0, count.get(d, 0) - 1) // 2
        history.setdefault(d, []).append((at, count[d]))
    def trust(d, at):
        value = 0
        for when, c in history.get(d, []):
            if when > at:
                break
            value = c
        return value
    req["trust"] = [trust(d, at) for d, at in zip(req.dealerId, req.respondBy)]
    return req


def orders(folder: str) -> pd.DataFrame:
    """One row for each order that we won: its request, its first gig and fee schedule, its first
    booking, its drops, and whether it arrived on time."""
    req = requests(folder).set_index("id")
    ev = events(folder, ["order_won", "gig_booked", "gig_dropped", "gig_started", "order_cancelled"],
                ["order.id", "order.deadline", "order.lastPickupAt", "order.priceCents", "order.option", "order.dealerId", "gigId", "driverId", "feeCents", "orderId"])
    gigs = pd.read_csv(f"{folder}/gigs.csv")
    gigs["cars"] = gigs.orders.str.split(" ").str.len()
    gigs["schedule"] = gigs.schedule.map(json.loads)
    gigs = gigs.assign(order=gigs.orders.str.split(" ")).explode("order")  # a pair's gig counts for both of its orders
    first_gig = gigs.sort_values("postedAt").groupby("order").first()
    of_gig = gigs[["id", "order", "cars"]].rename(columns={"id": "gigId"})
    booked = ev[ev.kind == "gig_booked"].merge(of_gig, on="gigId").sort_values("at")
    first_book = booked.groupby("order").first()
    last_book = booked.groupby("order").last()
    drops = ev[ev.kind == "gig_dropped"].merge(of_gig, on="gigId").groupby("order").size()
    cancelled = set(ev[ev.kind == "order_cancelled"].orderId)
    won = ev[ev.kind == "order_won"].set_index("order.id")
    out = pd.DataFrame({"won_at": won["at"], "deadline": won["order.deadline"], "last_pickup": won["order.lastPickupAt"], "price": won["order.priceCents"],
                        "option": won["order.option"], "dealer": won["order.dealerId"]})
    out = out.join(req[["referenceFeeCents", "legs", "mins", "km", "pickup.placeId", "delivery.placeId", "pickup.window.from", "pickup.privateAddress", "delivery.privateAddress",
                        "car.premium", "car.electric", "truth.deliveredAt", "truth.pickedUpAt", "truth.noteDeadline", "note", "week"]])
    out = out.rename(columns={"referenceFeeCents": "ref", "pickup.placeId": "pickup", "delivery.placeId": "delivery", "pickup.window.from": "ready", "truth.deliveredAt": "delivered_at",
                              "truth.pickedUpAt": "picked_at", "pickup.privateAddress": "private_pickup", "delivery.privateAddress": "private_delivery", "car.premium": "premium"})
    out["posted_at"] = first_gig.postedAt
    out["open_fee"] = first_gig.schedule.map(lambda s: s[0]["feeCents"] if isinstance(s, list) else np.nan)
    out["raise_at"] = first_gig.schedule.map(lambda s: s[1]["at"] if isinstance(s, list) and len(s) > 1 else np.nan)
    out["book_at"] = first_book["at"]
    out["book_fee"] = first_book.feeCents
    out["final_fee"] = last_book.feeCents
    out["final_book_at"] = last_book["at"]
    out["in_pair"] = last_book.cars.reindex(out.index).fillna(1) > 1  # delivered in a gig with another order
    out["drops"] = drops.reindex(out.index).fillna(0)
    out["cancelled"] = out.index.isin(cancelled)
    out["on_time"] = out.delivered_at <= out.deadline
    return out.reset_index(names="order")
