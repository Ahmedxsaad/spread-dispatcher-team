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

On weeks that no setting was tuned on, `v16` makes €17,172 a week at 97.1% on time (20 weeks, `hold-01` to `hold-20`, lowest week 94.1%). All 40 weeks are ranked.

Ranking rounds at level 8, five secret weeks each:

| Round | Version | Five weeks | On time |
|---|---|---|---|
| Saturday 00:00 | `v11` | €74,742 | 97.6% |
| Saturday 09:00 | `v16` | €77,573 | 97.2% |

In the Saturday 09:00 round this was the highest total of the 31 teams that had finished when we played, at 09:40.

## How it decides

Two estimates, and one rule that uses them.

**The chance that a driver takes a car in time.** A logistic curve on what a dispatcher knows at the quote: the awake hours until the last pickup, the length of the drive, the fee over the typical fee, the drivers who live within 100 km of each end, and how many of our orders already wait for a driver. It is fitted on 29,597 orders from 80 weeks that we played with random prices and fees (`analysis/fit.py`).

**The chance that a dealer takes a price.** A logistic curve in the log of the price over the list price, divided by the dealer's trust: 1% for each order that we delivered to it on time, as the rules say and as the fit confirms. Each lane has a level that holds in every world. The day's level does not hold: the desk learns it from each quote that wins or loses, one step of Bayes at a time, and widens its belief each morning. A price war shows as a low level within the first quotes of its day.

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
.venv/bin/python -m eval.compare v16 try                       # week by week against a version in the log
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
| `results/runs.csv` | One row for each week played: 4,210 weeks under 148 labels so far |
| `context/` | The challenge's rules, handbook and kits, and our first notes |

## Robustness

- The desk rebuilds its books from the world's event history and its own list of orders and gigs. With lost requests and lost answers injected into every kind of call, four weeks scored the same as without (`flaky` tests).
- A full rehearsal of the live loop from Thursday 00:00 to the world's end, at three times the final's pace and with two restarts, made €5,783 at 96.9% on time. The same half-week in practice mode made €5,622 at 95.0%.
- One look at the books takes 40 ms on average and 0.33 s at worst. A request waits 4.5 s.
