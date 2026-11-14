"""Plays one version of the system on fixed practice weeks, several at a time, and logs each week.

  python -m eval.run --label starter --strategy spread.starter      the kit starter on the 20 level 8 weeks
  python -m eval.run --label capacity --set l8 --set l7              dispatch.py on two sets
  python -m eval.run --label capacity-off --config capacity=false    the same code with one idea off
  python -m eval.run --label try --level 8 --seeds eval-01,eval-02   two weeks only
  python -m eval.run --free                                          delete the worlds that a stopped run left behind

Each week adds a row to results/runs.csv, its reveal goes to results/reveals/<label>/<week>/ and
the strategy's output to results/logs/<label>/<week>.log. Compare versions with eval.compare.

Do not edit the system's code while a run plays: each week starts in a fresh process and loads the
code as it is at that moment. When it happens, the weeks of the run differ in `code_hash`.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import multiprocessing
import os
import signal
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from spread.client import Client, SpreadError

from . import RESULTS, ROOT, RUNS_CSV, load_env, log
from .seeds import SETS, Week
from .worker import Job, play_week
from .worlds import SLOTS, free, unfinished


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", help="the name of this version of the system in results/runs.csv, for example starter or capacity")
    parser.add_argument("--strategy", default="dispatch", help="the module to play; it has play_practice(world, level), as the kit's starter has (default dispatch)")
    parser.add_argument("--set", dest="sets", action="append", choices=sorted(SETS), help="a set of weeks from eval/seeds.py; can be given more than once (default l8)")
    parser.add_argument("--level", type=int, choices=range(1, 9), help="with --seeds: the level of weeks outside the sets")
    parser.add_argument("--seeds", help="with --level: their seeds, separated by commas")
    parser.add_argument("--config", action="append", default=[], metavar="KEY=VALUE", help="a setting for play_practice(world, level, config); the value is JSON, or text when it is not")
    parser.add_argument("--workers", type=int, default=SLOTS, help=f"the weeks to play at once (default {SLOTS}, the team's practice slots)")
    parser.add_argument("--no-reveal", action="store_true", help="do not export the weeks' reveals")
    parser.add_argument("--free", action="store_true", help="delete the unfinished worlds that stopped harness runs left behind, and exit")
    args = parser.parse_args()
    load_env()
    try:
        client = Client()
        if args.free:
            print(f"Deleted {free(client)} unfinished worlds of the harness.")
            return
        weeks = chosen(parser, args)
        if not args.label:
            parser.error("--label names this version of the system in results/runs.csv")
        if importlib.util.find_spec(args.strategy) is None:
            parser.error(f"no module {args.strategy}: --strategy names a module, for example dispatch or spread.starter")
        held = len(unfinished(client))
    except SpreadError as error:
        sys.exit(f"spread: {error}")
    workers = max(1, min(args.workers, len(weeks), SLOTS - held))
    if held:
        print(f"{held} of the team's {SLOTS} practice slots hold unfinished worlds, so {workers} weeks play at a time. If a stopped run left them: python -m eval.run --free")
    run = f"{os.getpid()}-{int(time.time())}"
    jobs = [Job(run, args.label, args.strategy, config(parser, args.config), level, seed, not args.no_reveal) for level, seed in weeks]
    commit = git_commit()
    print(f'Playing {len(jobs)} week{"s" * (len(jobs) != 1)} with {args.strategy} as "{args.label}", {workers} at a time.', flush=True)

    # A fresh interpreter for each week, with a fixed hash seed: the order in which a strategy walks
    # a set is then the same in every run.
    os.environ["PYTHONHASHSEED"] = "0"
    signal.signal(signal.SIGTERM, signal.default_int_handler)  # a stop request cleans up as Ctrl-C does
    pool = ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"), max_tasks_per_child=1)
    futures = {pool.submit(play_week, job): job for job in jobs}
    rows = []
    try:
        for future in as_completed(futures):
            job = futures[future]
            try:
                row = future.result()
            except Exception as error:  # the week's process died
                row = {"label": job.label, "strategy": job.strategy, "level": job.level, "seed": job.seed, "status": "error", "error": f"{type(error).__name__}: {error}"}
            if row["status"] == "interrupted":
                continue
            row.update(ts=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), git_commit=commit)
            log.append(row)
            rows.append(row)
            print(log.week_line(row), flush=True)
    except KeyboardInterrupt:
        signal.signal(signal.SIGINT, signal.SIG_IGN)  # let the cleanup finish
        for process in multiprocessing.active_children():
            process.terminate()  # each week deletes its world
        pool.shutdown(wait=True, cancel_futures=True)
        left = free(client, run)
        sys.exit(f"Stopped. {len(rows)} weeks are logged; the unfinished worlds are deleted{f' ({left} by the cleanup)' if left else ''}.")
    pool.shutdown()
    free(client, run)  # the world of a week whose process died

    rows.sort(key=lambda row: (row["level"], row["seed"]))
    print()
    for row in rows:
        print(log.week_line(row))
    print()
    for line in log.summary(rows):
        print(line)
    failed = sum(row["status"] != "ok" for row in rows)
    print(f"{len(rows) - failed} of {log.count(len(rows))} played to the end. Every week has a row in {shown(RUNS_CSV)}.")
    if failed:
        print(f"{failed} failed: the tracebacks are in {shown(RESULTS / 'logs' / args.label)}/")
    sys.exit(1 if failed else 0)


def shown(path: Path) -> str:
    return str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)


def chosen(parser: argparse.ArgumentParser, args: argparse.Namespace) -> list[Week]:
    """The weeks to play, each once, in the order given."""
    if (args.level is None) != (args.seeds is None):
        parser.error("--level and --seeds go together")
    weeks = [week for name in args.sets or [] for week in SETS[name]]
    if args.seeds:
        weeks += [(args.level, seed.strip()) for seed in args.seeds.split(",") if seed.strip()]
    return list(dict.fromkeys(weeks or SETS["l8"]))


def config(parser: argparse.ArgumentParser, settings: list[str]) -> dict:
    values = {}
    for setting in settings:
        key, equals, value = setting.partition("=")
        if not equals or not key:
            parser.error(f"--config takes KEY=VALUE, not {setting}")
        try:
            values[key] = json.loads(value)
        except ValueError:
            values[key] = value
    return values


def git_commit() -> str:
    """The commit that the code is at, with "+" when files other than the results differ from it."""
    def git(*command: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(ROOT), *command], capture_output=True, text=True)
    try:
        head = git("rev-parse", "--short", "HEAD")
        if head.returncode != 0:
            return "nogit"
        return head.stdout.strip() + ("+" if git("status", "--porcelain", "--", ".", ":!results").stdout.strip() else "")
    except OSError:
        return "nogit"


if __name__ == "__main__":
    main()
