"""The fixed evaluation weeks. Every version of the system is judged on the same weeks, so a set
never changes once a version has played it: add a new set instead."""
from __future__ import annotations

Week = tuple[int, str]  # a level and a seed: together they name one practice week


def weeks(level: int, prefix: str, count: int) -> list[Week]:
    return [(level, f"{prefix}-{i:02d}") for i in range(1, count + 1)]


SETS: dict[str, list[Week]] = {
    # The tuning set, at the final's level. An idea counts when it gains on these 20 weeks.
    "l8": weeks(8, "eval", 20),
    # Its first 8 weeks: one batch of the team's 8 practice slots, for a first look at an idea.
    "l8-quick": weeks(8, "eval", 8),
    # Never tune on these. They show whether a gain holds on weeks that the system has not seen.
    "l8-holdout": weeks(8, "hold", 20),
    # The levels below the final: level 7 has an even shortage, level 6 none.
    "l7": weeks(7, "eval", 5),
    "l6": weeks(6, "eval", 5),
    # Two weeks at four levels: does the system still work at every step up to the final?
    "ladder": [(level, seed) for level in (1, 4, 6, 8) for seed in ("eval-01", "eval-02")],
    # Weeks for experiments that measure the market, such as random prices: never the evaluation weeks.
    "explore": weeks(8, "x", 40),
    "explore2": weeks(8, "x", 80)[40:],
    # HANDBOOK.md prints the kit starter's result on this week: -72,612.51 at 45.5% on time.
    # The starter must score exactly that through the harness.
    "known": [(8, "spread-1")],
}
