# Spread strategy notes

These are our reading of the official documents, turned into decisions. Every rule cited here is in `01-official-docs/RULES.md` or `HANDBOOK.md`; check there before relying on a detail. Ideas marked **(hypothesis)** must be measured before we trust them.

## 1. Where the money is made and lost

Score = sum of the account:

| Line | Amount |
|---|---|
| Delivered order | + the price we quoted |
| Late ≤ 2 h | 10% of price refunded |
| Late 2–24 h | 25% refunded |
| Late > 24 h, up to 2 business days | 50% refunded |
| Late > 2 business days | 100% refunded (car must still be delivered) |
| Not delivered when the world ends (Wed 22:00) | no price **and** a penalty of 2 × price |
| Driver fee | − fee, paid when the gig is done |
| Failed visit | − half the car's share of the gig fee, at least €25 |
| Release of a booked driver | − 25% of fee (pickup > 24 h away), 50% (< 24 h), 100% (< 2 h) |
| Premium car with a non-experienced driver | − €150 per car |
| EV < 30% charge on a route > 200 km without a charging stop | arrives 90 min late, − €100 |
| Waiting at a site that is unexpectedly closed | − €15/h, max 2 h |

Why the starter loses: it quotes list price, so at level 8 (competitor 26–54% above list) it **wins most cars**, but a third of the drivers exist, so it **can't move them on time**: late refunds, undelivered penalties, and an on-time share around 45–55%.

**The core trade-off:** win only the cars we can move on time at a fee well below the price, and price those cars as high as the competitor allows.

## 2. Quoting (the dealer side)

Facts:
- Each request has 1–2 legs (trade-in = 2 legs, one price), options `same_day` / `next_day` / `within_3_days` with deadlines and **list prices**, a `referenceFeeCents` (typical driver fee), maybe a note, and a 15-minute response deadline.
- Up to level 3, every quote wins the first option at list price; decline by **not quoting** (free).
- From level 4, a request we don't quote makes that dealer slightly less willing; **a losing quote costs nothing**. So **always quote**; to decline, quote far above list.
- We may quote fewer options than offered. The dealer compares each option's price with the value of its speed.
- Competitor price = list price (unrounded) × **lane factor** × **day factor** × **world price level** × small request noise.
  - The lane factor has a part that is **almost the same in every world** (hard lanes: little return work, few drivers near the delivery place) and a part new in each world.
  - World price level: ±10% around list up to level 6; **+26% to +54% at level 8**.
  - Some mornings its prices for cars leaving/arriving at a place step up or down; once a week its price list changes shape (short vs long lanes move opposite ways).
  - Each morning it looks at each dealer: **where we won most requests it lowers prices for that dealer**, where we won few it raises them.
  - **Outage** (level ≥ 6): one working day, 08:00–18:00, the competitor is down in one region (a town + 80 km); dealers there use a backup ~30% dearer than the competitor.
  - **Price war** (level 8): one working day without an outage, 08:00–18:00, the competitor quotes 20% under its usual prices everywhere.
- **Dealer trust** (level 8): each on-time order to a dealer raises the prices it accepts from us by 1%, up to 25 orders (+25%). A late order halves that dealer's count.
- A late or undelivered car makes its dealer accept only lower prices from us (all levels).

Proposed quote rule (expected profit):

```
for each option o we could serve on time:
    c_o  = expected cost to move it (fee estimate + risk of lateness × expected refund + failure costs)
    p*   = argmax_p  P(win | p, lane, day, dealer, option) × (p − c_o)
quote the options whose best expected profit is positive and whose capacity cost (section 4) is covered;
otherwise quote ~3× list (a safe decline from level 4).
```

- **P(win | p)**: a logistic curve in `log(p / list)` with features for lane (pickup town, delivery town), weekday/hour, dealer, option. Fit offline on many practice worlds (wins/losses are in the reveal) to learn the **persistent lane part**; then update online during the week (each quote's win/loss) for the world level, the day factor and per-dealer drift. This is exactly what TacTex did for supply-chain RFQs (see `05-research`).
- **Explore early in the week:** the first hours' wins and losses reveal this world's price level. A few deliberately varied quotes on Monday morning are cheap information. **(hypothesis)**
- **Event detectors (hypotheses):**
  - *Outage*: our win rate in one region jumps while elsewhere it is normal ⇒ raise prices there for that day (backup is ~30% dearer).
  - *Price war*: win rate collapses everywhere at once ⇒ don't chase; keep only clearly profitable cars, or accept fewer wins that day.
- **Dealer trust**: favour on-time reliability for dealers we serve repeatedly; at 25 on-time orders a dealer accepts +25%. Never let a frequent dealer's car go late if a pricier rescue fee avoids it.
- **Don't take everything from one dealer**: the competitor cuts prices for dealers where we win most.

## 3. Fees (the driver side)

Facts:
- A gig = one or more legs in a fixed stop order; options: windows per stop, `withPlates` (+30 min), `withCharging` (+40 min), `audience` (everyone / experienced only: rating ≥ 4.8 and ≥ 50 gigs; manual-licence requirement), and a **fee schedule** of 1–48 non-decreasing steps (level 1: one step).
- Drivers have homes and days; cost = driving time + trip to pickup (cheap ticket bought ahead) + trip home (dearer, bought on the day) + extras (evening, weekend, private address, trade-in, charging, plates, disliked work). Overnight stays for far morning pickups cost them more.
- A driver books when fee − cost beats their other options **and what they expect from waiting**. Close to pickup they wait less.
- **Drivers learn our fees** (from level 2): when a gig of an order books, drivers who viewed it and could have done it learn (booked fee / first viewed fee) and (minutes from first view to booking). **A system that always raises teaches drivers to wait.** A repost at a higher fee counts as a raise; the order keeps its first viewed fee and its age.
- Notifications reach drivers whose **home is within 30 km** of the first pickup; no reading 23:00–07:00. Raises send no notification.
- Fees that **only just pay** get more **drops**; longer holds ⇒ more drops; a driver who dropped books again only for a higher fee.
- **Direct offers**: one gig to one driver for 10 min at our chosen fee; ≤ 3 per driver per day, ≤ 3 open per gig. A yes books immediately. Best for gigs whose fee drivers expect to rise, and for drivers a notification doesn't reach (e.g. a driver finishing one of our gigs nearby).
- We see positions of drivers while they work our gigs, every view (driver id + fee), bookings, drops; `GET /drivers` lists home town, rating, licence, completed gigs, past drops.
- At levels 7–8 a gig at the typical fee often finds no driver; level 8's shortage is uneven by town.

Proposed fee policy (hypotheses to test):
1. **Open near the expected clearing fee**, not low. Estimate it per (pickup region, delivery region, hour, weekday, level) from our own booking history: `booked fee / typical fee` and time-to-book. Fewer, larger steps beat many small raises (they teach waiting).
2. **Pay a margin above "just pays"** to cut drops; measure the drop rate per fee ratio.
3. **Direct offers to well-placed drivers**: drivers who will finish a gig of ours near the next pickup (chains), drivers living near the delivery place (their trip home is cheap), reliable drivers (high rating, few drops) for tight deadlines.
4. **Deadline escalation** driven by `lastPickupAt`: plan the schedule so that the fee reaches a level that clears **before** `deadline_close` (3 h before `lastPickupAt`), not after.
5. **Experienced audience only when needed** (premium cars, tight windows): it shrinks the pool.

## 4. Capacity: win only what drivers can move

At levels 7–8 drivers are the binding constraint. Treat each won car as consuming driver supply in its region and time slot.

- Estimate supply per town from the roster (homes) and, at level 8, from **observed views/bookings per region in the first hours** (the per-town shortage factor is new each world). **(hypothesis)**
- Add an **opportunity cost** to the quote's cost estimate when the region/time is already loaded with our orders; it rises steeply as we approach the on-time limit.
- Signs of a good request (from the handbook): goes **towards towns where drivers live**; pairs with an order we have or expect (a **return leg**, a **second car from the same yard**); starts in a busy area when many drivers are free; the dealer accepts a **later option** we can bundle. Bad: ends where no work comes back, needs a long trip to the pickup, falls when few drivers work, has a risky note.
- **Bulk order** (level ≥ 6): 30–40 cars from one yard. With few drivers this is 30–40 trips from one place; quote it only for the share we can move, or price it high.
- **Flu**: some weeks 30% of working drivers stay home for a day; watch bookings collapsing and slow down winning.

## 5. Bundling (multi-car gigs)

- Allowed from level 3. A multi-car gig may plan **≤ 12 hours of driving** (road minutes of the map, including driving between stops; plates/charging excluded). A single car has no limit.
- Trade-in: put the old car's pickup **right after** the new car's delivery in the same gig (then the customer's slot doesn't end the gig). If the two legs exceed 12 h, post two gigs.
- Bundles save the driver's trip to the pickup and the trip home: one driver moves car A to town X and car B from X back. This is the dispatcher's main structural advantage over the competitor ("the competitor knows nothing about your drivers, your other orders or your timing").
- Start with greedy pairing (same yard; delivery of A near pickup of B within windows) before reaching for a solver; measure the saving per bundle. A PDPTW solver (OR-Tools/PyVRP) is an option if greedy plateaus.

## 6. Notes and changes of plan (level ≥ 5)

- Notes are Finnish, Swedish or English. The world acts on what the note says whether or not we read it: a misread ready time ⇒ failed visit; a misread deadline ⇒ late car.
- The grammar is specified exactly in RULES "Notes and changes of plan": relative days (`tänään/idag/today`, `huomenna/i morgon/tomorrow/tmrw/imorgon`, `ylihuomenna/i övermorgon/the day after tomorrow`), weekday names = 2–6 days after arrival, 24-h digits unless am/pm, hours in words = working hour 9–17 ("two" = 14:00, "half three" = 14:30), corrections override, denied times don't count, several facts per note, `release` events for pay-before-pickup cars.
- Build a deterministic parser for that grammar and **score it against the reveal** (`legs.csv` contains the note's true deadline, ready time, release, gearbox, plates, real hours). An LLM is too slow for the live 4.5-second window per request, but fine offline to propose rules and label test cases.
- Handle `order_changed` (car sent elsewhere; we pay extra driving), `order_cancelled` (withdrawn / released / shortened / continues), `release`, `visit_failed` (not ready, closed, licence, no plates), `driver_late`, `no_show`, `gig_dropped`, `gig_expired`, `forecast` (snow slows driving and keeps some drivers home; deadlines can move).
- Handling rules: premium ⇒ experienced audience; EV < 30% and > 200 km ⇒ `withCharging`; plates ⇒ `withPlates`; manual gearbox ⇒ licence requirement.

## 7. Proposed architecture

```
state.py      World state rebuilt from snapshot + events (needed for the final's restart)
market.py     P(win | price) model: offline lane priors + online updates; event detectors
costs.py      Expected fee per leg/bundle, drop/late risk, capacity opportunity cost
quote.py      Expected-profit quote per option; decline rule
gigs.py       Bundling, fee schedules, direct offers, deadline escalation, reposts
notes.py      Note parser (grammar from RULES) + tests built from reveal data
run.py        Practice / board / final loops, rate limiting, batching (≤ 50 actions)
eval/         Parallel seed runner, results/runs.csv, reveal exporter, ablation tables
```

## 8. Build order

1. Eval harness + baseline numbers (starter) on 20 level-8 seeds.
2. **Capacity-aware decline** (stop winning what we can't move) ⇒ get above 90% on time at level 7/8. This alone should move us from a big loss toward break-even.
3. **Fee policy** (clearing-fee opening, fewer raises, escalation before `deadline_close`).
4. **Quote pricing** with a learned P(win) (lane priors from many practice worlds + online update).
5. **Bundling** (return legs, same yard, trade-ins).
6. **Notes parser** validated on reveals.
7. **Direct offers** to well-placed drivers.
8. **Event detectors** (outage, price war, flu, bulk) and **dealer trust** policy.
9. Final-readiness: restart/rejoin, stream reconnect, 429 handling, latency budget; rehearse in the test finals.

## 9. What to measure (and later show the jury)

- Per idea: margin/week and on-time % with vs without, on the same ≥ 20 level-8 weeks. Format the jury likes: "€X a week, against €Y for the starter, on the same 20 weeks at level 8".
- Win rate vs `price/list` by lane and day; booked fee / typical fee by region and hour; drop rate vs fee ratio; time-to-book vs fee.
- Our result in our best ranking round and in the final; what did not work; what would break the system.
