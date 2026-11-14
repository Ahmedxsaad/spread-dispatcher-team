"""Compares versions of the system on the weeks that they played, from results/runs.csv.

  python -m eval.compare                      the versions in the log
  python -m eval.compare starter              one version: its weeks, and a line for each level
  python -m eval.compare starter capacity     two versions on the weeks that both played: the effect of an idea

The effect of an idea is the second version's margin minus the first's, week by week. The weeks
are the same for both, so the difference comes from the decisions and not from the luck of a week.
"""
from __future__ import annotations

import argparse
import sys
from statistics import mean, stdev

from . import log


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("labels", nargs="*", help="one version, or two: the baseline first")
    parser.add_argument("--level", type=int, choices=range(1, 9), help="only the weeks of this level")
    args = parser.parse_args()
    rows = log.load()
    if len(args.labels) > 2:
        parser.error("compare takes one version, or two")
    known = list(dict.fromkeys(row["label"] for row in rows))
    for label in args.labels:
        if label not in known:
            sys.exit(f'No version "{label}" in the log. It has: {", ".join(known) or "no weeks yet"}')
    if not args.labels:
        for label in known:
            played = log.weeks_of(rows, label)
            levels = sorted({level for level, _ in played})
            print(f"{label}: {log.count(len(played))} at level{'' if len(levels) == 1 else 's'} {', '.join(map(str, levels))}")
        return
    versions = [{week: row for week, row in log.weeks_of(rows, label).items() if args.level in (None, week[0])} for label in args.labels]
    if len(versions) == 1:
        played = [versions[0][week] for week in sorted(versions[0])]
        for row in played:
            print(log.week_line(row))
        print()
        for line in log.summary(played):
            print(line)
        return
    first, second = versions
    for level in sorted({level for level, _ in first.keys() & second.keys()}):
        compare(level, args.labels, [[version[week] for week in sorted(first.keys() & second.keys()) if week[0] == level] for version in versions])
    alone = len(first.keys() ^ second.keys())
    if alone:
        print(f"Left out: {log.count(alone)} that only one version played.")
    if not first.keys() & second.keys():
        print("The two versions have no week in common.")


def compare(level: int, labels: list[str], versions: list[list[dict]]) -> None:
    a, b = labels
    width = max(12, len(a), len(b))
    print(f"Level {level}: {log.count(len(versions[0]))} played by both")
    print(f"  {'seed':<10} {a:>{width}} {b:>{width}} {'change':>12}   on time")
    changes = []
    for before, after in zip(*versions):
        change = float(after["margin_eur"]) - float(before["margin_eur"])
        changes.append(change)
        print(f"  {before['seed']:<10} {float(before['margin_eur']):>{width},.2f} {float(after['margin_eur']):>{width},.2f} {change:>+12,.2f}"
              f"   {float(before['on_time_pct']):5.1f}% -> {float(after['on_time_pct']):5.1f}%{'' if int(after['ranked']) else '  NOT ranked'}")
    means = [mean(float(row["margin_eur"]) for row in version) for version in versions]
    print(f"  {'mean':<10} {means[0]:>{width},.2f} {means[1]:>{width},.2f} {mean(changes):>+12,.2f}")
    # The standard error of the mean change says how far the mean could move on 20 other weeks.
    error = f" (standard error {log.euros(stdev(changes) / len(changes) ** 0.5)})" if len(changes) > 1 else ""
    print(f"  Margin: {log.euros(mean(changes), signed=True)} a week{error}; better on {sum(change > 0 for change in changes)} of {log.count(len(changes))}, worse on {sum(change < 0 for change in changes)}.")
    for label, version in zip(labels, versions):
        won, on_time = sum(int(row["won"]) for row in version), sum(int(row["on_time"]) for row in version)
        print(f"  {label}: on time {on_time / max(1, won):.1%} of {won} orders, worst week {min(float(row['on_time_pct']) for row in version):.1f}%,"
              f" ranked in {sum(int(row['ranked']) for row in version)} of {log.count(len(version))}.")
    print()


if __name__ == "__main__":
    main()
