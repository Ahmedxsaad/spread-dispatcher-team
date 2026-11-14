"""The live loop, for the final: the world's clock moves by itself, and a request waits 4.5 real
seconds for its quote. The desk reads events from the stream and looks at its books a few times a
second. It can stop and start again at any minute: it rebuilds the books from the world's event
history and its own list of orders and gigs, and from a journal of its quotes on disk."""
from __future__ import annotations

import http.client
import socket
import threading
import time
import traceback
from pathlib import Path
from typing import Callable, Optional

from spread.client import Client, SpreadError, Unreachable, World

from .clock import DAY, clock
from .desk import Desk

LOOK_EVERY = 0.4  # real seconds between two checks of the clock while events keep coming
QUICK = 4.0  # real seconds that a request in play waits for an answer: a quote that is older is late anyway. The kit waits 20
JOIN = 20.0  # ... and while the desk joins a world, whose history is a long answer
CLOCK = 2.0  # ... and for the clock, which is asked again at once
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def remember_names() -> None:
    """A name server that does not answer must not stop the desk: when a look-up fails, the address that the
    same look-up gave before is used again. On the evening of 14 November the hall's network lost its name
    server for seconds at a time, and each time the desk had to join its world again."""
    if getattr(socket.getaddrinfo, "remembers", False):
        return
    look_up, known = socket.getaddrinfo, {}

    def getaddrinfo(host, port, *args, **kwargs):
        key = (host, port, args, tuple(sorted(kwargs.items())))
        try:
            known[key] = look_up(host, port, *args, **kwargs)
        except socket.gaierror:
            if key not in known:
                raise
        return known[key]

    getaddrinfo.remembers = True
    socket.getaddrinfo = getaddrinfo


def set_patience(client, seconds: float) -> None:
    """How long the client waits for an answer. In the Saturday 20:00 test final the hall's network lost three
    requests in six minutes. The kit waits 20 seconds for each, a world hour, and then the desk joined its world
    again from nothing: Monday ended with 66 orders, not 110."""
    if not hasattr(client, "patience"):
        send = client._send

        def _send(method, path, payload, headers):
            if client._connection is None:  # the kit would open it with its own 20 seconds
                kind = http.client.HTTPSConnection if client._parts.scheme == "https" else http.client.HTTPConnection
                client._connection = kind(client._parts.netloc, timeout=client.patience)
            elif client._connection.sock is not None:
                client._connection.sock.settimeout(client.patience)
            return send(method, path, payload, headers)

        client._send = _send
    client.patience = seconds


class Clock:
    """The world's minute, read in the background on a connection of its own. A read that gets no answer then
    holds nothing up: the desk goes on with the minute it has, and the requests that arrive meanwhile get their quotes."""

    def __init__(self, read: Callable[[], int]) -> None:
        self.now, self.read = 0, read
        threading.Thread(target=self.run, daemon=True).start()

    def run(self) -> None:
        while True:
            try:
                self.now = max(self.now, self.read())
            except Exception:  # no answer: the next read comes at once
                pass
            time.sleep(LOOK_EVERY)

    def minute(self) -> int:
        return self.now


def recover(world: World, desk: Desk, error: Exception, tries: int = 3) -> None:
    """A request got no answer. The desk keeps its books: it reads the events that it missed and the world's own
    list of our orders and gigs, which says which of its last actions arrived, and goes on. Only when that fails
    too does it join the world again from nothing."""
    print(f"{clock(desk.now)} no answer: {str(error)[:90]}. Reading the world again.", flush=True)
    for attempt in range(tries):
        try:
            for event in world.events(after=desk.last_seq):
                safely(desk.on_event, event)
            desk.sync(world.snapshot())
            return
        except Unreachable:
            time.sleep(0.5)
    raise error


def play_live(world: World, level: int, config: Optional[dict] = None, journal_folder: str = "results/journal",
              world_minute: Optional[Callable[[], int]] = None) -> None:
    """Plays a world whose clock moves by itself until the world ends. `world_minute` reads the
    clock when no event comes; by default it asks for the final's clock."""
    remember_names()
    client = world.client
    if world_minute is None:  # the final's clock
        watch = Client()
        set_patience(watch, CLOCK)
        world_minute = Clock(lambda: watch.final()["now"]).minute
    world_map, failed = None, 0
    while True:
        try:
            set_patience(client, JOIN)
            world_map = world_map or client.map()
            snapshot = world.snapshot()
            if snapshot["now"] >= snapshot["endsAt"]:
                return
            desk = Desk(level, config, world_map, world.roster(), snapshot["now"], snapshot["endsAt"])
            desk.rejoin(world.events(), world.snapshot(), Path(journal_folder) / f"{world.id}.jsonl")
            print(f"{clock(desk.now)} joined world {world.id}: {len(desk.books.orders)} orders in hand, {len(desk.books.gigs)} live gigs, "
                  f"{len(desk.books.unquoted)} open requests, market level {desk.market.mean:.2f}", flush=True)
            failed = 0
            set_patience(client, QUICK)
            follow(world, desk, world_minute)
            return
        except Unreachable as error:  # the server restarts, or the network is down: the desk rebuilds its books and goes on
            failed += 1
            wait = min(3.0, 0.5 * failed)  # at once after one lost answer, slower while the server stays away
            print(f"{error}. Joining again in {wait:g} seconds.", flush=True)
            time.sleep(wait)


def follow(world: World, desk: Desk, world_minute: Callable[[], int]) -> None:
    """Reads the world's events as they come. The desk looks at its books in the rhythm of its practice weeks: at once
    after an event that cannot wait, and else every `tick` minutes of the world. Every setting was measured at that
    rhythm, so the final plays at it. On 80 fresh weeks a look every 10 minutes makes 127 a week less than every 12,
    with a standard error of 138 (qt-10). Quotes alone do not wait for the rhythm: a dealer decides 4.5 real seconds
    after its request, whenever our quote came, so each request is answered at the next check of the clock. When
    quotes waited for the look, a slow server made 0 to 5 of a week's 1,000 quotes late in rehearsals at the final's pace."""
    looked, day = 0.0, desk.now // DAY
    due, urgent = desk.now, True  # the first look comes at once
    for event in world.stream(after=desk.last_seq, idle=LOOK_EVERY):
        if event is not None:
            safely(desk.on_event, event)
            urgent = urgent or event["kind"] in desk.wake_on(desk.now)
        elif desk.now < desk.ends_at:
            try:
                desk.now = max(desk.now, safely(world_minute) or desk.now)
            except Unreachable as error:  # the clock can wait for the next check: the events carry the minute too
                print(f"{clock(desk.now)} no answer to the clock: {str(error)[:90]}", flush=True)
        if event is None or time.monotonic() - looked >= LOOK_EVERY:
            looked = time.monotonic()
            if urgent or desk.now >= due:
                look(world, desk)
                due, urgent = min(desk.next_look(desk.now), (desk.now // DAY + 1) * DAY), False
            elif desk.books.unquoted:
                look(world, desk, quotes_only=True)
            if desk.now // DAY > day:
                report(world, desk, day)
                day = desk.now // DAY
            if desk.now >= desk.ends_at:
                return


def look(world: World, desk: Desk, quotes_only: bool = False) -> None:
    """One look at the books: decide, send, and read what the world did with each action."""
    try:
        actions = desk.decide(desk.now, quotes_only)
        if actions:
            desk.results(world.act(actions))
        if desk.needs_sync:  # the world refused a withdrawal: read its own list of our gigs
            desk.needs_sync = False
            desk.sync(world.snapshot())
    except Unreachable as error:
        recover(world, desk, error)
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
    try:
        score = safely(world.score)
    except Unreachable:  # the day's line in the log is not worth a stop
        score = None
    if score:
        print(f"{WEEKDAYS[day % 7]:<9}  margin €{score['marginCents'] / 100:>11,.2f}  {score['wonOrders']:>4} orders  {score['onTimeShare']:6.1%} on time  "
              f"{len(desk.books.waiting()):>3} without a driver | {dict(desk.tally)} | market level {desk.market.mean:.2f}", flush=True)
        desk.tally.clear()
