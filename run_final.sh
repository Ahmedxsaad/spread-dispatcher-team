#!/bin/sh
# Plays the final, or a test final, and starts the desk again at once if it ever stops.
# The desk rebuilds its books from the world, so a restart loses a few seconds, not the week.
#   ./run_final.sh
mkdir -p results/logs/final
log="results/logs/final/$(date +%a-%H%M).log"
echo "Logging to $log"
until .venv/bin/python dispatch.py --final >> "$log" 2>&1; do
    echo "$(date +%T) the desk stopped; starting it again" | tee -a "$log"
    sleep 1
done
tail -3 "$log"
