import json,time,unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
import server
from shuttle_timetable import ShuttleTimetable,KST,service_day

def stamp(value):return datetime.fromisoformat(value).replace(tzinfo=KST).timestamp()

class ShuttleTimetableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=server.Application();cls.service=cls.app.transit.shuttle
        cls.model=ShuttleTimetable(cls.app.transit.geometry,use_queue=False)

    def test_admin_mean_wait_matches_prior_uniform_simulation(self):
        r=self.service.routes[0];i=next(i for i,s in enumerate(r['stops']) if s['id']=='snu-410')
        a=self.model.arrival(r,i,stamp('2026-11-09T16:00:00'))
        self.assertEqual(a['wait_seconds'],120);self.assertIsNone(a['vehicle_id'])
        self.assertEqual(a['wait_model']['kind'],'uniform_headway_simulation_mean')
        self.assertFalse(a['wait_model']['observed_queue'])

    def test_fixed_admin_night_departure_and_station_last_departure(self):
        r=next(r for r in self.service.routes if r['provider_id']=='41915');i=0
        a=self.model.arrival(r,i,stamp('2026-11-09T21:11:00'))
        self.assertEqual(a['departure_at'],stamp('2026-11-09T21:40:00'))
        self.assertIsNone(self.model.arrival(self.service.routes[0],0,stamp('2026-11-09T18:01:00')))
        self.assertIsNone(self.model.arrival(self.service.routes[0],1,stamp('2026-11-09T21:11:00')))

    def test_reverse_fixed_clock_has_a_road_offset_for_downstream_stops(self):
        r=self.service.routes[2];ready=stamp('2026-11-09T16:00:00')
        first=self.model.arrival(r,0,ready);self.assertEqual(first['departure_at'],stamp('2026-11-09T16:10:00'))
        late=self.model.arrival(r,2,stamp('2026-11-09T17:11:00'))
        self.assertIsNotNone(late);self.assertGreater(late['departure_at'],stamp('2026-11-09T17:10:00'))

    def test_weekends_holidays_and_outside_semester_create_no_scheduled_vehicles(self):
        for date in ('2026-11-07T16:00:00','2026-10-15T16:00:00','2026-12-22T16:00:00'):
            self.assertFalse(service_day(stamp(date)))
            self.assertTrue(all(self.model.arrival(r,0,stamp(date)) is None for r in self.service.routes))

    def test_verified_conditional_queue_data_adds_only_capacity_delay(self):
        r=self.service.routes[0];i=next(i for i,s in enumerate(r['stops']) if s['id']=='snu-410')
        ready=stamp('2026-11-09T12:15:20')
        a=self.service.timetable.arrival(r,i,ready);baseline=self.model.arrival(r,i,ready)
        q=a['queue_model'];self.assertFalse(q['observed_queue'])
        self.assertGreater(q['capacity_extra_seconds'],600)
        self.assertEqual(a['departure_at']-baseline['departure_at'],q['capacity_extra_seconds'])
        self.assertAlmostEqual(a['wait_seconds']+20,q['reference_mean_seconds'],delta=2)
        self.assertEqual(q['hour'],12)

    def test_upper_campus_queue_mapping_uses_each_stop_and_direction(self):
        for r in self.service.routes[1:3]:
            for sid in ('snu-901','snu-1001'):
                stop=next(s for s in r['stops'] if s['id']==sid)
                p=self.service.timetable.queue.point(r,stop,stamp('2026-11-09T12:15:00'))
                self.assertIsNotNone(p);self.assertTrue(p['node'].endswith('302' if sid=='snu-901' else '301'))

    def test_future_route_uses_history_and_timetable_without_live_provider_calls(self):
        app=self.app
        with patch('urllib.request.urlopen',side_effect=AssertionError('No live network in specified-time calculation')),patch('time.time',return_value=stamp('2026-11-09T15:00:00')):
            result=app.plan({'origin_id':'snu-410','destination_id':'snu-station','departure_at':stamp('2026-11-09T16:00:00'),
                'mode':'estimate','include_shuttle':True})
        legs=[l for c in result['candidates'] for l in c['legs'] if l.get('route_id')=='shuttle-41841']
        self.assertTrue(legs);self.assertFalse(result['live_predictions_used'])
        self.assertFalse(result['calculation_data']['latest_positions_used'])
        for leg in legs:
            self.assertEqual(leg['arrival_source'],'shuttle_auto_queue_estimate');self.assertIsNone(leg['vehicle_id'])
            self.assertTrue(leg['automatic_queue']['future_query']);self.assertFalse(leg['automatic_queue']['live_signal']['available'])
            self.assertEqual(leg['ride_model']['source'],'shuttle_simulation_road_prior')

if __name__=='__main__':unittest.main()
