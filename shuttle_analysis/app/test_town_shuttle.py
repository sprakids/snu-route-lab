"""Regressions for the missing admin -> Daehak-dong timetable route."""
import json,unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
import server
from shuttle_timetable import KST
from road_geometry import meters,Buildings

def at(clock,date='2026-11-09'):
    return datetime.fromisoformat(date+'T'+clock).replace(tzinfo=KST).timestamp()

class TownShuttleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=server.Application();cls.service=cls.app.transit.shuttle
        cls.day=next(r for r in cls.service.routes if r['provider_id']=='41843')
        cls.night=next(r for r in cls.service.routes if r['provider_id']=='41942')
        cls.admin=next(i for i,s in enumerate(cls.day['stops']) if s['id']=='snu-410' and s['board_allowed'])

    def setUp(self):
        clock=patch('time.time',return_value=at('12:00:00'));clock.start();self.addCleanup(clock.stop)

    def test_day_uses_current_semester_headway_at_both_terminals(self):
        for index in [0,self.admin]:
            for clock,wait in [('07:30:00',450),('08:30:00',195),('12:00:00',300),('17:00:00',300)]:
                a=self.service.timetable.arrival(self.day,index,at(clock))
                self.assertEqual(a['wait_seconds'],wait)
                self.assertIsNone(a['vehicle_id']);self.assertIsNone(a['provided_at'])
                self.assertNotIn('queue_model',a);self.assertIn('v5 유입',a['prediction_note'])

    def test_day_closing_weekend_holiday_and_semester_limits(self):
        for date,clock in [('2026-11-09','06:59:59'),('2026-11-09','19:00:01'),('2026-11-14','12:00:00'),
                           ('2026-10-15','12:00:00'),('2026-12-22','12:00:00')]:
            self.assertIsNone(self.service.timetable.arrival(self.day,self.admin,at(clock,date)))
        a=self.service.timetable.arrival(self.day,self.admin,at('18:59:00'))
        self.assertEqual(a['departure_at'],at('19:00:00'))
        self.assertEqual(a['last_scheduled_departure_at'],at('19:00:00'))

    def test_night_exact_departure_last_bus_and_one_way(self):
        a=self.service.timetable.arrival(self.night,0,at('21:11:00'))
        self.assertEqual(a['departure_at'],at('21:40:00'));self.assertTrue(a['fixed_departure'])
        self.assertEqual(self.service.timetable.arrival(self.night,0,at('23:09:00'))['departure_at'],at('23:10:00'))
        self.assertIsNone(self.service.timetable.arrival(self.night,0,at('23:10:01')))
        self.assertIsNone(self.service.timetable.arrival(self.night,1,at('21:11:00')))
        self.assertEqual(self.service.timetable.arrival(self.night,0,at('19:30:00'))['departure_at'],at('21:10:00'))

    def test_distinct_official_day_night_stops_and_road_time_evidence(self):
        self.assertEqual(self.day['stops'][0]['id'],'snu-2501')
        self.assertEqual(self.night['stops'][1]['id'],'snu-2500')
        self.assertGreater(meters([self.day['stops'][0]['lat'],self.day['stops'][0]['lon']],
                                 [self.night['stops'][1]['lat'],self.night['stops'][1]['lon']]),100)
        for r,i,j in [(self.day,self.admin,self.admin+1),(self.night,0,1)]:
            road=self.app.transit.geometry.leg(r,i,j)
            self.assertGreater(len(road['geometry']),20)
            self.assertTrue(1500<road['meters']<2600)
            travel=self.app.planner.travel.estimate(r,i,j,at('12:00:00'))
            self.assertTrue(travel['available']);self.assertFalse(travel['validated'])
            self.assertEqual(travel['source'],'v12_segment_clock')
            self.assertGreater(travel['seconds'],road['meters']/(65/3.6))

    def test_saved_completed_trip_time_overrides_unvalidated_road_prior(self):
        r=self.day;i=self.admin;j=i+1;key=f"{r['id']}:{r['stops'][i]['seq']}:{r['stops'][j]['seq']}"
        obs={'travel_history':{key:{'n':7,'days':2,'median_seconds':422,'p10_seconds':390,'p90_seconds':480}}}
        result=self.app.planner.travel.estimate(r,i,j,at('12:00:00'),obs)
        self.assertEqual(result['source'],'measured_history');self.assertEqual(result['seconds'],422)

    def test_new_bus_paths_do_not_cut_through_mapped_buildings(self):
        blocks=Buildings(json.loads((Path(__file__).parent/'data/building_access.json').read_text(encoding='utf-8')))
        for route in (self.day,self.night):
            for part in self.app.transit.geometry.routes[route['id']]['segments']:
                self.assertFalse(any(blocks.blocked(a,b) for a,b in zip(part['geometry'],part['geometry'][1:])))

    def test_forecast_keeps_new_route_closing_and_night_fixed_clock(self):
        t=self.app.transit
        for r,index,clock,last in [(self.day,self.admin,'18:58:00','19:00:00'),(self.night,0,'21:11:00','23:10:00')]:
            a=t.forecast_service(r,index,at(clock),[],False)
            self.assertEqual(a['arrival_forecast']['last_service_at'],at(last))
            self.assertFalse(a['arrival_forecast']['vehicle_confirmed'])
        a=t.forecast_service(self.night,0,at('21:11:00'),[],False)
        self.assertEqual(a['arrival_forecast']['future_departures_at'],[at(s) for s in ['21:40:00','22:10:00','22:40:00','23:10:00']])

    def test_day_and_night_plans_include_direct_shuttle_and_real_last_walk(self):
        for clock,rid,alight in [('12:15:00','shuttle-41843','대학동 셔틀정류소'),('21:11:00','shuttle-41942','대학동 셔틀하차장')]:
            with patch('urllib.request.urlopen',side_effect=AssertionError('Specified time must not query live data')):
                result=self.app.plan({'origin_id':'snu-410','destination_id':'daehak-town','departure_at':at(clock),
                                      'mode':'estimate','include_shuttle':True})
            candidates=[c for c in result['candidates'] if len(c['route_names'])==1 and any(l.get('route_id')==rid for l in c['legs'])]
            self.assertTrue(candidates,clock);c=min(candidates,key=lambda c:c['total_seconds'])
            self.assertEqual(c['transfers'],0)
            ride=next(l for l in c['legs'] if l['type']=='bus')
            self.assertEqual(ride['to_name'],alight);self.assertIsNone(ride['vehicle_id'])
            self.assertEqual(ride['arrival_source'],'shuttle_auto_queue_estimate')
            self.assertIsNone(ride['crowd_cost']);self.assertEqual(ride['crowd_source'],'shuttle_simulation_estimate')
            self.assertTrue(ride['automatic_queue']['model_only'])
            self.assertTrue(c['legs'][-1]['type']=='walk' and c['legs'][-1]['meters']>50)
            self.assertAlmostEqual(c['total_seconds'],sum(l['seconds'] for l in c['legs']),delta=1)

    def test_new_parked_vehicle_never_gets_fabricated_departure(self):
        line=self.service.lines['41843'];now=at('12:00:00')
        from shuttle_live import locate
        line.state={'captured_at':now,'vehicles':[{'id':'parked','captured_at':now,'position':locate(157,393,line.route['anchors'])}],'error':None}
        with patch('shuttle_live.time.time',return_value=now):
            self.assertEqual(line.arrivals(self.day['stops'][self.admin],now+20),[])
            a=self.service.ready_arrivals(self.day,self.admin,now+20)[0]
        self.assertIsNone(a['vehicle_id']);self.assertEqual(a['wait_seconds'],300)

    def test_approaching_night_bus_cannot_depart_before_fixed_terminal_time(self):
        line=self.service.lines['41942'];ready=at('21:11:00')
        incoming={'arrival_source':'live_shuttle','departure_at':at('21:20:00'),'earliest_departure_at':at('21:18:00'),'vehicle_id':'incoming'}
        with patch.object(line,'arrivals',return_value=[incoming]):
            a=self.service.ready_arrivals(self.night,0,ready)[0]
        self.assertEqual(a['departure_at'],at('21:40:00'))
        self.assertIsNone(a['vehicle_id']);self.assertEqual(a['arrival_source'],'shuttle_timetable_estimate')

if __name__=='__main__':unittest.main()
