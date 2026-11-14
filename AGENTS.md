# For an agent working in this repository

This is the team's dispatcher for Spread, Bahn Express's challenge at Junction 2026. The final is one secret level 8 week on Sunday 15 November at 08:00 Helsinki time. The ten ranked teams with the highest margin go to a jury.

Read `README.md` first. It has the results, each idea with its measured effect, and a long list of what did not work. Do not test again what is in that list unless you have a reason that the list does not answer.

## Rules that protect the final

1. **Never start the final or a ranking run.** Do not run `run_final.sh`, `dispatch.py --final`, `dispatch.py --board` or `play_ranking_round.sh`. One machine plays the final, and a second one would send every quote and every gig twice. A ranking run is public and can be played once per round.
2. **The team key stays out of git and out of the issues.** It goes in your own `.env`, which git ignores. Ask a teammate for it in private.
3. **The team shares 8 practice worlds.** Every run of every teammate counts against them. Run the harness with `--workers 2`, so several people can test at the same time. A run that waits for a free world is normal.
4. **Do not change a default in `desk/desk.py` on `main`.** Add your idea as a setting that is off by default, and show its effect with `--config`. A default changes only after the evidence below.
5. **Do not edit `desk/` while one of your own runs is playing.** Each week starts in a fresh process and loads the code as it is at that moment.

## How to test an idea

```sh
python3 -m venv .venv
.venv/bin/pip install context/02-kits/spread-0.1.0-py3-none-any.whl pandas
printf 'SPREAD_URL=https://spread.bahnexpress.com\nSPREAD_KEY=<team key>\n' > .env

# 80 practice weeks with your setting, two at a time, then the comparison with version 20
.venv/bin/python -m eval.run --label <your-label> --set l8-more --no-reveal --workers 2 --config your_setting=value
.venv/bin/python -m eval.compare gv-a <your-label>
```

- `gv-a` is version 20, the current default, on every set of weeks. Its rows are in `results/runs.csv`.
- Practice weeks are deterministic: the same seed, level and actions give the same week. So a comparison is paired, week by week.
- Give each run its own label, with your initials in it, for example `xy-pairs-wide`.
- A first look can use 16 weeks (`--level 8 --seeds more-01,more-02,...`). A decision needs all 80.

## What counts as evidence

- The gain is at least twice its standard error on `l8-more` (80 weeks). On 40 weeks a difference of €200 a week is noise.
- The lowest week's on-time share does not fall. A team under 90% on time is not ranked, and the final is one week.
- Then one confirmation on `l8-check` (80 weeks that no setting was chosen on). Never choose a value on `l8-check`.
- The 40 weeks of `l8` and `l8-holdout` flatter the settings, because every setting was tuned on them. Do not judge on them alone.

## Where the discussion happens

In the issues of this repository. One idea per issue.

- Say what the idea is, why it should work in this world (quote the handbook in `context/01-official-docs/` when it helps), and what you measured: the output of `eval.compare`, the label, and the settings.
- A result that shows no gain is worth posting. It saves the next person the run.
- Push your code on a branch named after your label and link it in the issue. Leave `results/runs.csv` on `main` alone: post your numbers in the issue.
- Write for a reader who has not seen your session: full sentences, the numbers with their units, no private shorthand.

## Where things are

| Path | What it is |
|---|---|
| `desk/desk.py` | The decisions, and `SETTINGS`: every setting with the measurement behind its value |
| `desk/market.py` | The learner of the competitor's prices |
| `desk/model.py`, `desk/fitted.json` | The fitted curves: a driver in time, a dealer's answer, each lane's pair share |
| `desk/live.py` | The loop of the live final. Do not change it without a live rehearsal on a practice world |
| `eval/` | The harness: `eval.run`, `eval.compare`, the sets of weeks in `eval/seeds.py` |
| `analysis/` | The fits behind `desk/fitted.json` |
| `results/runs.csv` | Every week that every version has played |
| `context/01-official-docs/` | The rules, the handbook and the API, as the organisers wrote them |
