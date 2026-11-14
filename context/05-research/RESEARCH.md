# Research: what already exists that maps onto Spread

Spread combines three classic problems: **bidding against a hidden competitor with only win/lose feedback** (dealer quotes), **posting a price to strategic, learning workers** (driver fees), and **pickup-and-delivery bundling under time windows** (multi-car gigs). Below are the most useful references for each, with what to take from them. None of these is required; they are shortcuts to good ideas and good words for the jury.

A search for public Spread solutions from other teams found nothing (expected on the first night).

## 1. Quoting against a competitor (dealer side)

**TacTex-05: A Champion Supply Chain Management Agent** — Pardoe & Stone, AAAI 2006.
<https://cdn.aaai.org/AAAI/2006/AAAI06-234.pdf> · more TacTex papers: <https://www.cs.utexas.edu/~TacTex/dpardoe/papers/TacTexChapter.pdf>, <https://www.cs.utexas.edu/~dpardoe/papers/SIGecom04.pdf>
The Trading Agent Competition (TAC SCM) is the closest past competition to Spread: agents receive customer RFQs, compete with other agents' bids, and must plan production capacity. TacTex's "Offer Acceptance Predictor" maps each possible price to a probability of acceptance (a regression fit on recent offers and their outcomes), and its demand manager chooses bids that maximise expected profit **jointly with capacity**, weighting each potential order by its acceptance probability. Take: the P(win | price) curve + expected-profit + capacity framing for our quote engine.

**Bid Shading by Win-Rate Estimation and Surplus Maximization** — arXiv 2009.09259.
<https://ar5iv.arxiv.org/html/2009.09259>
Estimate the win-rate curve from binary win/lose outcomes, then pick the bid that maximises (value − bid) × P(win). Our quote is the mirror image: maximise (price − cost) × P(win).

**Learning to Bid in Contextual First Price Auctions** — Google Research. <https://research.google/pubs/pub50822/>
**Optimal No-regret Learning in Repeated First-price Auctions** — arXiv 2003.09795. <https://arxiv.org/pdf/2003.09795>
Background on learning prices online with censored feedback, useful if we want principled exploration on Monday morning.

**Thompson Sampling for Dynamic Pricing** — Ferreira, Simchi-Levi, Wang, arXiv 1802.03050.
<https://arxiv.org/pdf/1802.03050>
A simple Bayesian explore/exploit rule for choosing prices when demand is unknown. Fits two places: early-week quote calibration (this world's price level) and opening fees per lane.

## 2. Paying freelance drivers (driver side)

**Pricing, bundling, and driver behavior in crowdsourced delivery** — Çınar, Archetti, Dullaert, Leitner, Waldherr, arXiv 2507.03634 (2025).
<https://arxiv.org/abs/2507.03634>
Jointly chooses bundles, which occasional driver gets each bundle, and the compensation. Driver acceptance is a **logistic function of pay and bundle attributes** (detour, bundle size) with behavioural driver classes. Shows the optimal compensation for a driver–bundle pair has a **closed form via the Lambert W function**, and that integrating pricing with bundling beats doing them in sequence. Take: model acceptance as logistic in fee per driver segment; price bundles, not just legs; the closed-form fee is a neat, explainable formula for the jury.

**Optimizing Last-Mile Delivery: A Dynamic Compensation Strategy for Occasional Drivers** — Schur & Winheller, OR Spectrum 2024.
<https://link.springer.com/article/10.1007/s00291-024-00796-6> · PDF: <https://www.pl.msm.uni-due.de/fileadmin/Dateien/PL/Optimizing_Last_Mile_Delivery__A_Dynamic_Compensation_Strategy_for_Occasional_Drivers.pdf>
Dynamic programming that offers each arriving driver an individual task + compensation, treating the driver's acceptance threshold as random and pricing against the avoided cost. Maps to our direct offers and fee schedules over time.

**Intertemporal Pricing with Strategic Customer Behavior** — Xuanming Su, Management Science 53(5), 2007.
<https://econpapers.repec.org/RePEc:inm:ormnsc:v:53:y:2007:i:5:p:726-741>
Why customers who expect prices to move wait, and how that changes optimal pricing paths. Spread drivers do exactly this ("a system that always raises its fees teaches drivers to wait"). Take: commit to fewer, decisive raises; consider opening at the clearing fee.

## 3. Bundling cars into gigs (routing)

**Google OR-Tools — pickup and delivery / VRP with time windows.**
<https://developers.google.cn/optimization/routing/pickup_delivery?hl=en>, <https://developers.google.com/optimization/routing/vrptw>
Pickup-and-delivery with precedence and time windows, plus a duration dimension (our 12-hour driving cap).

**PyVRP** — open-source state-of-the-art VRP solver (Python). <https://github.com/PyVRP/PyVRP> · docs <https://pyvrp.org/> · pickup/delivery ("shipments") example: <https://pyvrp.org/notebooks/shipments.html>

Practical advice: our bundles are small (2–4 cars). Start with greedy pairing (return legs, same yard, delivery near next pickup within windows) using the map's road minutes; only bring in a solver if greedy plateaus. The map (`places.csv`, `roads.csv` from the reveal export, or the map endpoint) already gives road minutes, so no OSRM or external routing is needed.

## 4. Reading the dealers' notes

**dateparser** — multilingual date parsing for Python. <https://github.com/scrapinghub/dateparser> · docs <https://dateparser.readthedocs.io/>
Helpful as a reference, but the rules define the note grammar exactly (relative day words in Finnish/Swedish/English, weekday = 2–6 days ahead, hours in words = working hours 9–17, "half three" = 14:30, corrections override, denials don't count). A small deterministic parser written to that spec, tested against the reveal's ground truth (`legs.csv`), will beat a general library. Use an LLM **offline** to label notes and suggest patterns; the live final gives ~4.5 real seconds per request.

## 5. Tooling for the weekend

- **Optuna** for parameter sweeps over seeds (e.g. fee ratios, decline thresholds): <https://optuna.org>. Optimise the mean margin on a fixed seed set subject to on-time ≥ 93%.
- **pandas / DuckDB** for the reveal CSVs.
- The kit's own tools: `spread-reveal-csv` / `reveal-csv.ts`, the run viewer at `$SPREAD_URL/viewer/` (orders sorted worst margin first, replay on a map), `fork` for A/B decisions on the same future.

## 6. Questions the handbook itself suggests starting with

- At what price against the list price do our quotes start to lose, by lane and by day?
- At what fee, and how long after posting, do the gigs of a lane get booked?
- Which notes did our reader get wrong?
