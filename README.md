# DaVinci's Night Shift: a dispatcher for Spread

Spread is Bahn Express's challenge at Junction 2026: one simulated week of a car transport company in Finland. Dealers ask for prices, and a competitor answers them too. Each car that we win needs a freelance driver, found by posting a gig with a fee. The score is the gross margin, and a team is ranked only when at least 90% of its orders arrive on time.

This repository is our system (`desk/`), the harness that measures it (`eval/`), and the log of every week it has played (`results/runs.csv`).

## Result

Level 8, mean margin a week on the same 20 practice weeks (`eval-01` to `eval-20`). Each row adds to the one above.

| Version | What it adds | Margin a week | On time | Lowest week |
|---|---|---|---|---|
| `starter` | The kit starter | −€66,760 | 51.0% | 38.3% |
| `v2` | Prices by expected profit, from two fitted curves | €9,039 | 96.3% | 91.8% |
| `v5-notes` | A reader for the dealers' notes | €11,725 | 96.6% | 92.7% |
| `v8` | Return-trip pairs, the day with few drivers, the guard | €12,963 | 97.5% | 94.3% |
| `v9` | A wider radius for pairs | €14,027 | 97.7% | 95.5% |
| `v11` | Prices 6% above the curve's choice | €14,785 | 98.1% | 95.6% |
| `v12` | No low prices to buy trust; a lower minimum chance | €16,177 | 97.4% | 95.2% |
| `v13` | Fee raises before the last hours | €16,467 | 97.7% | 93.0% |
| `v15` | Riskier cars while the week has on-time share to spare | €17,384 | 97.2% | 92.8% |
| `v16` | Trade-ins | €17,363 | 97.1% | 93.1% |
| `v17` | A market learner that follows the competitor's own moves | €17,408 | 96.8% | 93.6% |
| `v18` | The easiest cars open at a lower fee | €17,508 | 97.2% | 93.3% |

On weeks that no setting was tuned on, `v18` makes €17,690 a week at 97.4% on time (20 weeks, `hold-01` to `hold-20`, lowest week 93.7%).

A gain of a few hundred euros a week does not show on 40 weeks: there the standard error of a difference is €150 to €200. So 80 more weeks (`more-01` to `more-80`) judge the last two steps. On all 120 weeks:

| Version | Margin a week | On time | Lowest week | Late cars a week |
|---|---|---|---|---|
| `v16` | €16,709 | 96.7% | 91.6% | 13.0 |
| `v17` | €17,023 | 96.9% | 91.5% | 12.2 |
| `v18` | €17,256 | 97.2% | 93.2% | 11.3 |

`v17` makes €314 a week more than `v16` (standard error €105), and `v18` €233 more than `v17` (standard error €99). Together: €546 (standard error €125), better on 80 of the 120 weeks. All 120 weeks are ranked.

The 40 weeks that the settings were tuned on flatter them. `v18` makes €17,599 a week on those 40 and €17,084 on the 80 new ones, at 97.1% on time. The second number is the one to expect. The rhythm test under Robustness shows the same thing from another side: on the tuned weeks, any change of rhythm looks like a loss.

Ranking rounds at level 8, five secret weeks each:

| Round | Version | Five weeks | On time |
|---|---|---|---|
| Saturday 00:00 | `v11` | €74,742 | 97.6% |
| Saturday 09:00 | `v16` | €77,573 | 97.2% |
| Saturday 12:00 | `v17` | €99,211 | 97.8% |

In the Saturday 09:00 round this was the second highest total of the 68 teams that played it. The highest was €79,003. In the Saturday 12:00 round it was the highest of the 34 teams that had finished when we played, at 12:34. The second was €98,990.

The same code, not tuned for them, also played the Saturday 12:00 round at levels 2 to 7, and every week is ranked: first of 19 at level 7 (€54,251), third of 8 at level 5, fourth at levels 2, 3 and 4, and 13th of 18 at level 6. Level 1 was not played: there the desk is at 89% on time in practice.

## How it decides

Two estimates, and one rule that uses them.

**The chance that a driver takes a car in time.** A logistic curve on what a dispatcher knows at the quote: the awake hours until the last pickup, the length of the drive, the fee over the typical fee, the drivers who live within 100 km of each end, and how many of our orders already wait for a driver. It is fitted on 29,597 orders from 80 weeks that we played with random prices and fees (`analysis/fit.py`).

**The chance that a dealer takes a price.** A logistic curve in the log of the price over the list price, divided by the dealer's trust: 1% for each order that we delivered to it on time, as the rules say and as the fit confirms. Each lane has a level that holds in every world. The day's level does not hold: the desk learns it from each quote that wins or loses, one step of Bayes at a time, and widens its belief each morning. A price war shows as a low level within the first quotes of its day. The same step of Bayes also learns this week's own parts of the competitor's prices: a tilt by the lane's length, and a level for each pickup place and each delivery place.

**The rule.** For each option of a request, the desk picks the opening fee with the lowest expected cost among the fees at which a driver comes in time often enough. Then it quotes the price with the highest expected profit: the chance that the dealer takes it, times what it leaves after that cost. An option without such a fee gets no price.

On top of that, each idea below has a reason and a measured effect, on the same weeks with and without it.

| Idea | Why | Effect a week |
|---|---|---|
| Read the notes | A note can move the ready time, the real opening hours, the deadline, or ask for plates or a manual licence. The world acts on it. The reader gets 99.97% of 3,963 unseen notes right, and says when it is unsure. | +€1,850; failed visits fall from €515 to €5 |
| A gig covers one day when the note gives hours | A stop's window is one stretch of time, and opening hours hold every day. | part of the row above |
| Return-trip pairs | Two cars in one gig, the second starting within 60 minutes of the first's delivery and ending within 120 minutes of its pickup. The driver needs no trip to a pickup and no trip home, so the pair goes at 0.75 of the two typical fees. 78% are booked within an hour. | +€1,224, then +€1,064 for the wider radius |
| The day with few drivers | In every week, on one night, 8 to 24 drivers give their bookings back just after midnight. That day causes 40% of all late cars. The desk sees the burst, stops pricing cars that need a pickup that day, and raises the fees of the day's cars in the morning. | on time 96.4% to 96.9%, margin unchanged |
| The guard | Up to a quarter of the cars due on such a day are late. So the desk never holds more cars due on one day than the week can afford to lose a quarter of. | lowest of 40 weeks: 91.3% to 94.1%, margin unchanged |
| Prices 6% above the curve's choice | A 6% higher price lost 13% of the orders, where the curve said 24%. | +€758 |
| No low prices to buy trust | Pricing low to win an order and its trust point loses more than the trust returns. | +€368 |
| A lower minimum chance | The curve is cautious: it says 94.7% in time where 97.3% are. So the desk asks it for 0.84, not 0.90, and lets more orders wait for a driver. | +€1,024 on top of the row above |
| Fee raises before the last hours | A gig that is not taken at its opening fee goes up in two steps before the steep last hours. | +€448, and more cars on time |
| Riskier cars while there is room | Long lanes earn €80 to €100 a car. The desk takes them, and others, at a lower chance only while the week's late share is under 3%. | +€367 and +€345 |
| The competitor's own moves | The handbook says how the competitor's prices move in a week: once, its price list changes shape, so short and long lanes move in opposite directions, and some mornings its prices for cars leaving a place, or arriving there, move a step. The learner has one part for each. On 80 weeks with random prices it predicts the next answer 3.9% better. | +€314 on 120 weeks, and 0.8 fewer late cars a week |
| The easiest cars open lower | In 80 weeks with random opening fees, the cars of which 94 in 100 book at 0.85 of the typical fee cost 0.85 in the end when they opened at 0.70, and 0.93 when they opened at 0.85. For other cars a lower opening fee saves nothing and makes more of them late. So only these cars may open at 0.72. Their expected cost falls, so does their price, and the desk wins more of them. | +€233 on 120 weeks, 0.9 fewer late cars a week, lowest week 91.5% to 93.2% |
| Trade-ins | Their list price is 1.9 times the typical fee, against 1.1 for other cars. The world lets a driver bring the new car after the customer's booked hour, so the gig carries its own window on that stop: 94% arrive inside it. | +€204 |

## What did not work

Each of these is in `results/runs.csv` under the label in brackets, and is off in the settings.

- Direct offers to a driver who has just delivered near an open gig: none of 6,491 offers was accepted (`explore-offers`).
- A detector for the region where the competitor is down for a day: it finds the region in 18 of 20 weeks, but mostly in the afternoon, too late to earn (`v9-outage`).
- A lower fee for a gig's first minutes (`i-*`), and a higher fee right after a driver gives a gig back (`o-drop*`).
- A lower price when the car pairs with a waiting order: the pair seldom forms (`v10-pairquote`).
- A level for each dealer (`d-sd*`), a price factor by lane length (`h-*`), a dearer same-day option (`o-fast*`), a flatter or steeper dealer curve (`k-*`).
- Driver curves with products of their features: they rank orders better on paper (AUC 0.869 against 0.851) and make less in play (`v17b`, `n-*`).
- Two beliefs about the day's price level each morning, an ordinary day and a price war day: €430 to €640 a week less than the single belief that starts from yesterday (`m-regimes*`).
- A pickup window that ends before the last pickup minute, so that a drive that runs long still ends in time: no more cars on time, €120 to €235 a week less (`b-*`).
- A lower minimum chance for private addresses (`pv-*`), and other shapes of the fee raises (`r-*`).
- A new car that stays off the app for 30 to 120 minutes, so that a return car that we win later still finds it as a partner: 15 more pairs a week, and €65 to €314 a week less. A pair saves little against two easy cars, which book alone at 0.85 of the typical fee (`pi-*`).
- Town effects in the driver curves: 1.3% better on paper, no gain on 120 weeks (`t-towns`).
- Direct offers to the drivers who looked at a gig and did not book it: 15 of 959 were accepted, and 2 of 331 at the fee in the app. A driver who looks and leaves needs a higher fee (`w-vo-smoke`).
- A driver level learned during the week, as the dealers' level is: it predicts the next gigs worse than the fixed curve, because a quick booking is known at once and a gig without a driver only hours later.
- A lower or a higher price factor with the new learner: €321 and €489 a week less (`qg-103`, `qg-109`).
- A guard that counts on fewer orders when the week wins them at a slow pace: it changed 5 of 80 weeks and did not lift the lowest ones (`qp-pace`).
- A higher opening fee, 1.00, for the cars that book least easily. The randomised weeks, which had no fee raises before the last hours, said it would get more of them a driver in time. With our two raises it does not: €292 a week less, on time unchanged (`qh-75`).
- A level for each dealer in the new learner: no gain, as before (`qd-03`).
- The lower opening fee for other shares than 94 in 100. From 97 in 100: no gain. From 90 in 100: €59 a week, and one of 79 weeks falls to 89.3% on time. From 85 in 100: €111 a week less (`qe-97`, `qe-90`, `qe-85`). The randomised weeks say the same: below 94 in 100 a lower opening fee saves nothing.

## What would break it

- The curves are fitted on level 8 weeks. At other levels the desk is ranked but not tuned.
- The guard assumes one day with few drivers a week and a loss of a quarter of that day's cars. Two such days, or a worse one, would cost on-time share.
- The live loop has run on practice worlds with a moving clock, restarts included. It has not yet played a final.

## Run it

Python 3.9 or later. The team key goes in `.env`, which git ignores.

```sh
python3 -m venv .venv
.venv/bin/pip install context/02-kits/spread-0.1.0-py3-none-any.whl pandas scikit-learn
printf 'SPREAD_URL=https://spread.bahnexpress.com\nSPREAD_KEY=<team key>\n' > .env

.venv/bin/python dispatch.py --level 8 --seed eval-01          # one practice week
.venv/bin/python -m eval.run --label try --set l8              # the 20 tuning weeks, 8 at a time
.venv/bin/python -m eval.compare v18 try                       # week by week against a version in the log
./play_ranking_round.sh 8                                      # the five weeks of the current ranking round
./run_final.sh                                                 # the final or a test final: waits, plays, restarts itself
```

`pandas` and `scikit-learn` are needed only for `analysis/`. The desk itself uses the kit and the standard library.

## What is where

| Path | What it is |
|---|---|
| `desk/desk.py` | The decisions, and every setting with the measurement behind it |
| `desk/books.py` | What the desk knows, kept from the world's events alone |
| `desk/model.py`, `desk/fitted.json` | The driver curves and their coefficients |
| `desk/market.py` | The dealer curve and the day's level |
| `desk/notes.py`, `desk/words.txt` | The note reader, and the words that it repairs typos against |
| `desk/play.py`, `desk/live.py` | The loops: a practice world, and the live final |
| `eval/` | The harness: fixed weeks, parallel runs, the log, the comparison |
| `analysis/` | Fits the curves, scores the note reader |
| `results/runs.csv` | One row for each week played: over 5,000 weeks under 170 labels so far |
| `context/` | The challenge's rules, handbook and kits, and our first notes |

## Robustness

- The desk rebuilds its books from the world's event history and its own list of orders and gigs. With lost requests and lost answers injected into every kind of call, four weeks scored the same as without (`flaky` tests).
- A full rehearsal of the live loop from Thursday 00:00 to the world's end, at three times the final's pace and with two restarts, made €5,783 at 96.9% on time. The same half-week in practice mode made €5,622 at 95.0%.
- One look at the books takes 40 ms on average and 0.33 s at worst. A request waits 4.5 s.
- The live loop keeps the rhythm of the practice weeks: a look at once after an event that cannot wait, and else every 12 minutes of the world. Every measurement here was made at that rhythm, so the final plays at it too. A quote never waits past 6 world minutes before its deadline. How much the rhythm itself is worth is not settled: on the 40 weeks that the settings were tuned on, a look every 3, 9 or 10 minutes makes €200 to €400 a week less, but on 80 fresh weeks a look every 10 minutes makes €127 less with a standard error of €138 (`qt-3`, `qt-9`, `qt-10`).
