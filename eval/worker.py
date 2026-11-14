"""Plays one practice week with one version of the system and returns the week's row for
results/runs.csv. Each week runs in a fresh process, so nothing that the system remembers leaks
from one week into the next, and the same code on the same week gives the same row."""
from __future__ import annotations

import contextlib
import csv
import hashlib
import importlib
import inspect
import json
import signal
import sys
import time
import traceback
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Callable, NamedTuple, Optional

from spread import reveal_csv
from spread.client import World
from spread.types import Score

from . import RESULTS, ROOT, load_env
from .worlds import CountingClient, create, delete, ended

NOT_THE_SYSTEM = {"eval", "results", "context", ".venv"}  # folders of the project whose code is not the system


class Job(NamedTuple):
    run: str  # the harness run that the week belongs to
    label: str  # the name of this version of the system in results/runs.csv
    strategy: str  # a module with play_practice(world, level), as the kit's starter has
    config: dict  # passed to play_practice as `config`, when it takes one
    level: int
    seed: str
    reveal: bool

    @property
    def week(self) -> str:
        return f"L{self.level}-{self.seed}"


def play_week(job: Job) -> dict:
    """Never raises: the row's `status` is `ok`, `error` or `interrupted`, and `error` says why.
    The strategy's own output and any traceback go to results/logs/<label>/<week>.log."""
    signal.signal(signal.SIGTERM, signal.default_int_handler)  # a stop request ends the week as Ctrl-C does
    load_env()
    row: dict = {"label": job.label, "strategy": job.strategy, "level": job.level, "seed": job.seed, "status": "error",
                 "config": json.dumps(job.config, sort_keys=True, separators=(",", ":"))}
    log = RESULTS / "logs" / job.label / f"{job.week}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    client: Optional[CountingClient] = None
    module: Optional[ModuleType] = None
    world: Optional[World] = None
    with open(log, "w", encoding="utf-8") as out, contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            client = CountingClient()
            module = importlib.import_module(job.strategy)
            play_practice = player(module, job.config)
            world = create(client, job.level, job.seed, job.run)
            row["world_id"] = world.id
            play_practice(world, job.level)
            snapshot = world.snapshot()
            if snapshot["now"] < snapshot["endsAt"]:  # a score before the end is not the week's score
                raise RuntimeError(f"{job.strategy} stopped at minute {snapshot['now']}, before the world's end at {snapshot['endsAt']}")
            ended(world)
            row.update(scored(snapshot["score"]), status="ok")
            if job.reveal:
                row.update(export(world.id, RESULTS / "reveals" / job.label / job.week))
        except BaseException as error:  # also Ctrl-C, and the exit of the kit's exporter
            for stop in (signal.SIGINT, signal.SIGTERM):  # let the cleanup finish
                signal.signal(stop, signal.SIG_IGN)
            traceback.print_exc()
            if row["status"] == "ok":  # the week is played and scored; only its reveal is missing
                row["error"] = f"reveal: {error}"
            else:
                row["status"] = "interrupted" if isinstance(error, KeyboardInterrupt) else "error"
                row["error"] = f"{type(error).__name__}: {error}"
                if world is not None:
                    delete(world)  # a world left behind holds one of the team's eight slots
        finally:
            row["wall_s"] = round(time.monotonic() - started)
            if client is not None:
                row.update(http_requests=client.sent, http_429=client.throttled)
            if module is not None:
                row["code_hash"] = fingerprint(module)
    return row


def player(module: ModuleType, config: dict) -> Callable[[World, int], None]:
    """The strategy's play_practice(world, level). It gets the run's config when it takes one."""
    play_practice = getattr(module, "play_practice", None)
    if play_practice is None:
        raise TypeError(f"{module.__name__} has no play_practice(world, level)")
    if "config" in inspect.signature(play_practice).parameters:
        return lambda world, level: play_practice(world, level, config=config)
    if config:
        raise TypeError(f"{module.__name__}.play_practice takes no config, and this run has one: {config}")
    return play_practice


def scored(score: Score) -> dict:
    """The week's result in the columns of the log. An order is on time, late (delivered after its
    deadline) or undelivered at the world's end; the delivery minimum counts the last two as late."""
    won = score["wonOrders"]
    on_time, undelivered = round(score["onTimeShare"] * won), round(score["undeliveredShare"] * won)
    return {"ranked": int(score["ranked"]), "margin_eur": f"{score['marginCents'] / 100:.2f}", "revenue_eur": f"{score['revenueCents'] / 100:.2f}",
            "on_time_pct": f"{100 * score['onTimeShare']:.2f}", "won": won, "on_time": on_time, "late": won - on_time - undelivered, "undelivered": undelivered}


def export(world_id: str, folder: Path) -> dict:
    """Writes the week's reveal with the kit's own exporter (HANDBOOK.md, Research), and counts
    the week's price requests by what the dealer did."""
    argv, sys.argv = sys.argv, ["spread-reveal-csv", world_id, "--out", str(folder)]
    try:
        reveal_csv.main()
    finally:
        sys.argv = argv
    with open(folder / "requests.csv", newline="", encoding="utf-8") as file:
        outcomes = Counter(request["outcome"] for request in csv.DictReader(file))
    return {"requests": sum(outcomes.values()), "lost": outcomes["lost"], "unquoted": outcomes["unquoted"]}


def fingerprint(module: ModuleType) -> str:
    """A short hash of the system's source: the strategy's file, and every module of the project
    that it loaded. Two rows with the same hash and config played the same code, whatever git says."""
    sources = {module.__name__: Path(module.__file__).resolve()}
    for name, loaded in list(sys.modules.items()):
        path = Path(getattr(loaded, "__file__", None) or "/").resolve()
        if path.suffix == ".py" and ROOT in path.parents and not NOT_THE_SYSTEM & set(path.relative_to(ROOT).parts):
            sources[name] = path
    digest = hashlib.sha256()
    for name in sorted(sources):
        digest.update(name.encode() + b"\0" + sources[name].read_bytes())
    return digest.hexdigest()[:10]
