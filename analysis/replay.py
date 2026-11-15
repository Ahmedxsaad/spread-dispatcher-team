"""Writes one finished practice week as a small file that the page replays on a map of Finland.

    .venv/bin/python -m analysis.replay check-35 wd54a633eb4ef34df4a7e      # a seed's name and its world id, from results/runs.csv

The file, results/replay.json, holds what a map can show and nothing else: where each request came from and
whether we won it, each car's four moments (won, booked by a driver, picked up, delivered) with its deadline,
the margin as it grew, and the minutes at which drivers gave a booking back. The places are the world's public map.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import spread

from eval import load_env

ROOT = Path(__file__).resolve().parent.parent
HALF_HOUR = 30


def history(world) -> list[dict]:
    events, after = [], -1
    while page := world.events(after=after):
        events += page
        after = page[-1]["seq"]
    return events


def replay(seed: str, events: list[dict], places: list[dict]) -> dict:
    index = {place["id"]: i for i, place in enumerate(places)}
    orders, booked, legs, lost, drops = {}, {}, {}, [], []
    cents, margin = 0, []
    for event in events:
        kind, at = event["kind"], event["at"]
        if kind == "order_won" or kind == "order_changed":      # a change can move a deadline or a place
            orders[event["order"]["id"]] = (orders.get(event["order"]["id"], (at,))[0], event["order"])
        elif kind == "gig_booked":
            booked[event["gigId"]] = at
        elif kind == "gig_dropped":
            drops.append(at)
            booked.pop(event["gigId"], None)
        elif kind == "picked_up":
            legs[event["orderId"], event["leg"]] = {"booked": booked.get(event["gigId"], at), "picked": at}
        elif kind == "delivered" and (event["orderId"], event["leg"]) in legs:
            legs[event["orderId"], event["leg"]]["delivered"] = at
        elif kind == "ledger":
            while len(margin) < at // HALF_HOUR:                 # the margin at the end of each half hour
                margin.append(round(cents / 100))
            cents += event["line"]["cents"]
    requests = {e["request"]["id"]: e["request"] for e in events if e["kind"] == "price_request"}
    for event in events:
        if event["kind"] == "order_lost" and event["requestId"] in requests:
            request = requests[event["requestId"]]
            lost.append([request["arrivedAt"], index[request["legs"][0]["pickup"]["placeId"]]])
    cars = []
    for (order_id, leg), moments in sorted(legs.items(), key=lambda item: item[1]["picked"]):
        won, order = orders[order_id]
        stops = order["legs"][leg]
        cars.append([won, index[stops["pickup"]["placeId"]], index[stops["delivery"]["placeId"]], moments["booked"],
                     moments["picked"], moments.get("delivered", -1), order["deadline"]])
    end = events[-1]["at"]
    margin += [round(cents / 100)] * (end // HALF_HOUR + 1 - len(margin))
    late = sum(1 for car in cars if car[5] < 0 or car[5] > car[6])
    return {"seed": seed, "end": end, "margin": margin, "cars": cars, "lost": lost, "drops": drops,
            "orders": len(orders), "late": late,
            "places": [{"name": place["name"], "lat": place["lat"], "lon": place["lon"]} for place in places]}


if __name__ == "__main__":
    load_env()
    client = spread.Client()
    week = replay(sys.argv[1], history(client.world(sys.argv[2])), client.call("GET", "/v1/map")["places"])
    (ROOT / "results/replay.json").write_text(json.dumps(week, separators=(",", ":")) + "\n")
    print(f"{week['seed']}: {week['orders']} orders, {len(week['cars'])} cars moved, {week['late']} late, "
          f"{len(week['lost'])} requests lost, margin €{week['margin'][-1]:,}")
