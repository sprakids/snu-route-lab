import copy,json,math,unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
import server
from automatic_queue import simulate,queue_at
from road_geometry import Buildings

ROOT=Path(__file__).parent
IDS={'41841','41842','41843','41868','41869','41914','41946','41915','41942','41916'}
def at(value):return datetime.fromisoformat(value).replace(tzinfo=server.KST).timestamp()

class AllShuttleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=server.Application();cls.service=cls.app.transit.shuttle;cls.q=cls.app.transit.automatic_queue
    def setUp(self):
        clock=patch('time.time',return_value=at('2026-11-09T12:00:00'));clock.start();self.addCleanup(clock.stop)
    def route(self,rid):return self.app.planner.by_id['shuttle-'+rid]
    def sample(self,rid):
        clock='2026-11-10T09:00:00' if rid in ('41842','41868','41869') else '2026-11-09T23:50:00' if rid=='41916' else '2026-11-09T21:11:00' if rid in ('41915','41942') else '2026-11-09T12:15:00'
        r=self.route(rid);i=next(i for i,s in enumerate(r['stops']) if s['board_allowed'] and (s['id']=='snu-410' if rid in ('41841','41843','41915','41942') else True))
        return r,i,at(clock)

    def test_catalog_matches_all_ten_official_student_routes(self):
        self.assertEqual({r['provider_id'] for r in self.service.routes},IDS)
        raw=json.loads((ROOT/'data/shuttle_live/snu_shuttle_search.json').read_text(encoding='utf-8'))
        from shuttle_live import CATALOG
        self.assertEqual({r['official_route_id'] for r in CATALOG['routes']},{r['bus_route_id'] for r in raw['suttle_route_list']})
        self.assertFalse(CATALOG['coverage']['staff_only_in_student_recommendations'])

    def test_all_routes_have_directed_road_travel_and_no_building_chords(self):
        blocks=Buildings(json.loads((ROOT/'data/building_access.json').read_text(encoding='utf-8')))
        for r in self.service.routes:
            for i in range(len(r['stops'])-1):
                path=self.app.transit.geometry.leg(r,i,i+1);self.assertIsNotNone(path,(r['id'],i))
                self.assertTrue(self.app.planner.travel.estimate(r,i,i+1,at('2026-11-09T12:00:00'))['available'])
                self.assertFalse(any(blocks.blocked(a,b) for a,b in zip(path['geometry'],path['geometry'][1:])),(r['id'],i))

    def test_position_never_overrides_any_shuttle_terminal_clock(self):
        for rid in IDS:
            r,i,ready=self.sample(rid)
            with patch.object(self.service.lines[rid],'arrivals',side_effect=AssertionError('Schematic approach is not a departure')):
                values=self.service.ready_arrivals(r,i,ready)
            self.assertTrue(values,rid)
            self.assertIsNone(values[0]['vehicle_id']);self.assertIsNone(values[0]['provided_at'])

    def test_all_ten_use_simulated_wait_without_bus_crowd_inputs(self):
        for rid in IDS:
            r,i,ready=self.sample(rid)
            a=self.q.arrival(r,i,ready,[],self.service.timetable,ready,{},False)
            b=self.q.arrival(r,i,ready,[{'arrival_source':'live_shuttle','departure_at':ready+1,'provided_at':ready,'vehicle_id':'fake','full':True}],
                             self.service.timetable,ready,{'vehicles':[{'id':'fake','crowd_code':'6','provided_at':ready}]},True)
            self.assertTrue(a,rid);self.assertTrue(b,rid)
            self.assertEqual(a[0]['wait_seconds'],b[0]['wait_seconds']);self.assertTrue(b[0]['automatic_queue']['model_only'])
            self.assertFalse(b[0]['automatic_queue']['live_signal']['available'])
            self.assertIsNone(b[0]['vehicle_id']);self.assertIsNone(b[0]['crowd_cost'])
            self.assertGreaterEqual(b[0]['departure_at'],ready)

    def test_night_profiles_share_daytime_residual_queue_without_copying_inflow(self):
        for rid,primary in [('shuttle-41915','shuttle-41841'),('shuttle-41942','shuttle-41843')]:
            target=self.q.data['routes'][rid]
            self.assertEqual(target['profile_route_id'],primary)
            self.assertEqual(target['ready_flows'],[])
            r,i,ready=self.sample(rid.removeprefix('shuttle-'))
            a=self.q.arrival(r,i,ready,[],self.service.timetable,ready,{},False)[0]
            self.assertEqual(a['automatic_queue']['profile_route_id'],primary)
            self.assertEqual(a['next_scheduled_departure_at'],at('2026-11-09T21:40:00'))

    def test_missing_commuter_and_midnight_cohorts_are_unknown_not_zero_people(self):
        for rid in ('41842','41868','41869','41916'):
            r,i,ready=self.sample(rid);a=self.q.arrival(r,i,ready,[],self.service.timetable,ready,{},False)[0]
            q=a['automatic_queue'];self.assertFalse(q['cohort_available'])
            self.assertIsNone(q['queue_at_arrival']);self.assertIsNone(q['queue_now']);self.assertIsNone(q['expected_load_ratio'])
            self.assertGreaterEqual(q['expected_wait_seconds'],0)

    def test_commuter_cutoff_applies_at_terminal_then_downstream_road_offset(self):
        for rid in ('41842','41868','41869'):
            r=self.route(rid);t=self.service.timetable
            self.assertIsNone(t._schedule_arrival(r,0,at('2026-11-10T11:00:01')))
            j=next((k for k,s in enumerate(r['stops'][1:],1) if s['board_allowed']),None)
            if j is not None:
                a=t._schedule_arrival(r,j,at('2026-11-10T11:00:01'))
                self.assertIsNotNone(a);self.assertGreater(a['last_scheduled_departure_at'],at('2026-11-10T11:00:00'))

    def test_midnight_uses_previous_operating_day_and_current_pdf_order(self):
        r=self.route('41916');self.assertEqual([s['id'] for s in r['stops'][:3]],['snu-901','snu-1001','snu-711'])
        t=self.service.timetable
        a=t._schedule_arrival(r,0,at('2026-11-14T01:10:00'))
        self.assertEqual(a['departure_at'],at('2026-11-14T01:30:00'))  # Friday service into Saturday
        self.assertIsNone(t._schedule_arrival(r,0,at('2026-11-15T01:10:00')))
        self.assertGreater(t._schedule_arrival(r,0,at('2026-11-09T23:50:00'))['departure_at'],at('2026-11-09T23:59:59'))

    def test_only_day_or_night_station_provider_is_recommended_at_its_clock(self):
        self.assertIsNone(self.service.timetable._schedule_arrival(self.route('41841'),1,at('2026-11-09T21:11:00')))
        a=self.service.timetable._schedule_arrival(self.route('41915'),0,at('2026-11-09T21:11:00'))
        self.assertEqual(a['departure_at'],at('2026-11-09T21:40:00'))

    def test_retained_packet_mass_matches_existing_inflow_and_night_is_not_duplicated(self):
        for rid in ('shuttle-41841','shuttle-41946','shuttle-41914','shuttle-41843'):
            r=self.q.data['routes'][rid]
            for day in range(5):
                inflow=math.fsum(row[3] for row in r['ready_flows'] if row[0]==day)
                packets=math.fsum(row[3] for row in r['ready_packets'] if row[0]==day)
                self.assertAlmostEqual(inflow,packets,places=5)
                p=simulate(r,day,.5,1,.1,lambda i,t:1.,15)
                self.assertAlmostEqual(p['input_mass'],p['boarded_mass']+p['exited_mass']+p['remaining_mass'],places=6)
                self.assertLessEqual(p['max_load'],p['capacity']+1e-7)

    def test_switched_people_exit_and_packet_input_is_not_counted_twice(self):
        r={'id':'shuttle-41869','n':1,'anchor':0,'capacity':25,'offsets':[0],
           'stops':[{'board_allowed':True}],'loop':False,'od':{},'ready_flows':[[0,0,510*60,60]],'flows':[[0,0,510,60]],
           'ready_packets':[[0,0,510*60,60,511*60]]}
        p=simulate(r,0,.5,1,0,lambda i,t:1.,15)
        self.assertEqual(p['input_mass'],60);self.assertEqual(p['exited_mass'],60)
        self.assertEqual(p['boarded_mass'],0);self.assertEqual(queue_at(p,0,512*60),0)

    def test_actual_arrival_preview_exposes_model_countdown_and_fixed_departures(self):
        now=at('2026-11-09T21:11:00');t=self.app.transit
        with patch('time.time',return_value=now),patch('urllib.request.urlopen',side_effect=AssertionError('No position or crowd API for model ETA')):
            data=t.arrival_preview([{'route_id':'shuttle-41915','seq':1,'ready_at':now+20,'forecast_only':True}])
        f=data['stops'][0]['arrival_forecast'];self.assertEqual(f['time_basis'],'shuttle_schedule_model')
        self.assertFalse(f['position_used_as_departure']);self.assertEqual(f['next_scheduled_departure_at'],at('2026-11-09T21:40:00'))
        self.assertEqual(data['position_calls_triggered'],0)

    def test_external_official_origin_can_route_but_custom_geofence_is_preserved(self):
        body={'origin_id':'snu-3101','destination_id':'snu-station','departure_at':at('2026-11-10T09:00:00'),'mode':'estimate','include_shuttle':True}
        with patch('urllib.request.urlopen',side_effect=AssertionError('Specified time must not call providers')):
            result=self.app.plan(body)
        self.assertTrue(any(l.get('route_id')=='shuttle-41868' for c in result['candidates'] for l in c['legs']))
        sadang=next(p for p in self.app.origins if p['id']=='snu-3101')
        with self.assertRaises(ValueError):self.app.plan({**body,'origin_id':None,'origin':{'lat':sadang['lat'],'lon':sadang['lon'],'kind':sadang['kind']}})

    def test_extended_travel_cannot_use_a_different_geometry_version(self):
        from travel_time import TravelTime
        geometry=copy.deepcopy(self.app.transit.geometry);geometry.version='different-version'
        result=TravelTime(geometry=geometry).estimate(self.route('41842'),0,1,at('2026-11-10T09:00:00'))
        self.assertFalse(result['available'])

    def test_intermediate_moving_position_can_condition_clock_but_not_crowd(self):
        r=self.route('41946');ready=at('2026-11-09T16:00:00');i=7
        incoming={'arrival_source':'live_shuttle','departure_at':ready+180,'earliest_departure_at':ready+120,
                  'provided_at':ready,'vehicle_id':'moving','full':True,'observed_at_stop':False,'prediction_note':'fixture'}
        with patch.object(self.service.lines['41946'],'arrivals',return_value=[incoming]):values=self.service.ready_arrivals(r,i,ready)
        self.assertTrue(values[0]['clock_conditioning_verified'])
        result=self.q.arrival(r,i,ready,values,self.service.timetable,ready,{},True)
        self.assertTrue(result);q=result[0]['automatic_queue']
        self.assertTrue(q['live_arrival_conditioned']);self.assertEqual(q['clock_observed_at'],ready)
        self.assertFalse(q['crowd_observations_used']);self.assertFalse(q['live_signal']['available'])
        self.assertIsNone(result[0]['crowd_cost'])

if __name__=='__main__':unittest.main()
