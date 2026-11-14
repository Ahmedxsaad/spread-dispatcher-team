"""The desk: it reads the world's events into the books and answers with actions. Three decisions:
the price of each option of a request, the gig and fee schedule of each car won, and what to do
when a plan fails. The same desk plays a practice world and the live final."""
from __future__ import annotations

import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import IO, NamedTuple, Optional

from . import notes
from .books import Books
from .clock import AWAKE, DAY, HOUR, LAST_REQUEST, awake_after, awake_before, awake_between, business_days_after, clock, cut, last_open, open_span
from .market import EventMarket, Market, RegimeMarket
from .model import FITTED, air_km, at_fee, drivers_near, gig_features, logistic

SETTINGS = {
    "join_day": 0,  # practice only: the day on which the desk joins the week, with nothing done before it, as a test final does (Thursday: 3)
    # A desk that joins the week late, as in a test final: the driver curves count the days from the join, not from Monday, because its drivers
    # are as free as on a Monday, and the guard counts on the orders of the days that are left. On 80 half weeks from Thursday the first part alone
    # made 103 more (hw-days). With the guard's part every half week is ranked, where 1 in 80 is not without it, but a third of the orders and
    # 2,336 of 6,475 euros are gone (hw-join). Off: a test final does not count.
    "days_from_join": False,
    "tick": 12,  # minutes between two looks at the world while requests can arrive; a request waits 15 minutes for its quote
    "seed": 1,
    "explore": False,  # random prices and opening fees, to measure how dealers and drivers answer them
    # Quotes
    "min_chance": 0.84,  # no price for an option whose car gets a driver in time less often than this. 0.90 makes 1,000 a week less, 0.80 a little more but a worst week of 92.5% (u-*)
    # The minimum is lower while the week has on-time share to spare: its late share, with the cars now at risk, is below `spare`.
    "spare": 0.03,
    "spare_chance": 0.78,  # the minimum chance then, for every lane. On 40 weeks: 345 a week more, on time unchanged (s-all78)
    "private_chance": 0.78,  # ... for a car to or from a private address
    "long_chance": [240, 0.70],  # [drive minutes, minimum chance then]: long lanes earn the most a car, 80 to 100 euros. On 40 weeks: 370 a week more (z-long70-spare3)
    "late_cost": 0.6,  # what a late car costs us beyond its fee, as a share of its list price: the refund, and the dealer's goodwill
    "trust_value": 0.0,  # how much of a trust point's worth lowers our price, to win the order and its point. Measured: pricing low to buy trust loses (u-gain0, t-trust2)
    "trust_late": 1.0,  # how much of the trust that a late car loses counts in its cost
    "win_share": 0.4,  # the share of a dealer's later requests that we expect to win
    "min_profit": 200,  # cents: no price for an option that is expected to make less
    "fast_factor": 1.0,  # a factor on the price of the fastest option when we also offer a later one: later options leave us more per car
    "drop_bump": 1.0,  # after a driver gives a gig back, its fee starts again at the fee that was booked times this
    "greed_short": [0, 1.06],  # [drive minutes, factor]: lanes up to this length have their own factor
    "greed_long": [100000, 1.06],  # ... and lanes from this length on
    # The factor follows the market: in a week with a cheap competitor a lower factor does as well or better, and a higher one loses most.
    # On 80 fresh weeks, by quarter of the week's level, a factor of 1.03 against 1.06 makes -17, +239, -589, -916 and 1.09 makes -725, -572, -427, -232.
    "greed_slope": 0.0,  # how much the factor rises for each unit of the day's level above the level of an average day, in the curve's units; 0: one factor
    "greed_range": [1.02, 1.09],  # the factor stays inside this range
    "greed_load": [0.0, 30],  # [how much the factor rises for each order without a driver above the usual number, that number]: with few cars waiting, drivers are free for more; 0: no such rise
    "greed_later": 0.0,  # the factor for a car due after the weekend: the driver curve says 88 in 100 of them get a driver in time, and 97 in 100 do, so their cost is put too high; 0.0: as any other car
    "greed": 1.06,  # a factor on the price that the models choose. Dealers react less to our price than the fitted curve says: 1.00 makes 14,027 a week, 1.06 14,785, 1.12 13,895 (g-*)
    "decline": 3.0,  # a price that no dealer takes, over the list price: a quote that loses costs nothing
    "max_waiting": 60,  # stop winning while this many orders have no driver
    "max_urgent": 20,  # ... or while this many of them are on the ladder: the last pickup is near
    "explore_fees": [0.5, 0.6, 0.7, 0.85, 1.0, 1.2, 1.4, 1.7, 2.0],
    # Two cars in one gig, when the second starts near where the first ends and ends near where the first starts: the driver
    # needs no trip to a pickup and no trip home, so the gig costs less than the two cars alone
    "pairs": True,
    "pair_hop": 60,  # road minutes at most from the first car's delivery to the second car's pickup
    "pair_back": 120,  # ... and from the second car's delivery back to the first car's pickup. The way back may be longer than the hop (p-hop*)
    "pair_fee": 0.75,  # the pair's fee, over the sum of the two typical fees
    "pair_wait": 90,  # minutes at most that the driver waits for the second car to be ready
    # A car that we post alone is mostly booked within minutes, and then a return car that we win an hour later has no partner.
    # So a new car that could go in a pair stays off the app for a while, as long as requests still arrive and its pickup is far.
    # Measured: 65, 181 and 314 a week less for 30, 60 and 120 minutes (pi-*). A pair saves little against two easy cars, which book alone at 0.85.
    "pair_hold": [0, 10],  # [minutes that it waits for a partner, awake hours that must be left before its fee ladder]; 0 minutes: post at once
    "pair_rise": [],  # raises of a pair's fee before the ladder, as `rise` for a single car
    "pair_quotes": False,  # price a request lower when its car pairs with an order that waits for a driver. Measured: worse, the pair seldom forms (v10-pairquote)
    "pair_share": 0.0,  # how much of a lane's expected pair saving comes off a car's cost when it is priced: 29% of our cars go in a return-trip pair, at 0.75 of the typical fees against 1.03 alone, and a lane's share runs from 3% to 45% and holds from week to week (analysis/pairs.py); 0.0: every car is priced as if it went alone
    "pair_odds": 0.8,  # how often such a pair then finds its driver
    # Trade-ins: the new car out to the customer and the old car back, one price and one gig. Their list price is about 1.9
    # times the typical fee, against 1.1 for other cars
    "trade_ins": True,
    "trade_in_fee": 1.3,  # the gig's opening fee, over the typical fee
    "trade_in_cost": 1.5,  # the fee that we expect to pay. Lower opening fees do not lower it (ti-*)
    "trade_in_chance": 0.6,  # the minimum chance for a trade-in: the fitted curve is for single cars, and trade-ins arrive on time more often than it says (tc-60: 94%)
    # Direct offers to a driver who has just delivered a car of ours near the pickup of an open gig: the app does not notify them there
    "offers": False,
    "offer_km": 30,  # how near the pickup the driver must stand, in a straight line
    "offer_fee": 0.75,  # the fee of such an offer, over the typical fee
    "offer_fee_home": 0.6,  # ... when the gig ends within 40 km of the driver's home
    "explore_offers": [],  # an exploring desk draws the offer's fee from these
    # Direct offers to the drivers who looked at a gig and did not book it. In the app such a driver holds out while they expect
    # the fee to rise before another driver books. An offer has no raise to wait for: the driver takes it when the fee pays.
    # Measured in one week: 15 of 959 offers accepted, and 2 of 331 at the fee in the app. A driver who looks and leaves needs a higher fee (w-vo-smoke)
    "viewer_offers": [0, 1.0, 30],  # [minutes that a gig waits in the app first, the offer's fee over the fee in the app, km at most from the driver's home to the delivery]; 0 minutes: none
    "explore_viewer_offers": [],  # an exploring desk draws the offer's fee, over the fee in the app, from these
    "explore_caps": [25, 40, 60, 90],  # an exploring desk draws its max_waiting from these, by the world's number of drivers
    # Fees, over the typical fee
    "fees": [0.85, 0.95, 1.05, 1.15, 1.25, 1.35, 1.5, 1.7, 1.85, 2.0],  # the opening fees to choose from. Lower ones book too slowly (v4-f70 against v4-f85)
    # The cars that book most easily can open lower still. In 80 weeks with random opening fees, the cars of which 94 in 100 book
    # at 0.85 cost 0.85 of the typical fee in the end when they opened at 0.70, against 0.93 when they opened at 0.85. For the
    # other cars a lower opening fee saves nothing and makes more of them late.
    # In play, on 120 weeks: 233 a week more (standard error 99), and more cars on time, because the desk then wins more of these cars (qe-94).
    # Other gates on 80 weeks: 0.97 no gain, 0.90 only 59 more with one week at 89.3% on time, 0.85 111 less (qe-97, qe-90, qe-85)
    "easy": [0.94, 0.72],  # [the share of such cars that book at the lowest opening fee, from which a car may open lower; that lower fee]; 1.0: never
    # The cars that book least easily open higher. In the same 80 weeks, the cars of which fewer than 75 in 100 book at 0.85 found a driver
    # in time 77 times in 100 when they opened at 0.85 and 87 times when they opened at 1.00, and cost 1.09 and 1.13 of the typical fee in the end.
    # In play, with our raises before the last hours: 292 a week less and no more cars on time (qh-75). Off.
    "hard": [0.0, 1.0],  # [the share of such cars that book at the lowest opening fee, below which a car opens higher; the lowest fee for such a car]; 0.0: never
    "rise": [[0.25, 1.15], [0.6, 1.3]],  # raises before the ladder: [share of the time until the ladder, fee over the opening fee]. On 40 weeks: 450 a week more, and more cars on time (y-rise)
    "judge_at": 1.0,  # the fee, over the opening fee, at which we judge the chance of a driver in time
    "driver_towns": False,  # the driver curves count each town's own effect, beyond the drivers who live near it. Measured on 120 weeks: no gain (t-towns)
    "fallback": 1.6,  # what a gig costs when no driver takes it before the ladder
    # A new gig starts below its fee for a few minutes: half of all gigs are taken within a quarter of an hour, so some
    # driver would have come for less. Most drivers see a gig later, and then at its full fee.
    "intro": [0, 1.0],  # [awake minutes, the fee in those minutes over the gig's fee]; 0 minutes: no discount
    "pair_intro": [0, 1.0],  # the same for a pair
    "ladder": [[300, 1.3], [240, 1.6], [180, 2.0], [120, 2.5], [60, 3.0]],  # [awake minutes before the last booking, fee]
    "reach": 60,  # minutes that a driver needs from the booking to the pickup
    "slack": [0, 0.0],  # [minutes, share of the drive]: a gig's pickup window ends this long before the last pickup minute, so a drive that runs long still ends in time
    # A day when drivers stay at home (flu, snow): they give their bookings back just after midnight. Seen in every week of level 7 and 8.
    "short_day_drops": 6,  # this many drops before 02:00 mark the day
    "short_day_steps": [[360, 1.15], [480, 1.35], [600, 1.6]],  # [minute of that day, fee]: the cars due that day go up early, while drivers still plan their day. Steeper steps cost more and gain nothing (sd-*)
    "short_day_quotes": False,  # on such a day, still price the options that need a pickup today
    # The guard of the delivery minimum: on the day when drivers stay at home, up to a quarter of the cars due that day are late.
    # So we never hold more cars due on one day than the week can afford to lose a quarter of.
    "guard_zero": False,  # treat numerical roundoff at the exact late allowance as a spent budget
    "guard_on_time": 0.94,  # the on-time share that the week must keep in the worst case. Measured on 40 weeks: worst week 91.3% without, 94.1% with, the margin unchanged (g94-x)
    "guard_orders": 350,  # the week's orders to count on, before that many are won
    # Two rules for a week in which drivers are scarce from its start. In one ranking week the cars sat (42 without a driver on Monday night, where
    # 37 is the most in 120 practice weeks), 25 of 241 were late by Wednesday, and then the day's limit let the desk quote 3 requests on Friday: ranked, and 18th.
    # The alarm, 35 cars: it rang in 6 of 80 fresh weeks. The week in which the guard had nearly closed the desk made 4,002 more and went from 93.2% to 95.6% on time;
    # over 120 weeks 7 a week more (standard error 36), every week ranked, the lowest unchanged (bc-35). With the quotes of the day stopped as well: one week at 92.9% (bb-35).
    # At 30 cars it rings on twice as many mornings and costs more than it saves (bb-30, st-bc30). When it also told the guard that the week's bad day had come: one week at 88% (ba-35).
    "backlog_alarm": 35,  # this many cars without a driver at 06:00 mark the day as one with few drivers, as the night's drops do; 0: never
    "alarm_quotes": True,  # on a day that the alarm marked, still price the cars that need a pickup that day: the alarm then only raises the fees of the cars that wait
    "guard_safe": 1.0,  # a car whose chance of a driver in time is at least this does not count against the day's limit: it raises the week's on-time share; 1.0: every car counts
    "guard_spent_safe": 0.95,  # (it changed no week of 136: the allowance is spent only in a week like the one above) the same, but only once the week's allowance of late cars is spent: stopping then protects nothing, and a safe car still raises the on-time share; 1.0: never
    "guard_early": [0.0, 2],  # [the on-time share that the week must keep in the worst case for the cars due early in the week, the last such day (2: Wednesday)]: a late car early in the week is made up for by the orders that follow, one on Friday is not; 0.0: one share for every day
    "guard_ahead": False,  # count on more when the week wins orders at a faster pace: in the weeks with the dearest competitor the day's limit turns 62 options away, in the cheapest 9
    "guard_pace": False,  # count on fewer when the week wins orders at a slower pace: small weeks have the lowest on-time shares (120 weeks: 95.0% under 330 orders, 97.0% over 380)
    "guard_loss": 0.25,  # the share of a day's cars that a day with few drivers makes late
    "guard_loss_after": 0.1,  # ... once the week's day with few drivers has come
    "guard_calm": [0.15, 26],  # [the share of a day's cars that a day with few drivers makes late in a calm week, the cars without a driver at midnight from which a week is not calm]: every week that a smaller reserve hurt had 28 or more cars waiting at some midnight before its bad day; 0.0: one reserve for every week
    # The reserve was the same for every day, and it cost the most where it protected nothing: of the 235 requests a week that the desk declines, 37 are over the day's limit,
    # good cars (a driver in time for 88 in 100, 26 euros of expected profit each), and most are Friday's requests for cars due on Monday. In one week in five no night of drops
    # comes at all, and there the limit turned 71 to 113 options a week away.
    "guard_loss_later": 0.1,  # ... of the cars due after the weekend, whatever the week has seen: they have the weekend to find a driver. On 40 revealed weeks 3% of them are late, 11% in the worst week, with or without a night of drops on that Monday; 0.0: as any other day
    # The week's two unannounced events, a price war day and an outage day in one region, as cases that each answer weighs (desk/market.py).
    # On 80 weeks with random prices: the next answer foretold 3.1% better than with the week's parts alone. In play, on 80 fresh weeks: 7 a week
    # less (standard error 99), 4 orders fewer (qv-ev). Off: the wide belief of each morning already follows a war within a few answers.
    "events": False,
    "calm_sd": 0.7,  # how far a calm day's level lies from the day before, in the curve's units, when the events are cases of their own
    "regimes": False,  # hold two beliefs about the day's level each morning: an ordinary day near the week's level, and a price war day
    "slope_scale": 1.0,  # a factor on the fitted slope of the dealer curve
    "dealer_sd": 0.0,  # how far a dealer's own level may lie from the day's, in the curve's units; 0: one level for all dealers. No gain, also with the week's parts below (d-sd*, qd-03)
    # This week's own parts of the competitor's prices, learned like the day's level: [how far the part lies from zero, in the curve's units, and the share of it that holds overnight].
    # On 80 weeks with random prices they predict the next answer 3.9% better. In play, on 120 weeks: 314 a week more than without them (standard error 105), and 0.8 fewer late cars a week (q-both)
    "tilt": [0.5, 0.7],  # by the lane's length: once a week the competitor's price list changes shape. 0: no tilt
    "places": [0.6, 0.7],  # a level for each pickup place and each delivery place: some mornings the competitor moves its prices there. 0: none
    "outages": False,  # look for the region where the competitor is down for a day, and price its dealers higher. Measured: found in 18 of 20 weeks, but mostly in the afternoon; no gain (v9-outage)
    "late_opening": 1.2,  # a late car: the fee until the next refund step comes near
    "late_ladder": [[240, 1.5], [120, 2.0]],
}

URGENT = ["order_changed", "order_cancelled", "visit_failed", "gig_expired", "gig_dropped", "no_show", "offer_answered"]
HOME_KM = 40  # a gig that ends this near a driver's home saves them the trip home
MARKUPS = [0.96 + 0.02 * step for step in range(83)]  # the prices to choose from, over the list price: 0.96 to 2.6
PAIRS = FITTED.get("pair_share") or {"lanes": {}, "bands": [], "by_band": [0.0], "saving": 0.0}  # each lane's share of cars that went in a pair, and what a pair saves
AVERAGE_LEVEL = FITTED["dealer"]["level"]  # the day's level of the dealer curve on an average day of an average world
REQUEST_MINUTES = 5 * 10 * HOUR  # requests arrive on five days, almost all from 08:00 to 18:00


class Plan(NamedTuple):
    """How we would move a car: the opening fee over the typical fee, the chance that a driver takes
    it in time, what we expect it to cost in cents, a late car's cost included, and its last pickup minute."""
    fee: float
    chance: float
    cost: float
    until: int = 0
    paid: float = 0.0  # the fee that we expect to pay, in cents: the part of `cost` without the late car's cost


class Desk:
    def __init__(self, level: int, config: Optional[dict], world_map: dict, roster: list[dict], now: int, ends_at: int):
        unknown = set(config or {}) - set(SETTINGS)
        if unknown:
            raise ValueError(f"no such setting: {', '.join(sorted(unknown))}")
        self.set = {**SETTINGS, **(config or {})}
        self.level, self.now, self.ends_at = level, now, ends_at
        self.books = Books()
        self.minutes = {(road["from"], road["to"]): road["minutes"] for road in world_map["roads"]}
        self.km = {(road["from"], road["to"]): road["km"] for road in world_map["roads"]}
        self.drivers = {driver["id"]: driver for driver in roster}
        self.near = drivers_near(world_map["places"], roster)  # place -> the drivers who live within 100 km
        places = {place["id"]: place for place in world_map["places"]}
        self.air = {(a, b): air_km(places[a], places[b]) for a in places for b in places}  # straight-line km
        self.free: dict[str, tuple[str, int]] = {}  # driver id -> (place, minute): they have just delivered there, and got no offer yet
        self.night_drops: Counter = Counter()  # day -> bookings given back before 02:00
        self.short_days: set[int] = set()  # the days when drivers stay at home
        self.drop_days: set[int] = set()  # those of them that began with a night of dropped bookings: the week's one such day, which the guard waits for
        self.mornings: set[int] = set()  # the days whose morning backlog has been looked at
        self.nights: dict[int, int] = {}  # day -> our cars without a driver at its midnight
        self.raised: set[str] = set()  # gigs that already got the short day's fees
        self.alone: set[str] = set()  # orders that go in a gig of their own from now on: their pair found no driver in time
        self.dropped: set[str] = set()  # gigs that a driver gave back since the last look
        self.needs_sync = False  # the world refused a withdrawal: the books may be wrong
        self.due_now: Counter = Counter()  # during one look: our cars by the day of their last pickup
        self.limit_now = self.limit_early = float("inf")
        self.spare_now = True
        self.pairable: list[dict] = []  # during one look: the waiting orders that can go in a pair
        kind, more = (RegimeMarket, {}) if self.set["regimes"] else (EventMarket, {"calm_sd": self.set["calm_sd"]}) if self.set["events"] else (Market, {})
        self.market = kind(level, **more, regions={town: {place for place in places if self.air[(town, place)] <= 80} for town in places}, outages=self.set["outages"], dealer_sd=self.set["dealer_sd"], slope_scale=self.set["slope_scale"],
                                                                           minutes=self.minutes, tilt=tuple(self.set["tilt"]), places=tuple(self.set["places"]))
        self.tally: Counter = Counter()  # what the desk did with each request, for the day's report
        if self.set["explore"]:
            self.set["max_waiting"], self.set["max_urgent"] = self.set["explore_caps"][len(roster) % len(self.set["explore_caps"])], 10 ** 6
        self.plans: dict[str, dict[str, Plan]] = {}  # request id -> option -> the plan behind our price
        self.asked: dict[str, tuple[float, int, bool]] = {}  # request id -> (lowest markup, the dealer's trust, only later options) of our quote
        self.facts: dict[str, notes.Facts] = {}  # request id -> what its note says
        self.judging: set[str] = set()  # requests with a quote that the dealer has not judged yet
        self.hold: dict[str, int] = {}  # order id -> no new gig before this minute, after the world refused one
        self.won_at: dict[str, int] = {}  # order id -> the minute we won it
        self.first_day = now // DAY if self.set["days_from_join"] else 0  # the day from which the driver curves count the week's days
        self.looked: dict[str, dict[str, int]] = defaultdict(dict)  # order id -> the drivers who viewed a gig of it, with the minute of their last view
        self.tried: dict[str, set] = defaultdict(set)  # order id -> the drivers who got an offer of it as its viewers
        self.off_app: set[str] = set()  # the orders that wait for a partner at this look: no driver can see them yet
        self.bare: set[str] = set()  # orders whose gigs go without stop windows of their own: one of them has ended
        self.changed: set[str] = set()  # orders with a change of plan since the last look
        self.last_seq = -1  # the last event that the desk has read
        self.journal: Optional[IO] = None  # the live desk writes each quote here, so a desk that starts again knows what it asked
        self.outbox: list[dict] = []
        self.meta: list[dict] = []  # what the desk must remember about each action in the outbox
        self.sent: tuple[list[dict], list[dict]] = ([], [])

    # --- the loop's side ---

    def on_event(self, event: dict) -> None:
        if event["seq"] <= self.last_seq:  # after a server restart, an answer can repeat events
            return
        self.last_seq = event["seq"]
        self.now = max(self.now, event["at"])
        kind = event["kind"]
        if kind == "price_request":
            self.facts[event["request"]["id"]] = notes.read(event["request"].get("note"), event["request"]["arrivedAt"])
        elif kind == "gig_viewed" and self.set["viewer_offers"][0]:
            for order_id, _ in getattr(self.books.gigs.get(event["gigId"]), "legs", ()):
                self.looked[order_id][event["driverId"]] = event["at"]
        elif kind == "order_changed":
            self.changed.add(event["order"]["id"])
        elif kind == "gig_expired":
            gig = self.books.gigs.get(event["gigId"])
            if gig:  # one of its windows has ended: post without them, unless they are a day's hours from the note, which move to the next day
                self.bare.update(key[0] for key in gig.legs if not self.noted(self.facts.get(key[0])))
        elif kind == "delivered" and self.set["offers"]:
            gig = self.books.gigs.get(event["gigId"])
            if gig and gig.driver and len(gig.legs) == 1:  # the gig's last car: the driver is free there
                self.free[gig.driver] = (event["placeId"], event["at"])
        elif kind == "gig_dropped" and self.set["drop_bump"] != 1.0 and event["at"] % DAY >= 2 * HOUR:
            self.dropped.add(event["gigId"])
        elif kind == "gig_dropped" and event["at"] % DAY < 2 * HOUR:
            day = event["at"] // DAY
            self.night_drops[day] += 1
            if self.night_drops[day] == self.set["short_day_drops"]:
                self.short_days.add(day)
                self.drop_days.add(day)
                print(f"{clock(event['at'])} {self.night_drops[day]} drivers gave their bookings back in the night: a day with few drivers")
        elif kind == "offer_answered":
            print(f"answer: {json.dumps({'at': event['at'], 'gig': event['gigId'], 'driver': event['driverId'], 'answer': event['answer']})}")
        elif kind == "visit_failed":
            self.alone.add(event["orderId"])
        elif kind in ("order_won", "order_lost"):
            request_id = event["order"]["id"] if kind == "order_won" else event["requestId"]
            if kind == "order_won":
                self.won_at[request_id] = event["at"]
                if self.set["days_from_join"]:  # after a restart: the desk joined no later than its first order
                    self.first_day = min(self.first_day, event["at"] // DAY)
            self.judging.discard(request_id)
            self.learn(request_id, event["order"] if kind == "order_won" else None, event["at"])
        self.books.on_event(event)

    def rejoin(self, history: list[dict], snapshot: dict, journal: Optional[Path] = None) -> None:
        """Rebuilds the books of a week that is under way: every event so far, then the world's own
        list of our orders and gigs. The journal holds what the events do not: the prices that we
        asked, which the market model learns from."""
        if journal is not None:
            journal.parent.mkdir(parents=True, exist_ok=True)
            for line in journal.read_text(encoding="utf-8").splitlines() if journal.exists() else ():
                try:
                    entry = json.loads(line)
                    if "night" in entry:
                        self.nights[int(entry["night"])] = int(entry["waiting"])
                        continue
                    self.asked[entry["request"]] = tuple(entry["asked"])
                    self.plans[entry["request"]] = {kind: Plan(fee, 0.95, 0.0, 0) for kind, fee in entry["fees"].items()}
                except (ValueError, KeyError, TypeError):
                    continue  # a line cut off by a crash
            self.journal = open(journal, "a", buffering=1, encoding="utf-8")
        for event in history:
            self.on_event(event)
        self.changed.clear()  # the snapshot already shows every change of plan
        self.sync(snapshot)

    def sync(self, snapshot: dict) -> None:
        """Makes the books agree with the world's own list of our orders and gigs. After a restart,
        ours or the server's, the events alone do not say which of our last actions the world took."""
        books = self.books
        books.orders = {order["id"]: order for order in snapshot["orders"] if order["status"] not in ("cancelled", "delivered") and order["id"] in books.requests}
        books.done = {order["id"] for order in snapshot["orders"] if order["status"] == "delivered"}
        books.gigs, books.carrier = {}, {}
        for listed in snapshot["gigs"]:
            for stop in listed["stops"]:
                if stop["kind"] == "pickup":
                    books.first_posted[stop["orderId"]] = min(listed["postedAt"], books.first_posted.get(stop["orderId"], listed["postedAt"]))
            if listed["status"] not in ("open", "booked", "working"):
                continue
            legs = [(stop["orderId"], stop["leg"]) for stop in listed["stops"] if stop["kind"] == "pickup"
                    and stop["orderId"] in books.orders and books.orders[stop["orderId"]]["deliveredAt"][stop["leg"]] is None
                    and not any(gig == listed["id"] for _, _, gig in books.failed.get((stop["orderId"], stop["leg"]), []))]  # a failed visit took the car out of that gig
            if not legs:
                continue
            self.now = max(self.now, snapshot["now"])
            stage, until = min((self.stage(books.orders[order_id]) for order_id in {key[0] for key in legs}), key=lambda pair: (-pair[0], pair[1]))
            # A working gig still lists its original stops. Register only cars it still carries.
            stops = [stop for stop in listed["stops"] if (stop["orderId"], stop["leg"]) in legs]
            gig = books.posted({"type": "post", "stops": stops, "audience": listed["audience"], "schedule": listed["schedule"]}, listed["id"], listed["postedAt"], until, stage)
            gig.status, gig.driver, gig.fee = listed["status"], listed["driverId"], listed["feeCents"]
        # Every open request gets a quote again: a new quote replaces the earlier one.
        for request in snapshot["openRequests"]:
            books.requests.setdefault(request["id"], request)
            self.facts.setdefault(request["id"], notes.read(request.get("note"), request["arrivedAt"]))
        books.unquoted = [request["id"] for request in snapshot["openRequests"]]
        self.sent, self.meta, self.outbox = ([], []), [], []

    def decide(self, now: int, quotes_only: bool = False) -> list[dict]:
        """The actions for this minute. Their results go to `results` before the next events. With `quotes_only`
        the desk only answers the requests that wait: in the final a quote does not wait for the next look."""
        self.now = now
        self.note_night()
        if quotes_only:
            self.quote_requests()
        else:
            self.replan()
            self.watch_backlog()
            self.quote_requests()
            self.review_open_gigs()
            self.post_free_cars()
            self.raise_for_short_day()
            if self.set["offers"]:
                self.offer_to_free_drivers()
            if self.set["viewer_offers"][0]:
                self.offer_to_viewers()
        actions, self.outbox = self.outbox, []
        self.sent, self.meta = (actions, self.meta), []
        return actions

    def results(self, results: list[dict]) -> None:
        actions, meta = self.sent
        self.sent = ([], [])
        for action, info, result in zip(actions, meta, results):
            if action["type"] == "post":
                if result["ok"]:
                    self.books.posted(action, result["id"], info["at"], info["until"], info["stage"])
                elif info.get("pair"):  # each car goes alone
                    print(f"{clock(info['at'])} pair refused for {info['pair']}: {result['reason']}")
                    self.alone.update(info["pair"])
                else:  # try again later, without stop windows of our own
                    print(f"{clock(info['at'])} post refused for {info['order']}: {result['reason']}")
                    self.hold[info["order"]] = info["at"] + 30
                    self.bare.add(info["order"])
            elif not result["ok"]:
                print(f"{clock(self.now)} {action['type']} refused: {result['reason']}")
                self.needs_sync = self.needs_sync or action["type"] == "withdraw"

    def next_look(self, now: int) -> int:
        """The latest minute for the next look at the world."""
        if now < LAST_REQUEST + 15:
            return now + self.set["tick"] if AWAKE[0] <= now % DAY < AWAKE[1] else (now // DAY + (now % DAY >= AWAKE[1])) * DAY + AWAKE[0]
        waits = [gig.until + 1 for gig in self.books.gigs.values() if gig.status == "open" and gig.until >= now]
        waits += [minute for minute in self.hold.values() if minute > now]
        if self.set["viewer_offers"][0] and AWAKE[0] <= now % DAY < AWAKE[1] and any(gig.status == "open" for gig in self.books.gigs.values()):
            waits.append(now + 30)  # an offer is open for 10 minutes: look again soon, for the next viewers
        return min([now + 3 * HOUR] + waits)

    def wake_on(self, now: int) -> list[str]:
        """The events that cannot wait for the next look. At night, a price request is one."""
        asleep = now < LAST_REQUEST + 15 and not AWAKE[0] <= now % DAY < AWAKE[1]
        return URGENT + ["price_request"] * asleep + ["delivered"] * bool(self.set["offers"])

    def send(self, action: dict, **info) -> None:
        for stop in action.get("stops", ()):  # the world refuses a whole batch for one window that ends before it starts
            if "window" in stop and stop["window"]["to"] < stop["window"]["from"]:
                print(f"{clock(self.now)} dropped a window that ends before it starts: {stop}")
                del stop["window"]
        self.outbox.append(action)
        self.meta.append(info)

    # --- quotes ---

    def urgent(self) -> int:
        """Our orders without a driver whose last pickup is near: their fee is on the ladder. Many of
        them at once mean that drivers are short today, whatever the reason."""
        ladder = max(minutes for minutes, _ in self.set["ladder"])
        return sum(1 for order in self.books.waiting() if awake_between(self.now, order["lastPickupAt"] - self.set["reach"]) <= ladder)

    def load(self) -> float:
        """Our orders without a driver, and half of the quotes that dealers have not judged yet. A car that waits
        for a partner is not in the app, so it does not compete for drivers yet."""
        return sum(1 for order in self.books.waiting() if order["id"] not in self.off_app) + len(self.judging) / 2

    def quote_requests(self) -> None:
        self.off_app = {order["id"] for order in self.books.waiting() if self.waits_for_partner(order)} if self.set["pair_hold"][0] else set()
        full = self.load() >= self.set["max_waiting"] or self.urgent() >= self.set["max_urgent"]
        self.due_now, self.limit_now, self.limit_early, self.limit_later = self.due(), self.day_limit(), self.day_limit(early=True), self.day_limit(later=True)
        # The week has on-time share to spare when few of its cars are late or at risk: only then it takes the riskier long lanes.
        self.spare_now = (self.books.late_count + self.urgent()) / max(self.books.won_count, self.set["guard_orders"] * self.week_left() / 2) < self.set["spare"]
        self.pairable = [order for order in self.books.orders.values() if self.can_pair(order)] if self.books.unquoted else []
        requests, self.books.unquoted = self.books.unquoted, []
        for request_id in requests:
            request = self.books.requests.get(request_id)
            if request is None or request["respondBy"] <= self.now:
                continue
            prices = self.prices(request, full)
            if prices:
                self.books.quotes[request_id] = prices
                self.judging.add(request_id)
                self.send({"type": "quote", "requestId": request_id, "prices": prices})

    def prices(self, request: dict, full: bool) -> Optional[dict]:
        """A price for each option that we offer; None for no quote. An option gets the price with the
        highest expected profit: the chance that the dealer takes it, times what it leaves after the
        car's expected cost, plus what the dealer's trust gains from one more order on time."""
        options = request["options"]
        if self.level <= 3:  # every quote wins the first option at its list price, so here no quote declines
            plan = None if full else self.plan(request, options[0], request["respondBy"])
            if plan is None or options[0]["listPriceCents"] - plan.cost < self.set["min_profit"]:
                return None
            self.plans[request["id"]] = {options[0]["kind"]: plan}
            return {options[0]["kind"]: options[0]["listPriceCents"]}
        decline = {options[0]["kind"]: euros(options[0]["listPriceCents"] * self.set["decline"])}
        facts = self.facts.get(request["id"]) or notes.Facts()
        no_trade_in = len(request["legs"]) > 1 and (not self.set["trade_ins"] or self.noted(facts) or facts.ready_at is not None)
        if full or no_trade_in or facts.unsure or facts.summer_tyres:
            self.tally["declined: too many orders without a driver" if full else "declined: trade-in" if no_trade_in else "declined: the note"] += 1
            return decline
        if self.set["explore"]:
            rng = random.Random(f"{self.set['seed']}:{request['id']}")
            markup, mode = rng.uniform(1.0, 2.0), rng.random()
            offered = options if mode < 0.5 else options[:1] if mode < 0.75 else options[-1:]
            return {option["kind"]: euros(option["listPriceCents"] * markup) for option in offered}
        dealer = request["dealerId"]
        trust = self.books.trust[dealer]
        gain = self.set["trust_value"] * self.trust_point(dealer) if trust + self.pending(dealer) < 25 else 0.0  # the dealer counts at most 25 orders
        prices, plans, markups = {}, {}, []
        for option in options:
            plan = self.plan(request, option, request["respondBy"])
            if plan is None:
                self.tally["options without a driver in time"] += 1
                continue
            limit = self.limit_later if plan.until // DAY > 4 else self.limit_early if plan.until // DAY <= self.set["guard_early"][1] else self.limit_now
            safe = min(self.set["guard_safe"], self.set["guard_spent_safe"]) if limit <= 0 else self.set["guard_safe"]  # a limit of zero or less: the allowance is spent
            if self.due_now[plan.until // DAY] + 1 > limit and plan.chance < safe:
                self.tally["options over the day's limit"] += 1
                continue
            if self.set["pairs"] and self.set["pair_quotes"] and self.level >= 4:
                plan = self.with_partner(request, option, plan)
            if self.set["pairs"] and self.set["pair_share"] and self.level >= 4 and len(request["legs"]) == 1:
                plan = plan._replace(cost=plan.cost - self.set["pair_share"] * self.pair_share(request) * PAIRS["saving"] * plan.paid)
            only_later = options[0]["kind"] not in prices and option is not options[0]
            chance = self.market.price_curve(request, trust, only_later, request["respondBy"])
            profit, markup = max((chance(m) * (m * option["listPriceCents"] - plan.cost + plan.chance * gain), m) for m in MARKUPS)
            if profit >= self.set["min_profit"]:
                drive = self.minutes[(request["legs"][0]["pickup"]["placeId"], request["legs"][0]["delivery"]["placeId"])]
                factor = self.set["greed_short"][1] if drive <= self.set["greed_short"][0] else self.set["greed_long"][1] if drive >= self.set["greed_long"][0] else self.set["greed"]
                if self.set["greed_slope"] or self.set["greed_load"][0]:  # a cheap competitor, or drivers with time to spare, leave less room above the price that the models choose
                    low, high = self.set["greed_range"]
                    factor += self.set["greed_slope"] * (self.market.mean - AVERAGE_LEVEL) + self.set["greed_load"][0] * (self.load() - self.set["greed_load"][1])
                    factor = max(low, min(high, factor))
                if self.set["greed_later"] and plan.until // DAY > 4:
                    factor = self.set["greed_later"]
                markup *= factor
                prices[option["kind"]], plans[option["kind"]] = euros(markup * option["listPriceCents"]), plan
                markups.append(markup)
        if len(prices) > 1 and self.set["fast_factor"] != 1.0:  # steer the dealer to a later option
            fast = next(iter(prices))
            prices[fast] = euros(prices[fast] * self.set["fast_factor"])
        if not prices:
            self.tally["declined: no option worth a price"] += 1
            return decline
        self.tally["quoted"] += 1
        self.plans[request["id"]] = plans
        self.due_now[next(iter(plans.values())).until // DAY] += 0.6
        self.asked[request["id"]] = (min(markups), trust, options[0]["kind"] not in prices)
        if self.journal:
            self.journal.write(json.dumps({"request": request["id"], "asked": self.asked[request["id"]], "fees": {kind: plan.fee for kind, plan in plans.items()}}) + "\n")
        return prices

    def plan(self, request: dict, option: dict, post_at: int) -> Optional[Plan]:
        """The opening fee with the lowest expected cost, among the fees at which a driver takes the car
        in time often enough. None when no fee does."""
        if len(request["legs"]) > 1:
            return self.plan_trade_in(request, option, post_at)
        facts = self.facts.get(request["id"]) or notes.Facts()
        leg = self.real(request["legs"][0], facts)
        deadline = option["deadline"]
        ready = max(leg["pickup"]["window"]["from"], facts.ready_at or 0)
        if ready // DAY > leg["pickup"]["window"]["from"] // DAY:  # a car that is ready a day or more later moves its deadline by the same days
            deadline += (ready // DAY - leg["pickup"]["window"]["from"] // DAY) * DAY
        until = self.last_pickup({"legs": [leg] + request["legs"][1:], "deliveredAt": [None] * len(request["legs"])}, min(deadline, facts.deliver_by or deadline))
        if until - max(post_at, ready) < HOUR:
            return None
        if until // DAY in self.short_days and not self.set["short_day_quotes"] and not (self.set["alarm_quotes"] and until // DAY not in self.drop_days):
            return None  # few drivers work today: no new car that needs one today
        return self.best_fee(leg, request["referenceFeeCents"], post_at, until, self.late_cost(request["dealerId"], option["listPriceCents"]))

    def plan_trade_in(self, request: dict, option: dict, post_at: int) -> Optional[Plan]:
        """A trade-in goes as one gig at one fee: the new car to the customer inside the booked hour,
        then the old car back in the same visit. None when the two drives pass the 12 hours of a
        gig with two cars, or when a driver is unlikely to take it in time."""
        legs = request["legs"]
        trip = {"legs": legs, "deliveredAt": [None, None]}
        drive = self.drive(trip, [0, 1])
        if self.level < 4 or len(legs) != 2 or drive > 12 * HOUR - 20:
            return None
        until = self.last_pickup(trip, option["deadline"])
        if until - max(post_at, legs[0]["pickup"]["window"]["from"]) < HOUR:
            return None
        if until // DAY in self.short_days and not self.set["short_day_quotes"] and not (self.set["alarm_quotes"] and until // DAY not in self.drop_days):
            return None
        pickup, delivery = legs[0]["pickup"], legs[0]["delivery"]
        fee = self.set["trade_in_fee"]
        x = gig_features(awake_between(post_at, until) / 60, drive / 60, fee, self.near[pickup["placeId"]], self.near[delivery["placeId"]],
                         any(leg["car"]["premium"] for leg in legs), False, True, post_at // DAY - self.first_day, self.load())
        chance = logistic(FITTED["driver_in_time"], x)
        if chance < (self.set["trade_in_chance"] or (self.set["spare_chance"] if self.spare_now else self.set["min_chance"])):
            return None
        paid = request["referenceFeeCents"] * self.set["trade_in_cost"]
        return Plan(fee, chance, paid + (1 - chance) * self.late_cost(request["dealerId"], option["listPriceCents"]), until, paid)

    def best_fee(self, leg: dict, reference: float, post_at: int, until: int, late: float) -> Optional[Plan]:
        pickup, delivery = leg["pickup"], leg["delivery"]
        towns = (pickup["placeId"], delivery["placeId"]) if self.set["driver_towns"] else ()
        best, floor = None, 0.0
        fees = self.set["fees"]
        if self.set["easy"][0] < 1:
            lowest = gig_features(awake_between(post_at, until) / 60, self.minutes[(pickup["placeId"], delivery["placeId"])] / 60, fees[0], self.near[pickup["placeId"]],
                                  self.near[delivery["placeId"]], leg["car"]["premium"], pickup["privateAddress"], delivery["privateAddress"], post_at // DAY - self.first_day, self.load())
            if logistic(FITTED["booked_at_opening"], lowest) >= self.set["easy"][0]:
                fees = [self.set["easy"][1]] + fees
        if self.set["hard"][0] > 0:
            lowest = gig_features(awake_between(post_at, until) / 60, self.minutes[(pickup["placeId"], delivery["placeId"])] / 60, self.set["fees"][0], self.near[pickup["placeId"]],
                                  self.near[delivery["placeId"]], leg["car"]["premium"], pickup["privateAddress"], delivery["privateAddress"], post_at // DAY - self.first_day, self.load())
            if logistic(FITTED["booked_at_opening"], lowest) < self.set["hard"][0]:
                fees = [fee for fee in fees if fee >= self.set["hard"][1]]
        for fee in fees:
            x = gig_features(awake_between(post_at, until) / 60, self.minutes[(pickup["placeId"], delivery["placeId"])] / 60, fee, self.near[pickup["placeId"]],
                             self.near[delivery["placeId"]], leg["car"]["premium"], pickup["privateAddress"], delivery["privateAddress"], post_at // DAY - self.first_day, self.load())
            # The fitted curve gives the share of gigs that a driver takes at a fee or below it: the steps of the schedule walk up it.
            paid, taken = 0.0, 0.0
            for step in [1.0] + [ratio for _, ratio in self.set["rise"]]:
                share = max(taken, logistic(FITTED["booked_at_opening"], at_fee(x, fee * step), towns))
                paid, taken = paid + (share - taken) * fee * step, share
            paid = reference * (paid + (1 - taken) * max(self.set["fallback"], 1.25 * fee))
            chance = floor = max(floor, logistic(FITTED["driver_in_time"], at_fee(x, fee * self.set["judge_at"]), towns))  # a higher fee never lowers the chance
            enough = (self.set["min_chance"] if not self.spare_now else self.set["long_chance"][1] if x[2] * 60 >= self.set["long_chance"][0]
                      else self.set["private_chance"] if x[8] or x[9] else self.set["spare_chance"])
            if chance >= enough and (best is None or paid + (1 - chance) * late < best.cost):
                best = Plan(fee, chance, paid + (1 - chance) * late, until, paid)
        return best

    def with_partner(self, request: dict, option: dict, plan: Plan) -> Plan:
        """A request whose car pairs with an order that waits for a driver costs less than alone: the
        pair's fee, less the fee that the waiting car would need by itself."""
        mine = {"id": request["id"], "dealerId": request["dealerId"], "option": option["kind"], "priceCents": 0, "legs": request["legs"],
                "deliveredAt": [None] * len(request["legs"]), "deadline": option["deadline"], "lastPickupAt": plan.until}
        if not self.can_pair(mine):
            return plan
        partners = [other for other in self.pairable if self.pair_plan(mine, other) or self.pair_plan(other, mine)]
        if not partners:
            return plan
        reference = request["referenceFeeCents"]
        other = max(self.books.requests[partner["id"]]["referenceFeeCents"] for partner in partners)
        together = max(0.3 * reference, self.set["pair_fee"] * (reference + other) - other)
        saving = self.set["pair_odds"] * max(0.0, plan.paid - together)
        self.tally["quotes with a partner waiting"] += 1
        return plan._replace(cost=plan.cost - saving)

    @staticmethod
    def pair_share(request: dict) -> float:
        """The share of this lane's cars that went in a return-trip pair in the revealed weeks. A lane without
        one has the share of the lanes of its length."""
        leg = request["legs"][0]
        share = PAIRS["lanes"].get(f'{leg["pickup"]["placeId"]}>{leg["delivery"]["placeId"]}')
        if share is None:
            share = PAIRS["by_band"][sum(request["referenceFeeCents"] > edge for edge in PAIRS["bands"])]
        return share

    def due(self) -> Counter:
        """Our cars by the day of their last pickup, and for each quote that a dealer has not judged yet, six tenths of a car."""
        days: Counter = Counter()
        for order in self.books.orders.values():
            stage, until = self.stage(order)
            if stage == 0:
                days[until // DAY] += 1
        for request_id in self.judging:
            plans = self.plans.get(request_id)
            if plans:
                days[next(iter(plans.values())).until // DAY] += 0.6
        return days

    def day_limit(self, early: bool = False, later: bool = False) -> float:
        """The most cars that may be due on one day: if that day turns out to have few drivers, the week still keeps its on-time share.
        With `early`, the limit for a day early in the week; with `later`, for a day after the weekend."""
        seen = any(day >= self.now // DAY - 6 for day in self.drop_days)  # a morning with many cars waiting does not count: the night of drops may still come
        orders = self.set["guard_orders"] * self.week_left()
        if self.set["guard_pace"] and self.week_share() >= 0.2:  # from Monday evening on, the week's own pace says how many orders it will have
            orders = min(orders, self.books.won_count / self.week_share())
        if self.set["guard_ahead"] and self.week_share() >= 0.2:
            orders = max(orders, self.books.won_count / self.week_share())
        target = self.set["guard_early"][0] if early and self.set["guard_early"][0] else self.set["guard_on_time"]
        allowed_late = (1 - target) * max(self.books.won_count, orders) - self.books.late_count - self.urgent()
        if self.set["guard_zero"] and abs(allowed_late) < 1e-9:
            allowed_late = 0.0
        loss = self.set["guard_loss_after"] if seen else self.set["guard_calm"][0] if self.set["guard_calm"][0] and self.calm() else self.set["guard_loss"]
        if later and self.set["guard_loss_later"]:
            loss = min(loss, self.set["guard_loss_later"])
        return allowed_late / loss

    def note_night(self) -> None:
        """Writes down our cars without a driver at each midnight. The live desk also writes it to its journal: a desk that starts again reads it there.
        A first look that comes later in the night still counts: no driver reads the app before 07:00, so the count stands still."""
        day = self.now // DAY
        if day not in self.nights and self.now % DAY < 6 * HOUR:
            self.nights[day] = len(self.books.waiting())
            if self.journal:
                self.journal.write(json.dumps({"night": day, "waiting": self.nights[day]}) + "\n")

    def calm(self) -> bool:
        """Drivers are not scarce this week, as far as it shows: at every midnight since Monday few of our cars had no driver.
        Not on Monday, which has no midnight behind it, and not when a midnight is missing: after a late join, or a restart without its journal."""
        day = self.now // DAY
        monday = day - day % 7
        return day > monday and all(self.nights.get(night, 10 ** 6) < self.set["guard_calm"][1] for night in range(monday + 1, day + 1))

    def week_left(self) -> float:
        """The share of the week's five request days that the desk plays: all of them, unless it joined late and counts its days from the join."""
        return max(1, 5 - self.first_day) / 5

    def week_share(self) -> float:
        """The share of the week's request hours that have passed."""
        return sum(min(10 * HOUR, max(0, min(self.now, day * DAY + 18 * HOUR) - (day * DAY + 8 * HOUR))) for day in range(5)) / REQUEST_MINUTES

    def late_cost(self, dealer: str, list_price: int) -> float:
        """What a late car costs beyond its fee: a share of its price, and half of the dealer's trust."""
        trust = self.books.trust[dealer]
        return self.set["late_cost"] * list_price + self.set["trust_late"] * (trust - trust // 2) * self.trust_point(dealer)

    def trust_point(self, dealer: str) -> float:
        """What one more order on time is worth, in cents: the dealer then accepts 1% more on each
        later order of the week. A dealer's size is about the same in every world."""
        done = sum(min(10 * HOUR, max(0, min(self.now, day * DAY + 18 * HOUR) - (day * DAY + 8 * HOUR))) for day in range(5)) / REQUEST_MINUTES
        weekly = FITTED["dealer_requests_a_week"].get(dealer, self.books.dealer_requests[dealer] / max(done, 0.2))
        price = FITTED["dealer_list_price"].get(dealer, 8000)
        return 0.01 * weekly * (1 - done) * self.set["win_share"] * price

    def pending(self, dealer: str) -> int:
        """The dealer's orders that we hold and have not delivered yet."""
        return sum(1 for order in self.books.orders.values() if order["dealerId"] == dealer)

    def learn(self, request_id: str, order: Optional[dict], at: int) -> None:
        """Tells the market model what the dealer did with our quote."""
        asked, request = self.asked.pop(request_id, None), self.books.requests.get(request_id)
        if asked is None or request is None:
            return
        markup, trust, only_later = asked
        if order is not None:  # the dealer took this option at this price
            lists = {option["kind"]: option["listPriceCents"] for option in request["options"]}
            markup = order["priceCents"] / lists[order["option"]]
        self.market.learn(request, markup, trust, only_later, order is not None, at // DAY, at)

    # --- gigs ---

    def reference_of(self, legs: list) -> float:
        """The typical fee of a gig with these cars, in cents. A pair of orders costs a share of the sum."""
        orders = {order_id for order_id, _ in legs}
        total = sum(self.books.requests[order_id]["referenceFeeCents"] * sum(1 for key in legs if key[0] == order_id) / len(self.books.requests[order_id]["legs"]) for order_id in orders)
        return total * (self.set["pair_fee"] if len(orders) > 1 else 1.0)

    def on_ladder(self, until: int) -> bool:
        """The last pickup is so near that the fee is on the ladder."""
        return awake_between(self.now, until - self.set["reach"]) <= max(minutes for minutes, _ in self.set["ladder"])

    def can_pair(self, order: dict) -> bool:
        """A one-car order between dealer sites with nothing special about it, still on time and not urgent,
        that no driver holds: not posted yet, or alone in an open gig."""
        facts = self.facts.get(order["id"]) or notes.Facts()
        leg = order["legs"][0]
        if (len(order["legs"]) != 1 or order["deliveredAt"][0] is not None or order["id"] in self.alone or self.hold.get(order["id"], 0) > self.now
                or leg["pickup"]["privateAddress"] or leg["delivery"]["privateAddress"] or leg["car"]["premium"]
                or self.noted(facts) or facts.ready_at is not None or self.books.failed.get((order["id"], 0))):
            return False
        stage, until = self.stage(order)
        if stage != 0 or self.on_ladder(until) or until // DAY in self.short_days:
            return False
        gig = self.books.gigs.get(self.books.carrier.get((order["id"], 0), ""))
        return gig is None or (gig.status == "open" and len(gig.legs) == 1 and not self.books.offers_open[gig.id])

    def pair_plan(self, x: dict, y: dict) -> Optional[tuple[int, int]]:
        """When one driver can take x and then y with both on time: the road minutes that the pair
        adds (to the second car, and back to the start), and the last minute to collect the first car."""
        X, Y = x["legs"][0], y["legs"][0]
        xp, xd, yp, yd = X["pickup"]["placeId"], X["delivery"]["placeId"], Y["pickup"]["placeId"], Y["delivery"]["placeId"]
        hop, back = self.minutes[(xd, yp)], self.minutes[(yd, xp)]
        if hop > self.set["pair_hop"] or back > self.set["pair_back"]:
            return None
        if self.minutes[(xp, xd)] + hop + self.minutes[(yp, yd)] > 12 * HOUR - 20:  # a gig with more than one car may plan 12 hours of driving
            return None
        there = self.minutes[(xp, xd)] + 40 * self.charging(X) + hop  # from the first pickup to the second
        until = min(self.stage(x)[1], self.stage(y)[1] - there)
        start = max(self.now + 90, X["pickup"]["window"]["from"], Y["pickup"]["window"]["from"] - there - self.set["pair_wait"])
        if until - start < 2 * HOUR or self.on_ladder(until):
            return None
        return hop + back, until

    def pair_up(self) -> set[str]:
        """Puts waiting orders in pairs, the pair with the least extra driving first. Returns the orders it paired."""
        orders = [order for order in self.books.orders.values() if self.can_pair(order)]
        plans = []
        for i, a in enumerate(orders):
            for b in orders[i + 1:]:
                for x, y in ((a, b), (b, a)):
                    plan = self.pair_plan(x, y)
                    if plan:
                        plans.append((plan[0], x["id"], y["id"], plan[1]))
        paired: set[str] = set()
        for _, x_id, y_id, until in sorted(plans):
            if x_id in paired or y_id in paired:
                continue
            paired.update((x_id, y_id))
            x, y = self.books.orders[x_id], self.books.orders[y_id]
            for order_id in (x_id, y_id):  # an order that waits alone in the app leaves it first
                gig_id = self.books.carrier.get((order_id, 0))
                if gig_id:
                    self.send({"type": "withdraw", "gigId": gig_id})
                    self.books.withdrawn(gig_id)
            facts = [self.facts.get(order_id) or notes.Facts() for order_id in (x_id, y_id)]
            reference = self.reference_of([(x_id, 0), (y_id, 0)])
            opening, early = self.intro(1.0, until, self.set["pair_intro"])
            action = {"type": "post", "stops": self.stops(x, [0], facts[0]) + self.stops(y, [0], facts[1]),
                      "audience": {"experienced": False, "manualLicence": facts[0].manual or facts[1].manual},
                      "schedule": schedule(self.now, reference, opening, until - self.set["reach"], self.set["ladder"], self.set["pair_rise"], single=self.level == 1, early=early)}
            self.send(action, at=self.now, order=x_id, stage=0, until=until, pair=[x_id, y_id])
            self.tally["pairs"] += 1
        return paired

    def post_free_cars(self) -> None:
        paired = self.pair_up() if self.set["pairs"] and self.level >= 3 else set()
        for order in list(self.books.orders.values()):
            if self.hold.get(order["id"], 0) > self.now or order["id"] in paired or self.waits_for_partner(order):
                continue
            legs = self.books.free_legs(order)
            if len(legs) == 2 and self.level >= 3 and self.drive(order, legs) <= 12 * HOUR:  # a trade-in: the old car's pickup right after the new car's delivery
                self.post(order, legs)
            else:
                for leg in legs:
                    self.post(order, [leg])

    def waits_for_partner(self, order: dict) -> bool:
        """A new car that could go in a pair, in the minutes that it stays off the app."""
        minutes, room = self.set["pair_hold"]
        if not minutes or not self.set["pairs"] or self.level < 3 or order["id"] in self.books.first_posted:
            return False
        if self.now >= self.won_at.get(order["id"], -DAY) + minutes or self.now >= LAST_REQUEST or self.now % DAY >= 18 * HOUR:
            return False  # it has waited, or no request arrives any more today
        ladder = max(step for step, _ in self.set["ladder"])
        return self.can_pair(order) and awake_between(self.now, self.stage(order)[1] - self.set["reach"]) - ladder >= room * 60

    def post(self, order: dict, legs: list[int]) -> None:
        request, facts = self.books.requests[order["id"]], self.facts.get(order["id"], notes.Facts())
        reasons = {reason for leg in legs for reason, _, _ in self.books.failed.get((order["id"], leg), [])}
        facts = facts if 0 in legs else notes.Facts()  # a note is about the request's first car
        audience = {"experienced": any(order["legs"][leg]["car"]["premium"] for leg in legs),  # a premium car needs an experienced driver: the fine is €150
                    "manualLicence": facts.manual or "licence" in reasons}
        stage, until = self.stage(order)
        reference = self.reference_of([(order["id"], leg) for leg in legs])
        action = {"type": "post", "stops": self.stops(order, legs, facts, until if stage == 0 else None), "audience": audience, "schedule": self.fees(order, reference, stage, until)}
        self.send(action, at=self.now, order=order["id"], stage=stage, until=until)

    def stops(self, order: dict, legs: list[int], facts: notes.Facts, stage_until: Optional[int] = None) -> list[dict]:
        """A pickup and a delivery for each car. A stop has its own window only when the note or an
        earlier failed visit makes it narrower than the order's window."""
        stops = []
        for leg in legs:
            spec = self.real(order["legs"][leg], facts) if leg == 0 else order["legs"][leg]
            pickup = spec["pickup"]
            fails = self.books.failed.get((order["id"], leg), [])
            not_there = [at for reason, at, _ in fails if reason in ("not_ready", "closed")]
            start = max([pickup["window"]["from"], facts.ready_at or 0] + [at + 2 * HOUR for at in not_there])  # the car was not there: try two hours on
            first = {"orderId": order["id"], "leg": leg, "kind": "pickup", "withPlates": facts.plates or any(reason == "no_plates" for reason, _, _ in fails),
                     "withCharging": self.charging(spec)}
            second = {"orderId": order["id"], "leg": leg, "kind": "delivery"}
            windows = self.day_windows(order, spec, facts, max(start, self.now)) if leg == 0 and self.noted(facts) and not pickup["privateAddress"] else None
            if windows:
                first["window"], second["window"] = windows
            elif start > pickup["window"]["from"]:
                first["window"] = {"from": start, "to": max(start, pickup["window"]["to"])}
            slack = max(self.set["slack"][0], self.set["slack"][1] * self.minutes[(pickup["placeId"], spec["delivery"]["placeId"])])
            if slack and "window" not in first and "window" not in second and len(order["legs"]) == 1 and not pickup["privateAddress"] and stage_until is not None:
                # The world lets a driver plan the pickup for the last minute. Real drives run longer than the map's, and a car that
                # arrives after the site has closed counts the next morning.
                end = int(stage_until - slack)
                if end - max(start, self.now) >= 45:
                    first["window"] = {"from": start, "to": end}
            if len(legs) > 1 and leg == legs[0] and spec["delivery"]["privateAddress"]:
                # In a trade-in gig the world lets a driver bring the new car after the customer's booked hour. This window does not.
                second["window"] = {"from": spec["delivery"]["window"]["from"], "to": spec["delivery"]["window"]["to"] + 25}
            stops += [first, second]
        # A window that has ended makes the world refuse the gig. Without it, the stop runs to the end of the world.
        return [{k: v for k, v in stop.items() if k != "window"} if "window" in stop and (order["id"] in self.bare or stop["window"]["to"] <= self.now) else stop
                for stop in stops]

    @staticmethod
    def noted(facts: Optional[notes.Facts]) -> bool:
        """The note gives hours or a deadline of its own, which the world does not plan by."""
        return facts is not None and any(value is not None for value in (facts.pickup_opens, facts.pickup_closes, facts.delivery_opens, facts.delivery_closes, facts.deliver_by))

    @staticmethod
    def real(leg: dict, facts: notes.Facts) -> dict:
        """The leg with the opening hours that the note gives, where it gives them."""
        if not Desk.noted(facts):
            return leg
        return {**leg, "pickup": {**leg["pickup"], "hours": cut(leg["pickup"]["hours"], facts.pickup_opens, facts.pickup_closes)},
                "delivery": {**leg["delivery"], "hours": cut(leg["delivery"]["hours"], facts.delivery_opens, facts.delivery_closes)}}

    def day_windows(self, order: dict, leg: dict, facts: notes.Facts, earliest: int) -> Optional[tuple[dict, dict]]:
        """A stop's window is one stretch of time, and opening hours hold every day. So a gig for a
        car with hours from its note covers one day: the first on which a driver can still collect
        and deliver the car inside the real hours. When that day ends without a driver, the gig
        expires, and the next one covers the next day."""
        pickup, delivery = leg["pickup"], leg["delivery"]
        drive = self.minutes[(pickup["placeId"], delivery["placeId"])] + 40 * self.charging(leg)
        due = min(order["deadline"], facts.deliver_by or order["deadline"])
        cap = due if due > self.now + drive else self.ends_at  # a car that is late already has no deadline left to meet
        for day in range(earliest // DAY, earliest // DAY + 8):
            span = open_span(pickup["hours"], day)
            if span is None:
                continue
            start = max(span[0], earliest)
            first_arrival = max(start + drive, delivery["window"]["from"])
            arrive_by = last_open(delivery["hours"], min(cap, (day + 1) * DAY - 1))  # delivered on the same day
            if arrive_by < first_arrival:  # a long drive, or a later booked hour: delivered on a later day
                arrive_by = last_open(delivery["hours"], cap)
            end = min(span[1] - 1, arrive_by - drive)
            if arrive_by >= first_arrival and end - start >= (90 if day == self.now // DAY else 30):
                return {"from": start, "to": end}, {"from": delivery["window"]["from"], "to": arrive_by}
        return None

    def charging(self, leg: dict) -> bool:
        """An electric car below 30% charge on a route over 200 km needs a charging stop."""
        car = leg["car"]
        return bool(car["electric"] and car["chargePercent"] is not None and car["chargePercent"] < 30
                    and self.km[(leg["pickup"]["placeId"], leg["delivery"]["placeId"])] > 200)

    def drive(self, order: dict, legs: list[int]) -> int:
        """The road minutes of a gig with these cars of the order, the drives between them included."""
        total, at = 0, None
        for leg in legs:
            pickup, delivery = order["legs"][leg]["pickup"]["placeId"], order["legs"][leg]["delivery"]["placeId"]
            total += (self.minutes[(at, pickup)] if at else 0) + self.minutes[(pickup, delivery)]
            at = delivery
        return total

    def last_pickup(self, order: dict, deadline: int) -> int:
        """Our estimate of the last minute to collect the order's first undelivered car and still deliver by `deadline`."""
        legs = [leg for leg, at in enumerate(order["deliveredAt"]) if at is None] or [0]
        first, last = order["legs"][legs[0]], order["legs"][legs[-1]]
        charging = 40 * sum(1 for leg in legs if self.charging(order["legs"][leg]))
        leave = last_open(last["delivery"]["hours"], deadline) - self.drive(order, legs) - charging
        if len(legs) > 1 and first["delivery"]["privateAddress"]:  # a trade-in's new car is due half an hour after the customer's booked hour
            leave = min(leave, first["delivery"]["window"]["to"] + 30 - self.minutes[(first["pickup"]["placeId"], first["delivery"]["placeId"])] - 40 * self.charging(first))
        if first["pickup"]["privateAddress"]:
            return min(leave, first["pickup"]["window"]["to"])
        return last_open(first["pickup"]["hours"], leave)

    def stage(self, order: dict) -> tuple[int, int]:
        """Where the order stands, and the last pickup minute of that stage. Stage 0: it can still be
        on time. Then each later refund step: one business day late, two, and the end of the world."""
        deadline, facts = order["deadline"], self.facts.get(order["id"]) or notes.Facts()
        later = [business_days_after(deadline // DAY, days) * DAY + deadline % DAY for days in (1, 2)] + [self.ends_at]
        untils = [order["lastPickupAt"]]
        if self.noted(facts):  # the world's last pickup minute follows the stated hours and deadline: ours follows the note
            order = {**order, "legs": [self.real(order["legs"][0], facts)] + order["legs"][1:]}
            untils = [min(order["lastPickupAt"], self.last_pickup(order, min(deadline, facts.deliver_by or deadline)))]
        untils += [self.last_pickup(order, minute) for minute in later]
        for stage, until in enumerate(untils):
            if until > self.now:
                return stage, until
        return len(untils) - 1, untils[-1]

    def fees(self, order: dict, reference: float, stage: int, until: int) -> list[dict]:
        new = order["id"] not in self.books.first_posted
        if stage == 0:
            opening, ladder, rise = self.opening(order), self.set["ladder"], self.set["rise"]
        else:
            opening, ladder, rise = self.set["late_opening"], self.set["late_ladder"], []
        early = [(until // DAY * DAY + minute, ratio) for minute, ratio in self.set["short_day_steps"]] if stage == 0 and until // DAY in self.short_days else []
        if stage == 0 and new and not early:
            opening, early = self.intro(opening, until, self.set["intro"])
        return schedule(self.now, reference, opening, until - self.set["reach"], ladder, rise, single=self.level == 1, early=early)

    def intro(self, fee: float, until: int, intro: list) -> tuple[float, list]:
        """The opening discount: the fee to show now, and the step back to the gig's fee. No discount when the ladder is near."""
        minutes, ratio = intro
        back = awake_after(self.now, minutes)
        ladder_from = awake_before(until - self.set["reach"], max(m for m, _ in self.set["ladder"]))
        if not minutes or ratio >= 1 or self.level == 1 or back >= ladder_from:
            return fee, []
        return fee * ratio, [(back, fee)]

    def watch_backlog(self) -> None:
        """In the morning, many cars that still wait for a driver say that drivers are few today, whatever the reason."""
        day = self.now // DAY
        if not self.set["backlog_alarm"] or day % 7 > 4 or self.now % DAY < 6 * HOUR or day in self.mornings:
            return
        self.mornings.add(day)
        waiting = len(self.books.waiting())
        if waiting >= self.set["backlog_alarm"] and day not in self.short_days:
            self.short_days.add(day)
            print(f"{clock(self.now)} {waiting} cars wait for a driver this morning: a day with few drivers")

    def raise_for_short_day(self) -> None:
        """On a day when drivers stay at home, the cars that are due that day and have no driver get
        their high fees in the morning: by the afternoon, nobody is left to take them at any fee."""
        today = self.now // DAY
        if today not in self.short_days:
            return
        for gig in self.books.gigs.values():
            order = self.books.orders.get(gig.legs[0][0]) if gig.legs else None
            if gig.status != "open" or gig.stage != 0 or gig.until // DAY != today or gig.id in self.raised or order is None:
                continue
            self.raised.add(gig.id)
            reference = self.reference_of(gig.legs)
            shown = max(step["feeCents"] for step in gig.post["schedule"] if step["at"] <= self.now) / reference  # never below the fee in the app now
            early = [(today * DAY + minute, ratio) for minute, ratio in self.set["short_day_steps"]]
            gig.post = {**gig.post, "schedule": schedule(self.now, reference, shown, gig.until - self.set["reach"], self.set["ladder"], single=self.level == 1, early=early)}
            self.send({"type": "reprice", "gigId": gig.id, "schedule": gig.post["schedule"]})

    def opening(self, order: dict) -> float:
        """The opening fee over the typical fee: the one behind our price, or a new plan for a car that we post again."""
        if self.set["explore"]:
            return random.Random(f"{self.set['seed']}:fee:{order['id']}").choice(self.set["explore_fees"])
        plan = self.plans.get(order["id"], {}).get(order["option"]) if order["id"] not in self.books.first_posted else None
        if plan is None:
            legs = [leg for leg, at in enumerate(order["deliveredAt"]) if at is None] or [0]
            request = self.books.requests[order["id"]]
            plan = self.best_fee(order["legs"][legs[0]], request["referenceFeeCents"], self.now, order["lastPickupAt"], self.late_cost(order["dealerId"], order["priceCents"]))
        return plan.fee if plan else self.set["fees"][-1]

    def bump_dropped(self) -> None:
        """A driver who gave a gig back takes it again only for more, and the gig notifies drivers again: it
        comes back at the booked fee times a bump, so that the next driver comes soon."""
        dropped, self.dropped = self.dropped, set()
        for gig_id in dropped:
            gig = self.books.gigs.get(gig_id)
            if gig is None or gig.status != "open" or gig.stage != 0 or len({order_id for order_id, _ in gig.legs}) != 1:
                continue
            reference = self.reference_of(gig.legs)
            shown = max(step["feeCents"] for step in gig.post["schedule"] if step["at"] <= self.now)
            opening = max(shown, gig.fee * self.set["drop_bump"]) / reference
            gig.post = {**gig.post, "schedule": schedule(self.now, reference, opening, gig.until - self.set["reach"], self.set["ladder"], single=self.level == 1)}
            self.send({"type": "reprice", "gigId": gig.id, "schedule": gig.post["schedule"]})

    def review_open_gigs(self) -> None:
        """A gig that no driver took in its stage moves to the next: the car will be later, and the fee starts again."""
        if self.dropped:
            self.bump_dropped()
        for gig in list(self.books.gigs.values()):
            if gig.status != "open":
                continue
            together = {order_id for order_id, _ in gig.legs}
            if len(together) > 1:  # a pair that found no driver before its fee would climb: each car goes alone, with its own last pickup
                if self.on_ladder(gig.until) or gig.until // DAY in self.short_days:
                    self.send({"type": "withdraw", "gigId": gig.id})
                    self.books.withdrawn(gig.id)
                    self.alone.update(together)
                    self.tally["pairs split"] += 1
                continue
            if self.now <= gig.until:
                continue
            order = self.books.orders.get(gig.legs[0][0])
            if order is None:
                continue
            stage, until = self.stage(order)
            if (stage, until) == (gig.stage, gig.until):
                continue
            reference = self.reference_of(gig.legs)
            gig.post = {**gig.post, "schedule": self.fees(order, reference, stage, until)}
            self.send({"type": "reprice", "gigId": gig.id, "schedule": gig.post["schedule"]})
            gig.stage, gig.until = stage, until

    def offer_to_viewers(self) -> None:
        """A gig that has waited in the app goes, as a direct offer at the fee in the app, to the drivers who looked at it
        and live near its delivery: the nearest first, three at a time, each driver once for an order. A viewer who lives
        within 30 km of the delivery books one gig in eight that they look at; other viewers, one in forty."""
        minutes, ratio, km = self.set["viewer_offers"]
        if not AWAKE[0] <= self.now % DAY < AWAKE[1] - 15:  # no driver reads an offer at night
            return
        sent, day = 0, self.now // DAY
        for gig in sorted(self.books.gigs.values(), key=lambda gig: gig.until):  # the most urgent gig first
            order = self.books.orders.get(gig.legs[0][0]) if gig.legs else None
            room = 3 - len(self.books.offers_open[gig.id])
            if gig.status != "open" or order is None or room <= 0 or self.now - gig.posted_at < minutes or gig.until < self.now + 30 or sent >= 30:
                continue
            audience = gig.post["audience"]
            last = self.books.orders[gig.legs[-1][0]]["legs"][gig.legs[-1][1]]
            delivery = last["delivery"]["placeId"]
            near = []
            for driver in {driver for order_id, _ in gig.legs for driver in self.looked.get(order_id, ())} - self.tried[order["id"]]:
                profile = self.drivers.get(driver)
                if (profile is None or self.books.offers_sent[(driver, day)] >= 3 or (audience["manualLicence"] and profile["licence"] != "manual")
                        or (audience["experienced"] and not (profile["rating"] >= 4.8 and profile["completedGigs"] >= 50))):
                    continue
                away = self.air[(profile["homePlaceId"], delivery)]
                if away <= km:
                    near.append((away, driver))
            reference = self.reference_of(gig.legs)
            shown = max(step["feeCents"] for step in gig.post["schedule"] if step["at"] <= self.now)  # the fee in the app now
            for away, driver in sorted(near)[:room]:
                if self.set["explore_viewer_offers"]:
                    ratio = random.Random(f"{self.set['seed']}:viewer:{gig.id}:{driver}").choice(self.set["explore_viewer_offers"])
                fee = int(shown * ratio + 0.5)
                self.send({"type": "offer", "gigId": gig.id, "driverId": driver, "feeCents": fee})
                self.books.offers_sent[(driver, day)] += 1
                self.books.offers_open[gig.id].add(driver)
                self.tried[order["id"]].add(driver)
                sent += 1
                self.tally["offers to viewers"] += 1
                print(f"offer: {json.dumps({'at': self.now, 'gig': gig.id, 'driver': driver, 'fee': fee, 'shown': round(shown / reference, 3), 'ratio': ratio, 'km': round(away), 'cars': len(gig.legs), 'open': self.now - gig.posted_at, 'viewed': self.now - max(self.looked[o].get(driver, -1) for o, _ in gig.legs), 'left': gig.until - self.now, 'stage': gig.stage})}")

    def offer_to_free_drivers(self) -> None:
        """A driver who has just delivered a car of ours stands far from home, and the app does not
        tell them of gigs there. A gig that starts where they stand costs them no trip to the
        pickup; one that ends near their home costs them no trip home either. So they get a direct
        offer of it, below the fee in the app."""
        for driver, (place, at) in list(self.free.items()):
            del self.free[driver]
            profile = self.drivers.get(driver)
            if profile is None or self.now - at > 30 or self.books.offers_sent[(driver, self.now // DAY)] >= 3:
                continue
            if any(gig.driver == driver for gig in self.books.gigs.values()):
                continue  # they hold another gig of ours
            best = None
            for gig in self.books.gigs.values():
                order = self.books.orders.get(gig.legs[0][0]) if gig.legs else None
                if gig.status != "open" or len(gig.legs) != 1 or order is None or len(self.books.offers_open[gig.id]) >= 3:
                    continue
                leg, audience = order["legs"][gig.legs[0][1]], gig.post["audience"]
                window = next((stop.get("window") for stop in gig.post["stops"] if stop["kind"] == "pickup"), None) or leg["pickup"]["window"]
                if (self.air[(place, leg["pickup"]["placeId"])] > self.set["offer_km"] or window["from"] > self.now + 2 * HOUR or gig.until < self.now + 30
                        or (audience["manualLicence"] and profile["licence"] != "manual")
                        or (audience["experienced"] and not (profile["rating"] >= 4.8 and profile["completedGigs"] >= 50))):
                    continue
                home = self.air[(profile["homePlaceId"], leg["delivery"]["placeId"])] <= HOME_KM
                if best is None or (home, -gig.until) > (best[0], -best[1].until):
                    best = (home, gig, order)
            if best is None:
                continue
            home, gig, order = best
            reference = self.reference_of(gig.legs)
            shown = max(step["feeCents"] for step in gig.post["schedule"] if step["at"] <= self.now)  # the fee in the app now
            if self.set["explore_offers"]:
                ratio = random.Random(f"{self.set['seed']}:offer:{gig.id}:{driver}").choice(self.set["explore_offers"])
            else:
                ratio = self.set["offer_fee_home"] if home else self.set["offer_fee"]
            ladder = max(minutes for minutes, _ in self.set["ladder"])
            urgent = awake_between(self.now, gig.until - self.set["reach"]) <= ladder  # near its last pickup: the fee in the app, to a driver who is there
            fee = shown if urgent and not self.set["explore_offers"] else min(shown, int(reference * ratio + 0.5))
            self.send({"type": "offer", "gigId": gig.id, "driverId": driver, "feeCents": fee})
            self.books.offers_sent[(driver, self.now // DAY)] += 1
            self.books.offers_open[gig.id].add(driver)
            print(f"offer: {json.dumps({'at': self.now, 'gig': gig.id, 'driver': driver, 'fee': fee, 'ratio': round(fee / reference, 3), 'shown': round(shown / reference, 3), 'home': home, 'urgent': urgent, 'km': round(self.air[(place, order['legs'][gig.legs[0][1]]['pickup']['placeId'])]), 'minutes': self.minutes[(order['legs'][gig.legs[0][1]]['pickup']['placeId'], order['legs'][gig.legs[0][1]]['delivery']['placeId'])], 'since': self.now - at})}")

    def replan(self) -> None:
        """After a change of plan, the order's open gigs leave the app, and its cars are posted again with the new windows."""
        changed, self.changed = self.changed, set()
        for order_id in changed:
            self.bare.discard(order_id)
            self.hold.pop(order_id, None)
        for gig in [gig for gig in self.books.gigs.values() if gig.status == "open" and any(key[0] in changed for key in gig.legs)]:
            self.send({"type": "withdraw", "gigId": gig.id})
            self.books.withdrawn(gig.id)


def euros(cents: float) -> int:
    """A price in whole euros, as cents."""
    return int(cents / 100 + 0.5) * 100


def narrower(stop: dict, window: dict, base: dict) -> dict:
    return {**stop, "window": window} if window["from"] > base["from"] or window["to"] < base["to"] else stop


def schedule(now: int, reference: float, opening: float, book_by: int, ladder: list, rise: list = (), single: bool = False, early: list = ()) -> list[dict]:
    """A fee schedule in three parts. The opening fee now. Early raises over the opening fee, each
    after a share of the awake time before the ladder. Then the ladder: fees over the typical fee,
    each a number of awake minutes before the minute by which a driver must have booked. A ladder
    step that is already due raises the opening fee. `single` gives one step, for level 1."""
    fee, steps = opening, {}
    ladder_from = awake_before(book_by, max(minutes for minutes, _ in ladder)) if ladder else book_by
    for at, ratio in [(awake_before(book_by, minutes), ratio) for minutes, ratio in sorted(ladder, reverse=True)] + sorted(early):  # `early`: steps at fixed minutes
        if at <= now:
            fee = max(fee, ratio)
        else:
            steps[at] = max(ratio, steps.get(at, 0))
    time = awake_between(now, ladder_from)
    for share, ratio in rise if fee == opening else ():
        at = awake_after(now, int(time * share))
        if now < at < ladder_from:
            steps[at] = max(opening * ratio, steps.get(at, 0))
    result, top = [{"at": now, "feeCents": max(1, int(reference * fee + 0.5))}], fee
    for at in sorted(steps):
        if steps[at] > top and not single:
            top = steps[at]
            result.append({"at": at, "feeCents": max(1, int(reference * top + 0.5))})
    return result
