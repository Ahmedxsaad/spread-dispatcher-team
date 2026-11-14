"""The eval harness: plays one version of the system on fixed practice weeks, several at a time,
logs each week to results/runs.csv and exports its reveal. See run.py and compare.py."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# SPREAD_RESULTS sends a trial run elsewhere, so it does not write into the evidence log.
RESULTS = Path(os.environ.get("SPREAD_RESULTS") or ROOT / "results")
RUNS_CSV = RESULTS / "runs.csv"


def load_env(path: Path = ROOT / ".env") -> None:
    """Reads the KEY=value lines of .env into the environment, so the team key stays out of the code
    and the shell history. A variable that is already set wins."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, equals, value = line.strip().removeprefix("export ").partition("=")
        if equals and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))
