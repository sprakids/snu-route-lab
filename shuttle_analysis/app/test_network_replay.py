import unittest
from datetime import datetime
from unittest.mock import patch

import server
from terminal_wait import RELEASE


def stamp(value):
    return datetime.fromisoformat(value+'+09:00').timestamp()


class NetworkReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=server.Application()
        cls.t=cls.app.transit
        cls.q=cls.t.automatic_queue
        cls.replay=cls.q.operations

    def test_sparse_terminal_and_continuing_passenger_use_same_release(self):
        join=stamp('2026-11-27T15:48:00')
        route=self.app.planner.by_id['shuttle-41841']
        table=self.t.shuttle.timetable
        with patch.object(self.q,'current',side_effect=AssertionError('legacy forecast')):
            q=self.q.arrival(route,1,join+20,[],table,join,{},False)[0]['automatic_queue']
            self.assertTrue(0<q['boarded_mass']<1)
            value=self.q.arrival(route,1,join+60,[],table,join+60,{},True,waiting_since=join)[0]
            self.assertGreaterEqual(value['boarding_at'],join+60)
            self.assertEqual(value['automatic_queue']['model_id'],RELEASE)
            self.assertEqual(value['automatic_queue']['join_at'],join)

    def test_weekend_buses_use_weekend_headways_and_weekday_capacity_prior(self):
        ready=stamp('2026-11-28T15:00:00')
        for route in self.t.network['routes']:
            with self.subTest(route=route['id']):
                self.assertIsNone(self.replay.passage(route,0,ready))
                base=self.t.forecast_service(route,0,ready,[],False)
                result=self.t.city_boarding(route,0,ready,base,False)
                q=result['city_wait']
                self.assertEqual(q['model_id'],RELEASE)
                self.assertTrue(q['simulation']['extrapolated'])
                self.assertGreater(q['simulation']['modeled_passages'],0)
                self.assertGreaterEqual(q['expected_boarding_at'],ready)
                self.assertIsNone(result['vehicle_id'])
        table=self.t.shuttle.timetable
        self.assertIsNone(self.q.arrival(self.app.planner.by_id['shuttle-41841'],1,ready,[],table,ready,{},False))

    def test_all_city_routes_use_matching_direction_and_replay_clock(self):
        ready=stamp('2026-12-01T15:23:00')
        for route in self.t.network['routes']:
            rid=route['id']
            sample=next((i,self.replay.passage(route,i,ready)) for i in range(len(route['stops']))
                        if self.replay.passage(route,i,ready))
            i,event=sample
            _,k=self.replay.mapping(route,i)
            stop=route['stops'][i]
            self.assertEqual(self.replay.routes[rid]['stops'][k],[stop['id'],stop['seq']])
            self.assertGreaterEqual(event['departure_at'],ready)
            self.assertEqual(event['operations']['model_id'],RELEASE)
            self.assertFalse(self.replay.profile(route,i,ready,300)['extrapolated'])
