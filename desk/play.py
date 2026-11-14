"""The loops: a practice world, which stands still until we move its clock, and the live final."""
from __future__ import annotations

import time
from typing import Optional

from spread.client import SpreadError, Unreachable, World

from .clock import DAY
from .desk import Desk

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def play_practice(world: World, level: int, config: Optional[dict] = None) -> None:
    """Looks at the world every few minutes while requests can arrive, and at once when a plan
    fails. Each look is one request: it sends the actions of the last look and moves the clock."""
    snapshot = world.snapshot()
    now, ends_at = snapshot["now"], snapshot["endsAt"]
    desk = Desk(level, config, world.client.map(), world.roster(), now, ends_at)
    actions: list[dict] = []
    while now < ends_at:
        day = now // DAY
        try:
            step = world.advance(until=desk.wake_on(now), max=min(ends_at, desk.next_look(now), (day + 1) * DAY), actions=actions)
            desk.results(step["results"])
            now = step["now"]
            for event in step["events"]:
                desk.on_event(event)
            if desk.needs_sync:  # the world refused a withdrawal: read its own list of our gigs
                desk.needs_sync = False
                desk.sync(world.snapshot())
            if now // DAY > day:
                report(WEEKDAYS[day % 7], world.score(), len(desk.books.waiting()))
                print(f"           {desk.urgent()} of them on the ladder", flush=True)
                if desk.tally:
                    print(f"           {dict(desk.tally)} | market level {desk.market.mean:.2f} ± {desk.market.var ** 0.5:.2f}", flush=True)
                    desk.tally.clear()
        except Unreachable as error:  # the server restarts, or the network drops: every world goes on from where it was
            print(f"{error}. Reading the world again.", flush=True)
            now = catch_up(world, desk)
        except SpreadError as error:  # the world took none of the batch: one bad action must not stop the desk
            if error.status != 400:
                raise
            print(f"The world refused a batch: {error}. Its actions are dropped: {actions}", flush=True)
            now = catch_up(world, desk)
            desk.decide(now)  # the same decisions again would be refused again: skip this look
            desk.sync(world.snapshot())
            actions = []
            continue
        actions = desk.decide(now)


def catch_up(world: World, desk: Desk, patience: float = 600) -> int:
    """After a lost connection: waits for the server, reads the events that the desk missed and
    the world's own list of our orders and gigs. Returns the world's minute."""
    give_up = time.monotonic() + patience
    while True:
        try:
            missed = world.events(after=desk.last_seq)
            snapshot = world.snapshot()
            break
        except Unreachable:
            if time.monotonic() > give_up:
                raise
            time.sleep(3)
    for event in missed:
        desk.on_event(event)
    desk.sync(snapshot)
    return snapshot["now"]


def report(label: str, score: dict, waiting: int) -> None:
    orders = f"{score['wonOrders']:>4} orders  {score['onTimeShare']:6.1%} on time  {score['undeliveredShare']:5.1%} not delivered  {waiting:>3} without a driver"
    print(f"{label:<9}  margin €{score['marginCents'] / 100:>11,.2f}  revenue €{score['revenueCents'] / 100:>11,.2f}  {orders}", flush=True)
