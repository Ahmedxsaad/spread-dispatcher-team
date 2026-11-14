"""The live loop, for the final: the world's clock moves by itself, and a request waits 4.5 real
seconds for its quote. The desk reads events from the stream and looks at its books a few times a
second. It can stop and start again at any minute: it rebuilds the books from the world's event
history and its own list of orders and gigs, and from a journal of its quotes on disk."""
from __future__ import annotations

import time
import traceback
from pathlib import Path
from typing import Callable, Optional

from spread.client import SpreadError, Unreachable, World

from .clock import DAY, clock
from .desk import Desk

LOOK_EVERY = 0.4  # real seconds between two checks of the clock while events keep coming
QUOTE_BY = 6  # world minutes before a request's deadline at which its quote goes out whatever the rhythm: 1.8 real seconds
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def play_live(world: World, level: int, config: Optional[dict] = None, journal_folder: str = "results/journal",
              world_minute: Optional[Callable[[], int]] = None) -> None:
    """Plays a world whose clock moves by itself until the world ends. `world_minute` reads the
    clock when no event comes; by default it asks for the final's clock."""
    client = world.client
    world_minute = world_minute or (lambda: client.final()["now"])
    world_map = None
    while True:
        try:
            world_map = world_map or client.map()
            snapshot = world.snapshot()
            if snapshot["now"] >= snapshot["endsAt"]:
                return
            desk = Desk(level, config, world_map, world.roster(), snapshot["now"], snapshot["endsAt"])
            desk.rejoin(world.events(), world.snapshot(), Path(journal_folder) / f"{world.id}.jsonl")
            print(f"{clock(desk.now)} joined world {world.id}: {len(desk.books.orders)} orders in hand, {len(desk.books.gigs)} live gigs, "
                  f"{len(desk.books.unquoted)} open requests, market level {desk.market.mean:.2f}", flush=True)
            follow(world, desk, world_minute)
            return
        except Unreachable as error:  # the server restarts: the desk rebuilds its books and goes on
            print(f"{error}. Joining again in 3 seconds.", flush=True)
            time.sleep(3)


def follow(world: World, desk: Desk, world_minute: Callable[[], int]) -> None:
    """Reads the world's events as they come. The desk looks at its books in the rhythm of its practice weeks: at once
    after an event that cannot wait, and else every `tick` minutes of the world. A car that waits a few minutes for the
    next look can still go in a pair with a car that we win just after it: with a look every 3 minutes, the same 40
    practice weeks make 335 a week less (qt-3). A quote never waits past `QUOTE_BY` minutes before its deadline."""
    looked, day = 0.0, desk.now // DAY
    due, urgent = desk.now, True  # the first look comes at once
    for event in world.stream(after=desk.last_seq, idle=LOOK_EVERY):
        if event is not None:
            safely(desk.on_event, event)
            urgent = urgent or event["kind"] in desk.wake_on(desk.now)
        elif desk.now < desk.ends_at:
            desk.now = max(desk.now, safely(world_minute) or desk.now)
        if event is None or time.monotonic() - looked >= LOOK_EVERY:
            looked = time.monotonic()
            if urgent or desk.now >= due or desk.quote_due(desk.now, QUOTE_BY):
                look(world, desk)
                due, urgent = min(desk.next_look(desk.now), (desk.now // DAY + 1) * DAY), False
            if desk.now // DAY > day:
                report(world, desk, day)
                day = desk.now // DAY
            if desk.now >= desk.ends_at:
                return


def look(world: World, desk: Desk) -> None:
    """One look at the books: decide, send, and read what the world did with each action."""
    try:
        actions = desk.decide(desk.now)
        if actions:
            desk.results(world.act(actions))
        if desk.needs_sync:  # the world refused a withdrawal: read its own list of our gigs
            desk.needs_sync = False
            desk.sync(world.snapshot())
    except Unreachable:
        raise
    except Exception as error:  # a refused batch or a bug must not stop the desk: read the world again and go on
        print(f"{clock(desk.now)} a look failed: {type(error).__name__}: {error}", flush=True)
        if not isinstance(error, SpreadError):
            traceback.print_exc()
        desk.sync(world.snapshot())


def safely(function: Callable, *args):
    try:
        return function(*args)
    except Unreachable:
        raise
    except Exception as error:
        print(f"{function.__name__} failed: {type(error).__name__}: {error}", flush=True)
        traceback.print_exc()
        return None


def report(world: World, desk: Desk, day: int) -> None:
    score = safely(world.score)
    if score:
        print(f"{WEEKDAYS[day % 7]:<9}  margin €{score['marginCents'] / 100:>11,.2f}  {score['wonOrders']:>4} orders  {score['onTimeShare']:6.1%} on time  "
              f"{len(desk.books.waiting()):>3} without a driver | {dict(desk.tally)} | market level {desk.market.mean:.2f}", flush=True)
        desk.tally.clear()
