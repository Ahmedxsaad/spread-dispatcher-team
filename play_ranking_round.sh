#!/bin/sh
# Plays the current ranking round at one level: its five secret weeks, one after another.
# A ranking run counts in the public practice rankings, so a person starts this, not the agent.
#   ./play_ranking_round.sh        level 8
#   ./play_ranking_round.sh 7      another level
level="${1:-8}"
mkdir -p results/logs/ranking
stamp="$(date +%a-%H%M)"
for run in 1 2 3 4 5; do
    log="results/logs/ranking/$stamp-L$level-run$run.log"
    .venv/bin/python dispatch.py --level "$level" --board > "$log" 2>&1
    tail -2 "$log"
done
