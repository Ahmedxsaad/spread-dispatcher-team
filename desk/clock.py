"""World time: whole minutes from Monday 00:00. Site opening hours, and the hours in which
drivers read the app."""
from __future__ import annotations

from typing import Optional

HOUR, DAY = 60, 24 * 60
AWAKE = (7 * HOUR, 22 * HOUR)  # no driver reads a notification from 23:00 to 07:00, and few look late in the evening
LAST_REQUEST = 4 * DAY + 18 * HOUR  # price requests arrive from Monday 08:00 to Friday 18:00


def business_days_after(day: int, count: int) -> int:
    """The day that lies `count` business days after `day`."""
    while count > 0:
        day += 1
        if day % 7 < 5:
            count -= 1
    return day


def awake_between(a: int, b: int) -> int:
    """The minutes from a to b in which drivers read the app."""
    total, day = 0, a // DAY
    while day * DAY < b:
        total += max(0, min(b, day * DAY + AWAKE[1]) - max(a, day * DAY + AWAKE[0]))
        day += 1
    return total


def awake_before(t: int, minutes: int) -> int:
    """The minute that lies `minutes` awake minutes before t."""
    day = t // DAY
    while day >= -1:
        span = min(t, day * DAY + AWAKE[1]) - (day * DAY + AWAKE[0])
        if span >= minutes:
            return min(t, day * DAY + AWAKE[1]) - minutes
        minutes -= max(0, span)
        day -= 1
    return 0


def awake_after(t: int, minutes: int) -> int:
    """The minute that lies `minutes` awake minutes after t."""
    day = t // DAY
    while True:
        start = max(t, day * DAY + AWAKE[0])
        span = day * DAY + AWAKE[1] - start
        if span >= minutes:
            return start + minutes
        minutes -= max(0, span)
        day += 1


def open_span(hours: Optional[dict], day: int) -> Optional[tuple[int, int]]:
    """The minutes of `day` in which a site with these stated hours is open; None when it is closed."""
    if hours is None:
        return (day * DAY, (day + 1) * DAY)  # a private address has no hours: its window is the booked slot
    weekday = day % 7
    today = hours if weekday in hours["weekdays"] else hours.get("saturday") if weekday == 5 else None
    if not today or today["closes"] <= today["opens"]:
        return None
    return (day * DAY + today["opens"], day * DAY + today["closes"])


def cut(hours: Optional[dict], opens: Optional[int], closes: Optional[int]) -> Optional[dict]:
    """Stated opening hours, cut to the hours that a note gives."""
    if hours is None or (opens is None and closes is None):
        return hours
    def narrow(span: dict) -> dict:
        return {**span, "opens": max(span["opens"], opens if opens is not None else 0), "closes": min(span["closes"], closes if closes is not None else DAY)}
    return {**narrow(hours), "saturday": narrow(hours["saturday"]) if hours.get("saturday") else None}


def last_open(hours: Optional[dict], t: int) -> int:
    """The latest minute, not after t, at which the site is open."""
    for day in range(t // DAY, t // DAY - 9, -1):
        span = open_span(hours, day)
        if span and span[0] <= t:
            return min(t, span[1] - 1)
    return t


def first_open(hours: Optional[dict], t: int) -> int:
    """The earliest minute, not before t, at which the site is open."""
    for day in range(t // DAY, t // DAY + 9):
        span = open_span(hours, day)
        if span and span[1] > t:
            return max(t, span[0])
    return t


def clock(t: int) -> str:
    return f"{'Mon Tue Wed Thu Fri Sat Sun'.split()[t // DAY % 7]} {t % DAY // HOUR:02d}:{t % HOUR:02d}"
