"""Summer-tyre pickups only use an explicit window clear of known snow at both ends."""
import unittest

from desk import notes
from desk.clock import DAY
from desk.desk import Desk


class SummerPickupTest(unittest.TestCase):
    def setUp(self):
        self.world_map = {"places": [{"id":k, "lat":60, "lon":25} for k in ("A","B")],
                          "roads": [{"from":a,"to":b,"minutes":60*int(a!=b),"km":60*int(a!=b)} for a in ("A","B") for b in ("A","B")]}
        self.desk = Desk(8, {"clear_summer_pickups":True}, self.world_map, [], 480, 9*DAY)
        def site(k):
            return {"placeId":k, "hours":None, "privateAddress":False, "window":{"from":480,"to":6*DAY}}
        self.leg = {"pickup":site("A"),"delivery":site("B"),"car":{"premium":False,"electric":False,"chargePercent":None}}
        self.request = {"id":"X","legs":[self.leg],"dealerId":"D","referenceFeeCents":4500,"respondBy":500,"arrivedAt":485,
                        "options":[{"kind":"same_day","deadline":1100,"listPriceCents":15000}],
                        "note":{"language":"en","text":"Car still on summer tyres."}}
        self.facts = notes.Facts(summer_tyres=True)
        self.order = {"id":"X","legs":[self.leg],"deliveredAt":[None],"deadline":1100,"lastPickupAt":1040,
                      "dealerId":"D","priceCents":15000,"option":"same_day","status":"waiting"}
        self.desk.books.requests["X"]=self.request
        self.desk.facts["X"]=self.facts

    def test_quotes_only_ordinary_cars_and_fully_clear_options(self):
        d=self.desk
        self.assertTrue(d.summer_car(self.request,self.facts))
        self.assertFalse(d.summer_car(self.request,notes.Facts(summer_tyres=True,plates=True)))
        self.leg["pickup"]["privateAddress"]=True
        self.assertFalse(d.summer_car(self.request,self.facts))
        self.leg["pickup"]["privateAddress"]=False
        d.best_fee=lambda *args: args[3]
        opt=self.request["options"][0]
        self.assertEqual(d.plan(self.request,opt,500),1040)
        self.assertIsNone(d.plan(self.request,{**opt,"deadline":3*DAY},500))
        for town in ("A","B"):
            d.books.snow=[{"from":800,"to":1000,"placeIds":[town]}]
            self.assertIsNone(d.plan(self.request,opt,500))

    def test_previous_storm_does_not_hide_the_next_storm(self):
        self.desk.books.snow=[{"from":100,"to":400,"placeIds":["A"]},{"from":800,"to":1000,"placeIds":["B"]}]
        self.assertEqual(self.desk.clear_pickup(self.leg,480,1100),{"from":480,"to":799})
        self.assertEqual(self.desk.clear_pickup(self.leg,800,1200),{"from":1000,"to":1200})
        self.assertIsNone(self.desk.clear_pickup(self.leg,800,990))

    def test_earliest_retry_uses_explicit_rolling_window_even_if_prior_post_was_refused(self):
        d=self.desk
        d.now=1200
        d.books.snow=[{"from":1100,"to":DAY+600,"placeIds":["B"]},{"from":2*DAY,"to":3*DAY,"placeIds":["A"]}]
        d.bare.add("X")
        d.books.failed[("X",0)].append(("not_ready",1150,"g-old"))
        d.post(self.order,[0])
        pickup=d.outbox[0]["stops"][0]
        self.assertEqual(pickup["window"],{"from":DAY+600,"to":2*DAY-1})
        self.assertFalse(d.can_pair(self.order))

    def test_rejoin_replays_forecasts_and_note_before_reposting(self):
        r={"seq":0,"at":485,"kind":"price_request","request":self.request}
        snow={"seq":1,"at":490,"kind":"forecast","from":600,"to":1000,"placeIds":["A"]}
        won={"seq":2,"at":500,"kind":"order_won","order":self.order}
        d=Desk(8,{"clear_summer_pickups":True},self.world_map,[],750,9*DAY)
        d.rejoin([r,snow,won],{"now":750,"orders":[self.order],"gigs":[],"openRequests":[]})
        self.assertTrue(d.facts["X"].summer_tyres)
        d.post(self.order,[0])
        self.assertEqual(d.outbox[0]["stops"][0]["window"],{"from":1000,"to":1040})

    def test_disabled_setting_still_declines_even_when_weather_is_clear(self):
        self.desk.set["clear_summer_pickups"]=False
        self.assertEqual(self.desk.prices(self.request,False),{"same_day":45000})
