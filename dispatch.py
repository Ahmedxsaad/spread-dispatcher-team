"""Plays a Spread world with our desk. Set SPREAD_URL and SPREAD_KEY first, or put them in .env.

  python dispatch.py --level 8 --seed eval-01     one practice week
  python dispatch.py --level 8 --board            the next ranking run at the level
  python dispatch.py --final                      the live final, or a test final: waits for it, plays it, and can be started again at any minute
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from spread.client import Client, SpreadError, Unreachable, World

from desk.play import play_practice, report  # noqa: F401  (the eval harness plays `play_practice`)
from eval import load_env


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--level", type=int, choices=range(1, 9), default=8)
    parser.add_argument("--seed", help="any text; the same seed gives the same world")
    parser.add_argument("--board", action="store_true", help="play the next ranking run at the level; it counts in the practice rankings")
    parser.add_argument("--final", action="store_true", help="play our copy of the final from the live stream")
    parser.add_argument("--config", default="{}", help="settings of the desk, as JSON")
    args = parser.parse_args()
    load_env()
    if args.final:
        return play_final(json.loads(args.config))
    try:
        client = Client()
        world = client.create(level=args.level, seed=args.seed, board=args.board)
        print(f"{'Ranking run' if args.board else 'Practice world'} {world.id}, level {args.level}.", flush=True)
        try:
            play_practice(world, args.level, json.loads(args.config))
        except BaseException:
            if not args.board:  # a ranking run that is deleted plays to its end without us, and counts
                world.delete()
            raise
        score = world.score()
        report("End", score, 0)
        print("Ranked." if score["ranked"] else "Not ranked.")
        if args.board:
            log_ranking_run(client, world, args, score)
    except SpreadError as error:
        sys.exit(f"spread: {error}")


def play_final(config: dict) -> None:
    """Waits for the final, plays it to its end, and survives a server that restarts. The desk
    rebuilds its books from the world, so this can be stopped and started again at any minute."""
    from desk.live import play_live, remember_names

    remember_names()  # from the first request on: the wait for the final already resolves the server's name
    while True:
        try:
            client = Client()
            world = next_final(client)
            print(f"Final world {world.id}.", flush=True)
            play_live(world, 8, config)
            score = world.score()
            report("End", score, 0)
            print("Ranked." if score["ranked"] else "Not ranked.")
            return
        except Unreachable as error:
            print(f"spread: {error}. Trying again in 3 seconds.", file=sys.stderr, flush=True)
            time.sleep(3)


def next_final(client: Client) -> World:
    """Our copy of the final that is set or runs now. Waits while none is set, and while the last one has ended."""
    said = False
    while True:
        try:
            world = client.world(client.final()["worldId"])
            snapshot = world.snapshot()
            if snapshot["now"] < snapshot["endsAt"]:
                return world
        except SpreadError as error:
            if isinstance(error, Unreachable) or error.status != 404:
                raise
        if not said:
            print("No final is set. Waiting for it: a test final is set 15 minutes before its start, the final 30 minutes before.", flush=True)
            said = True
        time.sleep(5)


def log_ranking_run(client: Client, world, args: argparse.Namespace, score: dict) -> None:
    """A ranking run goes into results/runs.csv too, named by its round and its number in the round."""
    from datetime import datetime, timezone

    from eval import log
    from eval.worker import scored

    listed = next((w for w in client.worlds() if w["worldId"] == world.id), {})
    log.append({"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "label": f"ranking-round-{listed.get('season')}", "strategy": "dispatch", "config": args.config,
                "level": args.level, "seed": f"run-{listed.get('boardRun')}", "world_id": world.id, "status": "ok", **scored(score)})


if __name__ == "__main__":
    main()
