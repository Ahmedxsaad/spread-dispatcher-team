"""Builds the page that shows the desk and its evidence: ui/index.html, one file that opens by itself.

    python3 ui/build.py

Every number on the page is computed here from results/runs.csv, the recorded test final and desk/fitted.json,
or copied from the README where a round's rank is stated. The layout is ui/page.html.
"""
from __future__ import annotations

import base64
import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETS = ("eval", "hold", "more", "check")  # the four families of level 8 weeks that judge a version

# Each version on the 20 tuning weeks: (version, its label in the log, what it adds).
LADDER = [
    ("starter", "starter", "The kit starter"),
    ("v2", "v2", "Prices by expected profit, from two fitted curves"),
    ("v5", "v5-notes", "A reader for the dealers' notes"),
    ("v8", "v8", "Return-trip pairs, the day with few drivers, the guard"),
    ("v9", "v9", "A wider radius for pairs"),
    ("v11", "v11", "Prices 6% above the curve's choice"),
    ("v12", "v12", "No low prices to buy trust; a lower minimum chance"),
    ("v13", "v13", "Fee raises before the last hours"),
    ("v15", "v15", "Riskier cars while the week has on-time share to spare"),
    ("v16", "v16", "Trade-ins"),
    ("v17", "q-both", "A market learner that follows the competitor's own moves"),
    ("v18", "qe-94", "The easiest cars open at a lower fee"),
    ("v19", "bc-35", "A morning alarm for cars that sit"),
    ("v20", "gv-a", "The guard's reserve follows what the week can still bring"),
]

# Comparisons to show week by week: (what was tried, the label without it, the label with it, verdict, one remark).
PAIRS = [
    ("The guard's reserve follows what the week can still bring", "bc-35", "gv-a", "kept",
     "Version 20. Judged once more on 80 weeks that no setting had seen: +€181 a week there."),
    ("A cap of 80, not 60, on our orders without a driver", "gv-a", "mw-80", "kept",
     "Version 21. The old cap stopped all pricing on Friday afternoons."),
    ("The easiest cars open at a lower fee", "q-both", "qe-94", "kept",
     "Version 18. It also lifts the lowest week, from 91.5% to 93.2% on time."),
    ("A market learner that follows the competitor's own moves", "v16", "q-both", "kept",
     "Version 17. It foretells the next answer 3.9% better on weeks with random prices."),
    ("A morning alarm for cars that sit", "qe-94", "bc-35", "kept as insurance",
     "Version 19. Nothing on average: it rang in 6 of 80 new weeks, and the hard one made €4,002 more."),
    ("A looser guard: 93% on time in the worst case", "qe-94", "gf-93", "not taken",
     "It gains, and the lowest week falls to 90.9% on time. The final is one week."),
    ("The smaller reserve for every week and every day", "bc-35", "gl-15", "not taken",
     "Four of 80 weeks end under 93% on time. Version 20 keeps the part that is safe."),
    ("A tighter guard: 95% on time in the worst case", "qe-94", "gd-95", "not taken",
     "0.3 points more on time, the lowest week no higher."),
    ("Prices for same-day cars on the day with few drivers", "gv-a", "sq-on", "not taken",
     "The late cars of that day use up the guard's allowance for the rest of the week."),
    ("Prices 3% lower on Monday and Tuesday", "gv-a", "rp-early-week-price", "not taken",
     "A teammate's idea: 16 more orders a week, and less margin."),
]

# The measured effect of each idea, as the README states it: (idea, why, euros a week or None, the effect in words).
IDEAS = [
    ("Read the notes", "A note can move the ready time, the opening hours or the deadline, and the world acts on it.", 1850, "failed visits fall from €515 to €5 a week"),
    ("Return-trip pairs", "Two cars in one gig: the driver needs no trip to a pickup and no trip home.", 1224, "then +€1,064 for a wider radius"),
    ("A lower minimum chance", "The driver curve is cautious: it says 94.7% in time where 97.3% are.", 1024, "more orders may wait for a driver"),
    ("Prices 6% above the curve's choice", "A 6% higher price lost 13% of the orders, where the curve said 24%.", 758, ""),
    ("Fee raises before the last hours", "A gig that nobody takes goes up in two steps before the steep last hours.", 448, "and more cars on time"),
    ("No low prices to buy trust", "A low price to win an order and its trust point loses more than the trust returns.", 368, ""),
    ("Riskier cars while there is room", "Long lanes earn €80 to €100 a car; taken only while the week's late share is under 3%.", 367, "then +€345 in a second step"),
    ("The competitor's own moves", "Its price list changes shape once a week, and moves by place on some mornings.", 314, "on 120 weeks; 0.8 fewer late cars a week"),
    ("The easiest cars open lower", "Cars that book 94 times in 100 at 0.85 of the typical fee cost less when they open at 0.72.", 233, "on 120 weeks; lowest week 91.5% to 93.2%"),
    ("Trade-ins", "Their list price is 1.9 times the typical fee, against 1.1 for other cars.", 204, ""),
    ("The reserve follows the week", "Cars due after the weekend risk 3% late, not 25%; a calm week reserves 15%.", 169, "on 200 weeks; +€181 on the 80 unseen ones"),
    ("A cap of 80 on waiting orders", "The cap of 60 stopped all pricing on Friday afternoons.", 90, "on 160 weeks; better in 29, worse in 1"),
    ("The day with few drivers", "On one night a week 8 to 24 drivers give their bookings back. That day causes 40% of all late cars.", None, "on time 96.4% to 96.9%, margin unchanged"),
    ("The guard", "Never more cars due on one day than the week can afford to lose a quarter of.", None, "lowest of 40 weeks: 91.3% to 94.1% on time"),
]

ROUNDS = [  # ranking rounds at level 8, five secret weeks each, as in the README
    ("Saturday 00:00", "v11", 74742, 97.6, ""),
    ("Saturday 09:00", "v16", 77573, 97.2, "2nd of 68"),
    ("Saturday 12:00", "v17", 99211, 97.8, "2nd of 64"),
    ("Saturday 15:00", "v18", 89578, 97.1, "6th of 79"),
    ("Saturday 18:00", "v19", 78279, 97.0, "7th of 67"),
    ("Saturday 21:00", "v20", 91134, 97.8, "5th of 56 when played"),
    ("Sunday 00:00", "v21", 87687, 97.2, "3rd of 40 when played"),
]

NOT_TAKEN = [  # a selection of the README's list: (what, label, what it did)
    ("Direct offers to a driver who has just delivered nearby", "explore-offers", "none of 6,491 offers was accepted"),
    ("A detector for the region where the competitor is down", "v9-outage", "right in 18 of 20 weeks, but too late in the day to earn"),
    ("A lower price when the car pairs with a waiting order", "v10-pairquote", "the pair seldom forms"),
    ("Driver curves with products of their features", "v17b", "rank better on paper (AUC 0.869 against 0.851), make less in play"),
    ("Two beliefs each morning: an ordinary day, a price war", "m-regimes", "€430 to €640 a week less than one belief"),
    ("A new car held off the app, to wait for a partner", "pi-30", "15 more pairs a week, and €65 to €314 less"),
    ("A price factor that follows the market's level", "gl-02", "19 more orders in cheap weeks, €202 a week less over all"),
    ("The lane's pair saving taken off the car's cost", "pp-10", "26 more orders a week, €85 less, inside the noise"),
    ("A higher opening fee for the cars that book least easily", "qh-75", "€292 a week less, on time unchanged"),
    ("The learner fed with the first option's price only", "rp-learn-fastest", "€336 a week less"),
    ("The shape of the dealer curve refitted by price band", "ds-on", "€149 a week less, lowest week 90.8% on time"),
    ("A lower on-time target for the guard, 92% for 94%", "gt-92", "€3 a week less: no change that 80 weeks can show"),
]


def weeks() -> dict:
    """label -> seed -> row, for the level 8 practice weeks that ended well."""
    by = defaultdict(dict)
    with open(ROOT / "results/runs.csv") as log:
        for row in csv.DictReader(log):
            if row["status"] == "ok" and row["level"] == "8" and row["seed"].split("-")[0] in SETS:
                by[row["label"]][row["seed"]] = row
    return by


def summary(rows: list) -> dict:
    won, on_time = sum(int(r["won"]) for r in rows), sum(int(r["on_time"]) for r in rows)
    return {"weeks": len(rows), "margin": round(statistics.mean(float(r["margin_eur"]) for r in rows)),
            "on_time": round(100 * on_time / won, 1), "lowest": round(min(float(r["on_time_pct"]) for r in rows), 1),
            "orders": round(won / len(rows))}


def data() -> dict:
    by = weeks()
    tuning = [f"eval-{i:02d}" for i in range(1, 21)]
    ladder = [{"version": version, "adds": adds, **summary([by[label][seed] for seed in tuning])} for version, label, adds in LADDER]

    pairs = []
    for what, base, new, verdict, remark in PAIRS:
        seeds = sorted(set(by[base]) & set(by[new]))
        gains = sorted(round(float(by[new][s]["margin_eur"]) - float(by[base][s]["margin_eur"])) for s in seeds)
        pairs.append({"what": what, "base": base, "new": new, "verdict": verdict, "remark": remark, "weeks": len(seeds),
                      "mean": round(statistics.mean(gains)), "error": round(statistics.stdev(gains) / math.sqrt(len(gains))),
                      "better": sum(g > 0 for g in gains), "worse": sum(g < 0 for g in gains), "gains": gains,
                      "lowest": [summary([by[label][s] for s in seeds])["lowest"] for label in (base, new)]})

    teams = {}
    with open(ROOT / "results/test-final-sunday-0100.csv") as feed:
        for row in csv.DictReader(feed):
            team = teams.setdefault(row["team"], {"name": row["team"], "place": int(row["place"]), "points": []})
            team["points"].append([int(row["world_hour"]), round(float(row["margin_eur"])), int(row["won_orders"])])
            team["margin"], team["orders"], team["on_time"] = round(float(row["margin_eur"])), int(row["won_orders"]), round(100 * float(row["on_time_share"]), 1)
    for team in teams.values():  # the orders won on each weekday: the last count of each day, less the day before
        last = [max((orders for hour, _, orders in team["points"] if hour < 24 * (day + 1)), default=0) for day in range(5)]
        team["by_day"] = [count - before for count, before in zip(last, [0] + last)]

    with open(ROOT / "results/runs.csv") as log:
        played = [(row["label"], row["status"]) for row in csv.DictReader(log)]
    unseen = summary([by["mw-80"][f"check-{i:02d}"] for i in range(1, 81)])
    fitted = json.loads((ROOT / "desk/fitted.json").read_text())
    return {
        "log": {"weeks": len(played), "labels": len({label for label, _ in played})},
        "unseen": unseen, "ladder": ladder, "ideas": [dict(zip(("idea", "why", "euros", "words"), idea)) for idea in IDEAS],
        "pairs": pairs, "rounds": [dict(zip(("round", "version", "total", "on_time", "place"), r)) for r in ROUNDS],
        "final": sorted(teams.values(), key=lambda team: team["place"]),
        "not_taken": [dict(zip(("what", "label", "result"), row)) for row in NOT_TAKEN],
        "dealer": {"slope": fitted["dealer"]["slope"], "level": fitted["dealer"]["level"], "spread": fitted["dealer"]["level_sd"]},
    }


def page(inline: bool) -> str:
    """The page with its data. inline: the diagrams go into the file itself, for a page that is hosted alone."""
    text = (ROOT / "ui/page.html").read_text().replace("/*DATA*/", json.dumps(data(), separators=(",", ":")))
    for name in ("how-the-desk-decides", "how-an-idea-becomes-a-default", "the-live-final"):
        picture = ROOT / f"docs/diagrams/{name}.svg"
        source = "data:image/svg+xml;base64," + base64.b64encode(picture.read_bytes()).decode() if inline else f"../docs/diagrams/{name}.svg"
        text = text.replace(f"DIAGRAM:{name}", source)
    return text


if __name__ == "__main__":
    head, body = page(inline=False).split("<!--BODY-->")
    (ROOT / "ui/index.html").write_text('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                                        + head + "</head>\n<body>\n" + body + "</body>\n</html>\n")
    if len(sys.argv) > 1:  # a second copy without the document's frame and with the diagrams inside, for a host that adds its own
        Path(sys.argv[1]).write_text(page(inline=True).replace("<!--BODY-->", ""))
