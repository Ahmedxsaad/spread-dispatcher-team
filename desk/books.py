"""The books: what the desk knows about the week, kept up to date from the world's events alone.
Because every fact comes from an event or an action's result, a desk that restarts rebuilds the
same books from the world's event history and snapshot."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

LegKey = tuple[str, int]  # an order id and a leg


@dataclass
class Gig:
    """One of our gigs in the drivers' app."""
    id: str
    post: dict  # the post action that made it
    legs: list[LegKey]  # the cars it still carries
    posted_at: int
    status: str = "open"  # open, booked or working; an ended gig leaves the books
    driver: Optional[str] = None
    fee: int = 0
    booked_at: Optional[int] = None
    until: int = 0  # the last pickup minute of the stage below
    stage: int = 0  # 0: the car can still be on time; then the later refund steps
    viewers: set = field(default_factory=set)
    offered: set = field(default_factory=set)  # drivers who got a direct offer of this gig


class Books:
    def __init__(self) -> None:
        self.requests: dict[str, dict] = {}  # request id -> price request, while open or won
        self.unquoted: list[str] = []  # requests that wait for our quote
        self.quotes: dict[str, dict] = {}  # request id -> the prices we sent
        self.orders: dict[str, dict] = {}  # order id -> order, won and not cancelled or done
        self.done: set[str] = set()  # orders with every car delivered
        self.gigs: dict[str, Gig] = {}
        self.carrier: dict[LegKey, str] = {}  # the live gig that carries a leg
        self.failed: dict[LegKey, list[tuple[str, int, str]]] = defaultdict(list)  # failed visits of a leg: (reason, minute, gig)
        self.released: set[LegKey] = set()  # cars that the dealer has handed over after payment
        self.first_posted: dict[str, int] = {}  # order id -> the minute of its first gig
        self.trust: Counter = Counter()  # dealer id -> orders delivered on time, as the dealer counts them
        self.dealer_requests: Counter = Counter()
        self.dealer_wins: Counter = Counter()
        self.outcomes: list[tuple[int, str, float, bool]] = []  # (minute, dealer, price over list, won) of each quote that the dealer judged
        self.snow: list[dict] = []  # forecasts
        self.late: set[str] = set()  # orders with a late refund
        self.won_count = self.on_time_count = self.late_count = 0
        self.driver_seen: dict[str, int] = {}  # driver id -> the minute of their last view or booking
        self.driver_at: dict[str, tuple[str, int]] = {}  # driver id -> (place, minute) of their last delivery for us
        self.offers_sent: Counter = Counter()  # (driver id, day) -> direct offers: at most three a day
        self.offers_open: dict[str, set] = defaultdict(set)  # gig id -> drivers with an open direct offer: at most three

    # --- events ---

    def on_event(self, event: dict) -> None:
        handler = getattr(self, f"_{event['kind']}", None)
        if handler:
            handler(event)

    def _price_request(self, event: dict) -> None:
        request = event["request"]
        if request["id"] not in self.requests:
            self.requests[request["id"]] = request
            self.unquoted.append(request["id"])
            self.dealer_requests[request["dealerId"]] += 1

    def _order_won(self, event: dict) -> None:
        order = event["order"]
        if order["id"] in self.orders or order["id"] in self.done:
            return
        self.orders[order["id"]] = order
        self.dealer_wins[order["dealerId"]] += 1
        self.won_count += 1
        self._judged(order["id"], event["at"], True, order["option"])

    def _order_lost(self, event: dict) -> None:
        self._judged(event["requestId"], event["at"], False, None)
        self.requests.pop(event["requestId"], None)
        self.quotes.pop(event["requestId"], None)

    def _judged(self, request_id: str, at: int, won: bool, option: Optional[str]) -> None:
        request, prices = self.requests.get(request_id), self.quotes.get(request_id)
        if not request or not prices:
            return
        lists = {o["kind"]: o["listPriceCents"] for o in request["options"]}
        kind = option if option in prices else min(prices, key=lambda k: prices[k] / lists[k])  # a lost quote: its best offer
        self.outcomes.append((at, request["dealerId"], prices[kind] / lists[kind], won))

    def _order_changed(self, event: dict) -> None:
        order = event["order"]
        if order["id"] in self.orders:
            self.orders[order["id"]] = order

    def _order_cancelled(self, event: dict) -> None:
        order_id = event["orderId"]
        if self.orders.pop(order_id, None) is not None:
            self.won_count -= 1  # a cancelled order does not count
        for told in event["gigs"]:
            gig = self.gigs.get(told["gigId"])
            if gig is None:
                continue
            if told["outcome"] in ("withdrawn", "released"):
                self._end(gig)
            else:  # shortened or continues: the gig goes on without this order's cars
                for key in [key for key in gig.legs if key[0] == order_id]:
                    self._drop_leg(gig, key)
        for key in [key for key in self.carrier if key[0] == order_id]:
            del self.carrier[key]

    def _gig_viewed(self, event: dict) -> None:
        gig = self.gigs.get(event["gigId"])
        if gig:
            gig.viewers.add(event["driverId"])
        self.driver_seen[event["driverId"]] = event["at"]

    def _gig_booked(self, event: dict) -> None:
        gig = self.gigs.get(event["gigId"])
        if gig:
            gig.status, gig.driver, gig.fee, gig.booked_at = "booked", event["driverId"], event["feeCents"], event["at"]
        self.driver_seen[event["driverId"]] = event["at"]

    def _gig_dropped(self, event: dict) -> None:
        gig = self.gigs.get(event["gigId"])
        if gig:
            gig.status, gig.driver, gig.booked_at = "open", None, None

    _no_show = _gig_dropped  # the gig is open again in the app

    def _gig_started(self, event: dict) -> None:
        gig = self.gigs.get(event["gigId"])
        if gig:
            gig.status = "working"

    def _gig_expired(self, event: dict) -> None:
        gig = self.gigs.get(event["gigId"])
        if gig:
            self._end(gig)

    def _visit_failed(self, event: dict) -> None:
        key = (event["orderId"], event["leg"])
        self.failed[key].append((event["reason"], event["at"], event["gigId"]))
        gig = self.gigs.get(event["gigId"])
        if gig:
            self._drop_leg(gig, key)

    def _release(self, event: dict) -> None:
        self.released.add((event["orderId"], event["leg"]))

    def _delivered(self, event: dict) -> None:
        key = (event["orderId"], event["leg"])
        order = self.orders.get(key[0])
        gig = self.gigs.get(event["gigId"])
        if gig:
            if gig.driver:
                self.driver_at[gig.driver] = (event["placeId"], event["at"])
            self._drop_leg(gig, key)
        self.carrier.pop(key, None)
        if order:
            order["deliveredAt"][key[1]] = event["at"]
            if all(at is not None for at in order["deliveredAt"]):
                self.done.add(key[0])
                del self.orders[key[0]]

    def _ledger(self, event: dict) -> None:
        """Counts each dealer's orders on time as the dealer does: a revenue line with no late refund."""
        line = event["line"]
        dealer = (self.requests.get(line.get("orderId") or "") or {}).get("dealerId")
        if dealer is None:
            return
        if line["kind"] == "revenue":
            self.trust[dealer] = min(25, self.trust[dealer] + 1)
            self.on_time_count += 1
        elif line["kind"] == "late_refund" and line["orderId"] not in self.late:
            self.late.add(line["orderId"])
            self.trust[dealer] = max(0, self.trust[dealer] - 1) // 2  # take the revenue line's count back, then halve
            self.on_time_count -= 1
            self.late_count += 1

    def _offer_answered(self, event: dict) -> None:
        self.offers_open[event["gigId"]].discard(event["driverId"])

    def _forecast(self, event: dict) -> None:
        self.snow.append(event)

    # --- gigs ---

    def posted(self, action: dict, gig_id: str, now: int, until: int, stage: int) -> Gig:
        legs = [(stop["orderId"], stop["leg"]) for stop in action["stops"] if stop["kind"] == "pickup"]
        gig = Gig(gig_id, action, legs, now, until=until, stage=stage)
        self.gigs[gig_id] = gig
        for key in legs:
            self.carrier[key] = gig_id
            self.first_posted.setdefault(key[0], now)
        return gig

    def _drop_leg(self, gig: Gig, key: LegKey) -> None:
        if key in gig.legs:
            gig.legs.remove(key)
        if self.carrier.get(key) == gig.id:
            del self.carrier[key]
        if not gig.legs:
            self.gigs.pop(gig.id, None)

    def _end(self, gig: Gig) -> None:
        for key in list(gig.legs):
            if self.carrier.get(key) == gig.id:
                del self.carrier[key]
        self.gigs.pop(gig.id, None)

    def withdrawn(self, gig_id: str) -> None:
        gig = self.gigs.get(gig_id)
        if gig:
            self._end(gig)

    # --- questions ---

    def free_legs(self, order: dict) -> list[int]:
        """The order's cars that are not delivered and that no live gig carries."""
        return [leg for leg, at in enumerate(order["deliveredAt"]) if at is None and (order["id"], leg) not in self.carrier]

    def waiting(self) -> list[dict]:
        """Our orders that no driver holds yet."""
        held = {key[0] for gig in self.gigs.values() if gig.status != "open" for key in gig.legs}
        return [order for order in self.orders.values() if order["id"] not in held]
