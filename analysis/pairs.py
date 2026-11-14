"""How often does a car go in a return-trip pair, by lane? A pair costs 0.75 of the two typical fees, a car alone
about 1.03 of its own, so a car on a lane that often pairs costs less than the desk thought when it priced each
car as if it went alone. Writes the share of each lane's cars that went in a pair, and what a pair saves, to
desk/fitted.json.

  python -m analysis.pairs [label ...]      the reveals of these runs (default v15 v16 v17b: 40 weeks each)
"""
from __future__ import annotations

import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PRIOR = 30  # a lane's share counts as that many orders at the share of all lanes of its length
BANDS = [2500, 4000, 6000, 8000, 12000]  # typical fee in cents: the edges of the length bands


def band(reference: float) -> int:
    return sum(reference > edge for edge in BANDS)


def main() -> None:
    labels = sys.argv[1:] or ["v15", "v16", "v17b"]
    rows = []
    for label in labels:
        for folder in sorted(glob.glob(str(ROOT / "results" / "reveals" / label / "L8-*"))):
            gigs = pd.read_csv(folder + "/gigs.csv")
            requests = pd.read_csv(folder + "/requests.csv", usecols=["id", "referenceFeeCents", "legs", "outcome"]).set_index("id")
            legs = pd.read_csv(folder + "/legs.csv", usecols=["requestId", "leg", "pickup.placeId", "delivery.placeId"])
            legs = legs[legs.leg == 0].set_index("requestId")
            for gig in gigs.itertuples(index=False):
                if gig.status != "done":
                    continue
                orders = sorted({stop["orderId"] for stop in json.loads(gig.stops)})
                if any(order not in requests.index or requests.legs[order] != 1 for order in orders):
                    continue  # a trade-in is one gig of its own
                typical = sum(requests.referenceFeeCents[order] for order in orders)
                for order in orders:
                    rows.append((f'{legs["pickup.placeId"][order]}>{legs["delivery.placeId"][order]}', requests.referenceFeeCents[order], len(orders) > 1, gig.feeCents / typical))
    cars = pd.DataFrame(rows, columns=["lane", "reference", "paired", "fee"])
    cars["band"] = cars.reference.map(band)
    by_band = cars.groupby("band").paired.mean()
    count, pairs = defaultdict(int), defaultdict(int)
    for lane, paired in zip(cars.lane, cars.paired):
        count[lane] += 1
        pairs[lane] += paired
    lane_band = cars.groupby("lane").band.agg(lambda b: int(b.mode().iloc[0]))
    lanes = {lane: round((pairs[lane] + PRIOR * by_band[lane_band[lane]]) / (count[lane] + PRIOR), 3) for lane in sorted(count)}
    saving = 1 - cars[cars.paired].fee.mean() / cars[~cars.paired].fee.mean()
    fitted_path = ROOT / "desk" / "fitted.json"
    fitted = json.loads(fitted_path.read_text())
    fitted["pair_share"] = {"lanes": lanes, "bands": BANDS, "by_band": [round(float(by_band.get(i, 0.0)), 3) for i in range(len(BANDS) + 1)], "saving": round(float(saving), 3),
                            "from": f"{len(cars)} cars of {len(labels)} runs ({' '.join(labels)})"}
    fitted_path.write_text(json.dumps(fitted, indent=1) + "\n")
    print(f"{len(cars)} cars, {100 * cars.paired.mean():.1f}% in a pair. A pair's fee is {cars[cars.paired].fee.mean():.3f} of the typical fees, a car alone pays {cars[~cars.paired].fee.mean():.3f}: a pair saves {100 * saving:.1f}%.")
    print("share in a pair by the lane's typical fee (up to 25, 40, 60, 80, 120 euros, and above):", " ".join(f"{100 * share:.0f}%" for share in fitted["pair_share"]["by_band"]))
    shares = pd.Series(lanes)
    print(f"{len(lanes)} lanes; their share after shrinking: 5th percentile {100 * shares.quantile(0.05):.0f}%, median {100 * shares.median():.0f}%, 95th {100 * shares.quantile(0.95):.0f}%")


if __name__ == "__main__":
    main()
