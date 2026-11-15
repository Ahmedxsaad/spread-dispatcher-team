# CLAUDE.md — Spread (Bahn Express) dispatcher · Junction 2026

You are the lead engineer on a hackathon team building a system for **Spread**, Bahn Express's challenge at Junction 2026. Read this file first, then `context/01-official-docs/RULES.md` in full. Where any document disagrees with `RULES.md`, `RULES.md` wins.

## The mission in one paragraph

Spread is a simulated week of a car-transport company in Finland. Our system quotes prices to car dealers (who also ask a competitor) and posts the won cars as gigs to freelance drivers, choosing the fee and how it rises. **Score = gross margin in euros** (what dealers pay minus driver fees, refunds, fines). **Hard gate: at least 90% of won orders on time**, or we are not ranked. The **final** is one secret **level 8** week on **Sunday 15 Nov 09:00 Helsinki time** (moved from 08:00; set at 08:30, registration closes 08:30), running by itself for ~34 minutes. The **10 ranked teams with the highest margin** go to a jury, which then judges only how **elegant, clear, creative and robust** the system is, with **measured evidence** for each idea. So: (1) get into the top 10 in the final, (2) be able to explain and prove every big idea.

## Targets

- On-time share: aim for **≥ 93%** in practice, never plan to sit at 90%. The final is a single week, so variance is real.
- Margin: the house reference "House best" scored **€60,449 over 5 level-8 ranking weeks (~€12k/week) at 94.2% on time** in the Friday 20:01 round. The kit starter loses tens of thousands per level-8 week. See `context/03-leaderboard/LEADERBOARD.md` for the live picture when this pack was made.
- Engineering: the system must survive restarts, a slow network and rate limits in the live final.

## Folder map

| Path | What it is |
|---|---|
| `context/01-official-docs/` | Verbatim copies: `RULES.md` (authoritative), `HANDBOOK.md`, `API.md`, `openapi.json`, `llms.txt`, plus the site's `how-it-works.md` and `judging.md` pages |
| `context/02-kits/` | Official kits: original archives plus unpacked `typescript/` and `python/spread/` source |
| `context/03-leaderboard/` | Snapshot of the practice rankings (all 8 levels) and the final endpoint, as JSON + a readable summary |
| `context/04-strategy/STRATEGY.md` | Our analysis of the levers, a proposed architecture, and the experiment plan |
| `context/04-strategy/TIMELINE.md` | Weekend schedule, checklists and the final-morning runbook |
| `context/04-strategy/TECH-PARTNERS.md` | Which Junction tech challenges (side prizes) fit this project, and the rule that nothing may risk the live final |
| `context/05-research/RESEARCH.md` | Papers, libraries and techniques that map onto this problem, with links |
| `context/06-junction/` | The Junction challenge page for Spread (prizes, event code, submission requirements) |

## Setup

1. A human creates the team at `https://spread.bahnexpress.com/join` with the event code in `context/06-junction/`. That gives a **team key**.
2. Environment: `SPREAD_URL=https://spread.bahnexpress.com`, `SPREAD_KEY=<team key>`. **Never commit the key**; read it from the environment or a git-ignored `.env`.
3. Pick one kit and stay with it:
   - **Python ≥ 3.9** (recommended for this team: pandas/numpy for the reveal CSVs and tuning): `pip install $SPREAD_URL/kit/spread-0.1.0-py3-none-any.whl`, then copy the starter out of the package: `cp "$(python -c 'import spread.starter as s; print(s.__file__)')" dispatch.py`. The unpacked source is in `context/02-kits/python/spread/` for reading.
   - **TypeScript** (Bun or Node ≥ 22.18, no dependencies): source in `context/02-kits/typescript/`, run `bun starter.ts`.
4. Run the starter once at `--level 1` to see the loop work, then read `starter.py` / `starter.ts` end to end (about 200 lines of logic). It already does: quote at list price, post at typical fee with hourly raises, keyword note parsing, reposting after failures/expiry, steep fees after a deadline warning, and rejoining a running final from snapshot + events.
5. Junction rule: **all code must be written at the event** (open-source libraries are fine). The repo is MIT-licensed on submission.

## How the API works (short)

- Practice worlds stand still until you call `advance`; one `advance` request can carry the step's actions. Same seed + level + actions ⇒ identical week (deterministic). `fork` copies a world to try two decisions on the same future. `reveal` after a world ends gives CSV-able truth about your own quotes, won cars and gig views (`spread-reveal-csv <world id>` / `bun reveal-csv.ts`).
- Limits: batch ≤ 50 actions; ≤ 8 unfinished practice worlds; ≤ 16 streams. Practice requests share a token bucket (1,000/s quiet, ~170/s with 60 teams, ~50/s with 200, 20/s during a final). In the final: actions 20/s, reads 50/s; over the limit ⇒ HTTP 429 (the clients read `RateLimit` headers).
- Ranking runs (`create(level, board=True)`, starter `--board`): 5 secret worlds per level per round, identical for every team, cannot be forked or revealed. Rounds open Fri 19:30; Sat 00/09/12/15/18/21; Sun 00/03/06. **They do not count for the final**; they show where we stand.
- Live final: weekday hour = 18 real seconds (06–22), so a price request's 15-minute response window is **~4.5 real seconds**. If our code stops, the world continues (requests go to the competitor). Rebuild state from `snapshot()` + `events()` on start, read events from `stream()`.

## How to work

1. **Make it run, level by level.** Level 1→3 (posting, fee schedules, multi-car gigs, direct offers; every quote wins at list price), 4 (competitor), 5 (notes, changes, weather, handling rules), 6 (outage, flu, bulk order), 7 (driver shortage), 8 (uneven shortage, price war, dealer trust). The final is level 8; spend most tuning time there once the basics work.
2. **Fixed evaluation set.** Keep a list of ≥ 20 level-8 seeds (e.g. `eval-01`…`eval-20`) and a few level-6/7 seeds. Every change is judged on the same seeds, run in parallel (8 slots). Log every run to `results/runs.csv` (git commit, config, seed, level, margin, on-time %, orders won, late, undelivered). This log becomes the jury's evidence.
3. **One idea at a time, with an ablation.** For each idea record margin and on-time with and without it on the same weeks. The jury explicitly asks for "the idea, why, and the effect".
4. **Use reveals.** After each eval run, export the reveal CSVs and study: where quotes start losing vs list price (by lane, day, dealer), at what fee and delay gigs book per lane/hour, which notes were misread, which orders lost money (the run viewer at `$SPREAD_URL/viewer/` sorts orders worst margin first).
5. **Play ranking rounds** whenever a new round opens and the system is better than last time, to compare with other teams and House best.
6. **Rehearse the live clock** in the test finals (Sat 14:00 and 20:00 Helsinki). Measure quote latency, 429s, reconnects, restart-rejoin.

## Design principles (keep the jury in mind)

- Few parts, each with a stated reason and a measured effect. Prefer a clear formula over a pile of special cases.
- Use the challenge's words in code and slides: dealer, request, option, quote, order, leg, gig, fee, typical fee, deadline, direct offer.
- Separate **estimation** (what will this car cost to move? what is P(win) at this price?) from **decision** (quote/fee/bundle choices). It makes ablations easy.
- Everything in cents and whole minutes, as the API requires.
- Determinism: seed any randomness, so practice results are reproducible.

## Next actions for you

1. Read `RULES.md`, then `HANDBOOK.md` ("How the world works", "Research"), then `API.md`.
2. Read the kit starter; run it at levels 1, 4, 6 and 8 on two seeds; save the baseline numbers to `results/runs.csv`.
3. Build the eval harness (parallel seeds, CSV logging, reveal export) before changing strategy.
4. Then follow the build order in `context/04-strategy/STRATEGY.md`.
