import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import server
from terminal_wait import RELEASE, TerminalWait


def stamp(clock, day=1):
    return datetime.fromisoformat(f'2026-12-{day:02}T{clock}:00+09:00').timestamp()


class TerminalWaitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = server.Application()
        cls.app.walker.key = None
        cls.queue = cls.app.transit.automatic_queue
        cls.service = cls.app.transit.shuttle

    def route(self, provider):
        route = next(r for r in self.service.routes if r['provider_id'] == provider)
        index = next(i for i,s in enumerate(route['stops']) if s['id']=='snu-410' and s['board_allowed'])
        return route, index

    def test_release_and_unusable_files(self):
        self.assertEqual(self.queue.terminal_wait.info()['supported_cells'], 9995)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'feed.json'
            self.assertEqual(TerminalWait(path).status,'legacy_fallback')
            path.write_bytes(b'{}')
            self.assertEqual(TerminalWait(path).status,'legacy_fallback')
        with patch.dict('os.environ',{'SNU_TERMINAL_WAIT_ENABLED':'0'}):
            self.assertEqual(TerminalWait().status,'disabled')

    def test_queue_and_dwell_from_same_cohort(self):
        for provider, clock, day, outside, dwell in [
            ('41841','15:23',1,158,68), ('41843','15:18',1,22,383), ('41841','16:00',2,80,64)
        ]:
            with self.subTest(provider=provider,day=day):
                route,index=self.route(provider)
                join=stamp(clock,day)
                value=self.queue.arrival(route,index,join+20,[],self.service.timetable,join,{},False)[0]
                q=value['automatic_queue']
                self.assertEqual(q['model_id'],RELEASE)
                self.assertEqual(value['boarding_at'],join+outside)
                self.assertEqual(value['departure_at'],join+outside+dwell)
                self.assertEqual(value['wait_seconds'],outside+dwell-20)
                self.assertIsNone(value['vehicle_id'])
                self.assertFalse(q['observed_queue'])

    def test_fallback_and_capacity_boundaries(self):
        model=self.queue.terminal_wait
        route,index=self.route('41841')
        for clock, day in [('21:10',1),('15:23',5)]:
            t=stamp(clock,day)
            self.assertIsNone(model.arrival(route,index,t+20,[],self.service.timetable,t,True))
        t=stamp('15:23')
        self.assertIsNone(model.arrival(route,index,t+20,[{'arrival_source':'live_shuttle','provided_at':t,
                                        'clock_conditioning_verified':True,'departure_at':t+50}],
                                        self.service.timetable,t,True))
        self.assertIsNotNone(model.arrival(route,index,t+20,[{'arrival_source':'live_shuttle','provided_at':t,
                                           'observed_at_stop':True}],self.service.timetable,t,True))
        for provider,clock,vehicles in [('41841','14:59',1),('41841','15:00',2),('41841','19:00',1),('41843','15:00',1)]:
            route,index=self.route(provider)
            value=self.queue.with_vehicle_supply(route,index,{'departure_at':stamp(clock)})['vehicle_supply']
            self.assertEqual((value['capacity'],value['batch_vehicles']),(44,vehicles))
        route,index=self.route('41843')
        other=next(i for i,s in enumerate(route['stops']) if s['id']!='snu-410' and s['board_allowed'])
        self.assertIsNone(model.node_at(route,other,t))
        self.assertIsNone(model.arrival(route,index,stamp('07:02')+20,[],self.service.timetable,t,False))

    def test_walk_then_lookup_and_time_conservation(self):
        t=stamp('15:23')
        with patch('time.time',return_value=t-3600), patch.object(self.app.transit,'shared',None):
            plan=self.app.plan({'origin_id':'campus-11C0600','destination_id':'snu-station','departure_at':t,'mode':'estimate'})
        c, bus = next((c,b) for c in plan['candidates'] for b in c['legs'] if b.get('route_id')=='shuttle-41841'
                      and b.get('automatic_queue',{}).get('model_id')==RELEASE and c['legs'][0]['seconds']>60)
        q=bus['automatic_queue']
        self.assertEqual(q['join_at'],t+c['legs'][0]['seconds'])
        self.assertNotEqual(q['join_minute'],923)
        self.assertEqual(bus['arrival_forecast']['expected_boarding_at'],bus['boarding_at'])
        self.assertEqual(bus['arrival_forecast']['expected_departure_at'],bus['departure_at'])
        self.assertFalse(bus['arrival_forecast']['rolling'])
        self.assertEqual(bus['arrival_at'],bus['departure_at']+bus['seconds'])
        self.assertEqual(c['total_seconds'],sum(c[k] for k in ('walk_seconds','wait_seconds','ride_seconds','boarding_seconds')))
        self.assertIn(RELEASE,plan['prediction_model']['applied_shuttle_wait_models'])
