"""results/runs.csv: one row for each practice week that a version of the system played. It is
the evidence for every claim about an idea: its margin and on-time share with and without it, on
the same weeks."""
from __future__ import annotations

import csv
import fcntl
from statistics import mean

from . import RESULTS, RUNS_CSV

FIELDS = [
    "ts",  # when the week ended, UTC
    "label",  # the name of this version of the system
    "strategy",  # the module that played
    "git_commit",  # with "+" when files differed from the commit; "nogit" outside a repository
    "code_hash",  # a hash of the system's source files: the same hash and config played the same code
    "config",  # JSON
    "level", "seed", "world_id",  # the week; the world id opens it in the run viewer
    "status",  # ok or error
    "ranked",  # 1 when the week meets the delivery minimum: 90% of the won orders on time
    "margin_eur", "revenue_eur", "on_time_pct",
    "won", "on_time", "late", "undelivered",  # orders: won = on_time + late + undelivered
    "requests", "lost", "unquoted",  # the week's price requests; won + lost + unquoted + cancelled orders = requests
    "http_requests", "http_429", "wall_s",  # what the week cost to play
    "error",
]


def append(row: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    with open(RUNS_CSV, "a+", newline="", encoding="utf-8") as file:
        fcntl.flock(file, fcntl.LOCK_EX)  # two harness runs can log at once
        file.seek(0)
        header = file.readline().strip()
        if header and header != ",".join(FIELDS):
            raise SystemExit(f"{RUNS_CSV} has other columns than this harness writes. Move it aside, or give it the columns of eval/log.py.")
        writer = csv.DictWriter(file, FIELDS, lineterminator="\n")
        if not header:
            writer.writeheader()
        writer.writerow(row)


def load() -> list[dict]:
    if not RUNS_CSV.exists():
        return []
    with open(RUNS_CSV, newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def weeks_of(rows: list[dict], label: str) -> dict[tuple[int, str], dict]:
    """The weeks that a version played to the end: (level, seed) -> its row. When a version played
    a week more than once, the last row counts."""
    return {(int(row["level"]), row["seed"]): row for row in rows if row["label"] == label and row["status"] == "ok"}


def euros(amount: float, signed: bool = False) -> str:
    return f"{'-' if amount < 0 else '+' if signed else ''}€{abs(amount):,.2f}"


def count(n: int, noun: str = "week") -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def week_line(row: dict) -> str:
    week = f"L{row['level']} {row['seed']}"
    if row["status"] != "ok":
        return f"{week:<12} {row['status']}: {row.get('error', '')}"
    ranked = "ranked" if int(row["ranked"]) else "NOT ranked"
    return (f"{week:<12} margin €{float(row['margin_eur']):>11,.2f}  {int(row['won']):>4} won  {float(row['on_time_pct']):5.1f}% on time"
            f"  {int(row['late']):>3} late  {int(row['undelivered']):>3} undelivered  {ranked:<10}  {row['wall_s']}s")


def summary(rows: list[dict]) -> list[str]:
    """One line for each level: what a week makes, and how safe the delivery minimum is."""
    lines = []
    for level in sorted({int(row["level"]) for row in rows}):
        weeks = [row for row in rows if int(row["level"]) == level and row["status"] == "ok"]
        if not weeks:
            continue
        margins = [float(row["margin_eur"]) for row in weeks]
        won, on_time = sum(int(row["won"]) for row in weeks), sum(int(row["on_time"]) for row in weeks)
        lines.append(f"Level {level}, {count(len(weeks))}: mean margin {euros(mean(margins))} a week (worst {euros(min(margins))}, best {euros(max(margins))})"
                     f" | on time {on_time / max(1, won):.1%} of {won} orders, worst week {min(float(row['on_time_pct']) for row in weeks):.1f}%"
                     f" | ranked in {sum(int(row['ranked']) for row in weeks)} of {count(len(weeks))}")
    return lines
