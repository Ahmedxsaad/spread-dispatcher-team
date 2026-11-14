# Runbook: playing a final

The final is one level 8 week on Sunday 15 November at 08:00 Helsinki time. The organisers set it at 07:30. It runs by itself for about 34 minutes. A test final works the same way and takes about 19 minutes.

## Where the final is played from

`../spread-final/` is a separate copy of this repository with its own `.venv` and `.env`. Experiments here cannot change what plays there. Only a `git pull` in that folder changes it.

```sh
cd ../spread-final
git log --oneline | head -1          # the version that will play
git status --short                   # must print nothing
```

## Start

Start the runner before 07:30. One runner at a time: a second one stops at once and says so.

```sh
cd ../spread-final
systemd-inhibit --what=sleep:idle --who="Spread final" --why="The desk is playing a final" ./run_final.sh
```

It waits for the final, joins it, plays it, and starts again by itself if it dies. It ends when the final ends. Its log is `results/logs/final/<day>-<HHMM>.log`.

## What a healthy run looks like

```sh
tail -f results/logs/final/*.log
```

| When | The log says |
|---|---|
| Before the final is set | `No final is set. Waiting for it` |
| From 07:30 | `Final world <id>.`, then `Mon 00:00 joined world <id>: 0 orders in hand ...` |
| During the final | One line for each day of the week: margin, orders, on-time share, cars without a driver |
| At the end | `End  margin € ...` and `Ranked.` |

Lines that are harmless: `withdraw refused: Gig ... is not open` and `pair refused` (a driver booked the gig in the same second), `Joining again in 3 seconds` (the server restarted; the desk rebuilds its books and goes on).

Lines that need a look: `a look failed` more than a few times, `quote refused: Request ... is not open` more than a few times (quotes arrive too late: check the network), a Python traceback that repeats.

The public feed shows every team during the final: `https://spread.bahnexpress.com/v1/leaderboard`.

## If something goes wrong

| What you see | What to do |
|---|---|
| The runner is not running | Start it again with the command above. It rebuilds its books from the world's events and its own journal of quotes, and goes on. |
| `Another run_final.sh is already running` | Good: one is running. Do not start another. |
| The laptop lost the network | Reconnect. The runner keeps trying and rejoins by itself. |
| The log stands still for more than a minute during the final | Press Ctrl-C once and start the runner again. |

While the desk is down the world goes on: gigs keep their fee schedules, booked drivers keep working, and new requests go to the competitor. A restart costs the requests of those seconds, nothing else.

## Before the final: checklist

- The laptop is on mains power, on the best network available, with the lid open.
- `git log` in `../spread-final/` shows the version chosen on Saturday evening, and `git status --short` prints nothing.
- No evaluation is running here (`pgrep -af "eval.run"` prints nothing): a final slows practice worlds, and they slow the laptop.
- The team key in `../spread-final/.env` is the team's own.

## After the final

- The result is the last lines of the log and the public feed.
- For the Junction submission (final by Sunday 10:00): the submission hash from the team page on the Spread site, the link to the code, the slides or video.
