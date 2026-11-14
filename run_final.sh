#!/bin/sh
# Plays the final, or a test final, and starts the desk again at once if it ever stops.
# The desk rebuilds its books from the world, so a restart loses a few seconds, not the week.
#   ./run_final.sh
# Only one copy runs at a time: a second one would send every quote and gig twice.
mkdir -p results/logs/final
exec 9> results/logs/final/.lock
if ! flock -n 9; then
    echo "Another run_final.sh is already running here. This one stops."
    exit 1
fi
log="results/logs/final/$(date +%a-%H%M).log"
echo "Logging to $log"
until .venv/bin/python dispatch.py --final >> "$log" 2>&1; do
    echo "$(date +%T) the desk stopped; starting it again" | tee -a "$log"
    sleep 1
done
tail -3 "$log"
