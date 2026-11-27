import math
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from routing import normalize, rank_candidates, eligible_departure, WalkingGraph, finish_candidate, PRESETS
from shuttle import next_shuttle, KST
from validation import error_summary
from shuttle_live import LiveShuttle, locate
import server

def candidate(name,seconds,walk,transfers,crowd):
    return {'id':name,'total_seconds':seconds,'walk_m':walk,'transfers':transfers,'crowd_cost':crowd}

class DecisionTests(unittest.TestCase):
    def test_equal_metric_has_no_effect(self):
        self.assertEqual(normalize([7,7,7]),[0,0,0])

    def test_units_do_not_change_normalized_cost(self):
        self.assertEqual(normalize([4,8,12]),normalize([240,480,720]))

    def test_unknown_crowd_preserves_comparison_weight(self):
        values=[candidate('known',600,200,0,2),candidate('unknown',700,150,0,None)]
        r=rank_candidates(values,PRESETS['comfort'])
        self.assertGreater(r['effective_weights']['crowd'],0)
        self.assertAlmostEqual(sum(r['effective_weights'].values()),1)
        self.assertIn('comfort',r['winners'])
        self.assertIsNone(next(x for x in r['candidates'] if x['id']=='unknown')['crowd_cost'])

    def test_invalid_weights_rejected(self):
        for weights in ({'time':-1},{'time':float('nan')},{'time':0}):
            with self.assertRaises(ValueError):rank_candidates([],weights)

    def test_crowd_only_without_crowd_uses_equal_uncertainty_and_time_tiebreak(self):
        r=rank_candidates([candidate('slow',700,100,0,None),candidate('fast',500,200,0,None)],{'crowd':100})
        self.assertEqual(r['effective_weights']['crowd'],1)
        self.assertEqual(r['candidates'][0]['id'],'fast')
        self.assertTrue(all(c['score']==0 and c['crowd_cost'] is None and c['crowd_risk']==3 for c in r['candidates']))

    def test_walking_misses_first_and_catches_second(self):
        first={'departure_at':1100,'full':False}
        second={'departure_at':1400,'full':False}
        self.assertIs(eligible_departure([first,second],1150),second)

    def test_no_extrapolated_vehicle_when_all_departed(self):
        self.assertIsNone(eligible_departure([{'departure_at':1000}],1100))

    def test_full_vehicle_is_not_boardable(self):
        self.assertIsNone(eligible_departure([{'departure_at':1200,'full':True}],1100))

    def test_total_counts_every_leg_once(self):
        legs=[{'type':'walk','seconds':120,'meters':150},{'type':'board','seconds':20},
              {'type':'wait','seconds':60},{'type':'bus','seconds':600,'crowd_cost':None,'route_name':'5511','arrival_source':'live'},
              {'type':'board','seconds':20},{'type':'wait','seconds':120},
              {'type':'bus','seconds':300,'crowd_cost':0,'route_name':'5513','arrival_source':'live'},
              {'type':'walk','seconds':80,'meters':100}]
        r=finish_candidate('x',legs,1000)
        self.assertEqual(r['total_seconds'],1320)
        self.assertEqual(r['arrival_at'],2320)
        self.assertEqual(r['boarding_seconds'],40)
        self.assertEqual(r['transfers'],1)
        self.assertIsNone(r['crowd_cost'])

    def test_weekend_shuttle_not_generated(self):
        self.assertIsNone(next_shuttle(datetime(2026,11,7,17,0,tzinfo=KST).timestamp()))

    def test_official_night_departure_respects_ready_time(self):
        ready=datetime(2026,11,6,21,11,tzinfo=KST).timestamp()
        r=next_shuttle(ready)
        self.assertEqual(datetime.fromtimestamp(r['departure_at'],KST).strftime('%H:%M'),'21:40')

    def test_no_shuttle_outside_semester(self):
        self.assertIsNone(next_shuttle(datetime(2026,12,22,17,tzinfo=KST).timestamp()))

    def test_no_statistical_claim_without_observations(self):
        result=error_summary([0]*9,600)
        self.assertIsNone(result['simulated_interval_seconds'])
        self.assertIsNone(result['mae_seconds'])

    def test_empirical_simulation_uses_observed_errors(self):
        result=error_summary([60]*10,600)
        self.assertEqual(result['simulated_interval_seconds'],[660,660])
        self.assertEqual(result['mae_seconds'],60)

class WalkingTests(unittest.TestCase):
    def graph(self,ways):
        return WalkingGraph({'elements':[
            {'type':'node','id':1,'lat':37.46,'lon':126.95},
            {'type':'node','id':2,'lat':37.4605,'lon':126.95},
            {'type':'node','id':3,'lat':37.461,'lon':126.95},
            {'type':'node','id':4,'lat':37.4615,'lon':126.95}]+ways})

    def test_private_connection_does_not_become_shortcut(self):
        g=self.graph([{'type':'way','nodes':[1,2],'tags':{'highway':'footway'}},
                      {'type':'way','nodes':[2,3],'tags':{'highway':'footway','foot':'no'}},
                      {'type':'way','nodes':[3,4],'tags':{'highway':'footway'}}])
        self.assertIsNone(g.walk((37.46,126.95),(37.4615,126.95)))

    def test_pedestrian_oneway_terminal_is_not_snapped_backwards(self):
        g=self.graph([{'type':'way','nodes':[1,2,3],'tags':{'highway':'footway','oneway:foot':'yes'}}])
        self.assertIsNotNone(g.walk((37.46,126.95),(37.461,126.95)))
        self.assertIsNone(g.walk((37.461,126.95),(37.46,126.95)))

    def test_far_endpoint_is_not_straight_line_fallback(self):
        g=self.graph([{'type':'way','nodes':[1,2],'tags':{'highway':'footway'}}])
        self.assertIsNone(g.walk((37.47,126.95),(37.46,126.95)))

class LiveShuttleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.network=json.loads((Path(__file__).parent/'data/network.json').read_text(encoding='utf-8'))

    def test_schematic_has_direction_but_never_claims_gps(self):
        inward=locate(195,230);outward=locate(117,260)
        self.assertEqual(inward['direction'],'towards_admin')
        self.assertEqual(outward['direction'],'towards_station')
        self.assertNotIn('lat',inward);self.assertNotIn('lon',inward)

    def test_empty_response_does_not_create_vehicle(self):
        import io
        transit=type('FakeTransit',(),{'budget':lambda *args:True})()
        shuttle=LiveShuttle(self.network,transit)
        with patch('shuttle_live.urllib.request.urlopen',return_value=io.BytesIO(b'{"d":""}')):
            state=shuttle.refresh()
        self.assertEqual(state['vehicles'],[])
        self.assertFalse(state['stale'])

    def test_stale_observation_never_falls_back_to_timetable(self):
        transit=type('FakeTransit',(),{'budget':lambda *args:True})()
        shuttle=LiveShuttle(self.network,transit)
        shuttle.state={'captured_at':time.time()-120,'error':None,'vehicles':[]}
        self.assertEqual(shuttle.arrivals({'anchor_index':4}),[])

    def test_failed_request_is_cached_and_never_generates_vehicles(self):
        transit=type('FakeTransit',(),{'budget':lambda *args:True})()
        shuttle=LiveShuttle(self.network,transit)
        with patch('shuttle_live.urllib.request.urlopen',side_effect=OSError('offline')) as request:
            shuttle.refresh();state=shuttle.refresh()
        self.assertEqual(request.call_count,1)
        self.assertTrue(state['stale'])
        self.assertTrue(state['error'])
        self.assertEqual(state['vehicles'],[])

class KakaoAdapterTests(unittest.TestCase):
    def walker(self):
        fallback=type('Graph',(),{'walk':lambda *args:{'seconds':150,'meters':180,'source':'OSM 보행망'}})()
        transit=type('Budget',(),{'budget':lambda *args:True})()
        with patch('server.secret',return_value='test-only-key'):
            return server.KakaoWalker(fallback,transit)

    def test_kakao_contract_parses_seconds_meters_and_coordinate_order(self):
        import io
        payload={'status':'OK','route':{'properties':{'totalTime':95,'totalDistance':110},
            'legs':[{'steps':[{'path':{'points':[[126.95,37.46],[126.951,37.461]]}}]}]}}
        walker=self.walker()
        with patch('server.urllib.request.urlopen',return_value=io.BytesIO(json.dumps(payload).encode())) as request:
            result=walker.walk((37.46,126.95),(37.461,126.951))
            self.assertEqual(walker.walk((37.46,126.95),(37.461,126.951)),result)
        self.assertEqual(request.call_count,1)
        self.assertEqual(result['seconds'],round(110/(4.8/3.6)));self.assertEqual(result['provider_seconds'],95)
        self.assertEqual(result['meters'],110)
        self.assertEqual(result['geometry'][0],[37.46,126.95])
        self.assertEqual(result['source'],'카카오 도보 경로·평균4.8km/h 시간 추정')

    def test_kakao_failure_keeps_fallback_source(self):
        walker=self.walker()
        with patch('server.urllib.request.urlopen',side_effect=OSError('offline')):
            result=walker.walk((37.46,126.95),(37.461,126.951))
        self.assertEqual(result['seconds'],150)
        self.assertTrue(result['source'].startswith('OSM'))
        self.assertIn('카카오 응답 실패',result['source'])

class ApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=tempfile.TemporaryDirectory(prefix='snu-route-tests-')
        assert Path(cls.directory.name).resolve().parent==Path(tempfile.gettempdir()).resolve()
        cls.patch=patch.object(server,'RUNTIME',Path(cls.directory.name));cls.patch.start()
        cls.app=server.Application()
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.make_handler(cls.app))
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.http.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.patch.stop();cls.directory.cleanup()

    def request(self,path,body=None,headers=None):
        req=urllib.request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type':'application/json',**(headers or {})})
        with urllib.request.urlopen(req) as response:return response.status,json.load(response)

    def test_bootstrap_never_contains_server_secrets(self):
        _,data=self.request('/api/bootstrap');raw=json.dumps(data)
        if self.app.transit.key:self.assertNotIn(self.app.transit.key,raw)
        self.assertNotIn('KAKAO_REST_API_KEY',raw)
        self.assertNotIn('serviceKey',raw)

    def test_static_path_does_not_expose_backend_files(self):
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/../server.py')
        self.assertEqual(error.exception.code,404)
        error.exception.close()

    def test_cross_origin_mutation_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/refresh',{}, {'Origin':'https://example.com'})
        self.assertEqual(error.exception.code,403)
        error.exception.close()

    @patch('time.time',return_value=datetime(2026,11,9,17,tzinfo=server.KST).timestamp())
    def test_engine_has_no_reverse_stop_sequence_or_duplicate_time(self,mock_time):
        body={'origin_id':self.app.origins[0]['id'],'destination_id':'snu-station','mode':'estimate','include_shuttle':False,'preset':'fast'}
        _,result=self.request('/api/plan',body)
        self.assertGreater(result['candidate_count'],1)
        for c in result['candidates']:
            self.assertAlmostEqual(c['total_seconds'],sum(l['seconds'] for l in c['legs']),delta=1)
            for l in c['legs']:
                if l['type']=='bus':self.assertGreater(l['to_seq'],l['from_seq'])
                self.assertGreaterEqual(l['seconds'],0)

    def test_all_four_presets_both_destinations(self):
        for destination in ('snu-station','nakseongdae'):
            for preset in PRESETS:
                _,r=self.request('/api/plan',{'origin_id':self.app.origins[0]['id'],'destination_id':destination,'mode':'estimate','preset':preset})
                self.assertGreater(r['candidate_count'],0)
                self.assertTrue(all(math.isfinite(c['total_seconds']) for c in r['candidates']))

    def test_observations_and_real_statistics_are_separated(self):
        status,_=self.request('/api/observations',{'candidate':'qa-only','planned_seconds':600,'actual_minutes':11,'satisfaction':4,'seated':'unknown','is_test':True})
        self.assertEqual(status,201)
        _,r=self.request('/api/observations')
        self.assertEqual(r['records'],[])

if __name__=='__main__':unittest.main(verbosity=2)
