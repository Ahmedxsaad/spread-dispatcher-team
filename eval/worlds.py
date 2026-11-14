"""Practice worlds inside the team's eight slots: a client that counts its requests, a create
that waits for a free slot, and the cleanup of the worlds that a stopped run left behind."""
from __future__ import annotations

import contextlib
import time
from pathlib import Path
from typing import Optional

from spread.client import Client, SpreadError, World

from . import RESULTS

SLOTS = 8  # a team holds at most 8 practice worlds that have not ended (API.md)
# One file for each world that the harness created and has not seen end, holding the id of its
# harness run. Only these worlds are ever deleted: never a teammate's week, never a ranking run.
OPEN = RESULTS / ".open"


class CountingClient(Client):
    """The kit's client, counting the HTTP requests it sends and the 429 answers it gets."""

    def __init__(self) -> None:
        super().__init__()
        self.sent = self.throttled = 0

    def _send(self, method, path, payload, headers):
        status, answer, data = super()._send(method, path, payload, headers)
        self.sent += 1
        self.throttled += status == 429
        return status, answer, data


def unfinished(client: Client) -> set[str]:
    """The team's practice worlds that hold a slot, ranking runs included."""
    return {world["worldId"] for world in client.worlds() if world["kind"] == "practice" and not world["ended"]}


def create(client: Client, level: int, seed: str, run: str, patience: float = 600) -> World:
    """A new practice world. While the team's slots are full, it waits for one: a teammate's week,
    or another harness run, ends within minutes."""
    give_up = time.monotonic() + patience
    while True:
        try:
            world = client.create(level=level, seed=seed)
        except SpreadError as error:
            if error.status != 409 or time.monotonic() > give_up:
                raise
            time.sleep(3)
            continue
        OPEN.mkdir(parents=True, exist_ok=True)
        (OPEN / world.id).write_text(run)
        return world


def ended(world: World) -> None:
    """The world has ended, or is deleted: it holds no slot."""
    (OPEN / world.id).unlink(missing_ok=True)


def delete(world: World) -> None:
    """Frees the slot of a week that stopped before its end. When the delete fails, the world's
    file stays, and `free` deletes the world later."""
    with contextlib.suppress(SpreadError):
        world.delete()
        ended(world)


def free(client: Client, run: Optional[str] = None) -> int:
    """Deletes the unfinished worlds that the harness left behind: those of one harness run, or all
    of them. Returns how many it deleted."""
    if not OPEN.exists():
        return 0
    held, deleted = unfinished(client), 0
    for path in sorted(OPEN.iterdir()):
        if run is not None and path.read_text() != run:
            continue
        if path.name in held:
            client.world(path.name).delete()
            deleted += 1
        path.unlink(missing_ok=True)
    return deleted
