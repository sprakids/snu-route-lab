import io
import json
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime
from shuttle_live import LiveShuttle, ShuttleService, CATALOG, locate
from routing import WalkingGraph, Planner, PRESETS, eligible_departure
import server

class ShuttleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.network=json.loads((Path(__file__).parent/'data/network.json').read_text(encoding='utf-8'))
        cls.graph=WalkingGraph(json.loads((Path(__file__).parent/'data/walking_osm.json').read_text(encoding='utf-8')))

    def service(self):
        transit=server.Transit(self.network);transit.budget=lambda *args:True
        service=ShuttleService(self.network,transit);transit.shuttle=service
        return service,transit

    def observed(self,line,identifier,x,y):
        line.state={'captured_at':time.time(),'vehicles':[{'id':identifier,'x':x,'y':y,'captured_at':time.time(),'position':locate(x,y,line.route['anchors'])}],'error':None,'provider_timestamp':None}

    def test_five_distinct_live_route_requests_and_no_cross_route_vehicle_copy(self):
        service,_=self.service();requests=[]
        def respond(req,**kwargs):
            route=json.loads(req.data)['data'].split(',')[2];requests.append(route)
            return io.BytesIO(json.dumps({'d':'' if route=='41914' else route+'/157/40/1/test/code'}).encode())
        with patch('shuttle_live.urllib.request.urlopen',side_effect=respond):result=service.refresh()
        self.assertEqual(set(requests),{'41841','41946','41914','41843','41942','41842','41869','41868','41915','41916'})
        self.assertEqual(len(result['routes']),10)
        reverse=next(r for r in result['routes'] if r['id']=='41914')
        self.assertTrue(reverse['empty']);self.assertEqual(reverse['vehicles'],[])

    def test_unstop_landmarks_are_not_boarding_stops_and_station_sides_are_distinct(self):
        service,_=self.service();admin=service.routes[0]
        self.assertEqual([s['anchor_index'] for s in admin['stops'] if s['board_allowed']],[0,4])
        self.assertFalse(admin['stops'][2]['board_allowed'])
        self.assertNotEqual(admin['stops'][0]['id'],admin['stops'][2]['id'])
        self.assertAlmostEqual(admin['stops'][1]['lat'],37.46086)

    def test_circular_order_wrap_is_explicit_and_never_boards_a_second_cycle(self):
        service,_=self.service();route=service.routes[1];n=route['cycle_length']
        self.assertEqual(len(route['stops']),2*n)
        self.assertTrue(all(not s['board_allowed'] for s in route['stops'][n:]))
        self.assertEqual(route['stops'][0]['id'],route['stops'][n]['id'])

    def test_parked_admin_observation_has_unknown_departure_model(self):
        from datetime import datetime
        from shuttle import KST
        service,_=self.service();line=service.lines['41841'];self.observed(line,'parked',157,398)
        stop=next(s for s in service.routes[0]['stops'] if s['anchor_index']==4)
        now=datetime(2026,11,9,17,0,tzinfo=KST).timestamp()
        line.state['captured_at']=now
        with patch('shuttle_live.time.time',return_value=now):arrivals=line.arrivals(stop,now+20)
        self.assertEqual(len(arrivals),1);self.assertTrue(arrivals[0]['observed_at_stop'])
        self.assertIn('출발시각 미제공',arrivals[0]['prediction_note'])
        self.assertIsNone(arrivals[0]['vehicle_id'])
        self.assertEqual(arrivals[0]['arrival_source'],'shuttle_timetable_estimate')
        self.assertIsNotNone(eligible_departure(arrivals,now+20))
        self.assertIsNone(eligible_departure(arrivals,now+600))

    def test_stale_circle_is_excluded(self):
        service,_=self.service();line=service.lines['41946'];self.observed(line,'v',157,40)
        line.state['captured_at']=time.time()-61
        self.assertFalse(service.available(service.routes[1]));self.assertEqual(line.arrivals(service.routes[1]['stops'][7]),[])

    def test_one_route_failure_does_not_hide_other_routes(self):
        service,_=self.service()
        def response(req,**kwargs):
            route=json.loads(req.data)['data'].split(',')[2]
            if route=='41841':raise OSError('offline')
            return io.BytesIO(json.dumps({'d':route+'/157/40/1/test/code'}).encode())
        with patch('shuttle_live.urllib.request.urlopen',side_effect=response):result=service.refresh()
        self.assertIsNotNone(result['routes'][0]['error']);self.assertIsNone(result['error'])
        self.assertTrue(service.available(service.routes[1]))

    def test_cloud_instance_keeps_last_observation_on_provider_failure(self):
        service,_=self.service();line=service.lines['41946'];self.observed(line,'last-good',157,40)
        previous=line.status()
        class Shared:
            def read(self,key):return {'value':previous},'etag'
            def cached(self,key,seconds,producer):return producer()
        line.state={'captured_at':None,'vehicles':[],'error':None};line.transit.shared=Shared()
        with patch('shuttle_live.urllib.request.urlopen',side_effect=OSError('offline')):result=line.refresh()
        self.assertEqual(result['vehicles'][0]['id'],'last-good');self.assertIsNotNone(result['error'])
        self.assertFalse(service.available(service.routes[1]))

    def test_conservative_eta_does_not_connect_a_potentially_missed_vehicle(self):
        self.assertIsNone(eligible_departure([{'departure_at':1300,'earliest_departure_at':1100}],1200))

    @patch('time.time',return_value=datetime(2026,11,9,17,tzinfo=server.KST).timestamp())
    def test_circle_to_city_transfer_has_walk_and_sums_time_once(self,mock_time):
        service,transit=self.service()
        # Deterministic observed vehicle fixture, not a claim about current operation.
        self.observed(service.lines['41946'],'circle-observed',157,40)
        service.refresh=lambda:service.status();transit.prefetch=lambda pairs:None
        planner=Planner({'routes':self.network['routes']+service.routes},self.graph,transit)
        route=service.routes[1];start=route['stops'][7]
        destination=next(s for r in self.network['routes'] for s in r['stops'] if s['id']=='120000150')
        result=planner.plan((start['lat'],start['lon']),(destination['lat'],destination['lon']),time.time(),'live',PRESETS['fast'])
        connections=[c for c in result['candidates'] if any(l.get('route_id')=='shuttle-41946' for l in c['legs'])]
        self.assertTrue(connections)
        for c in connections:
            self.assertEqual(c['transfers'],1)
            self.assertTrue(any(l.get('label')=='환승 정류소까지' for l in c['legs']))
            self.assertAlmostEqual(c['total_seconds'],sum(l['seconds'] for l in c['legs']),delta=1)
            self.assertLessEqual(sum(l['type']=='bus' for l in c['legs']),2)

    @patch('time.time',return_value=datetime(2026,11,9,17,tzinfo=server.KST).timestamp())
    def test_after_observed_shuttle_later_city_bus_is_an_explicit_scenario(self,mock_time):
        service,transit=self.service();self.observed(service.lines['41946'],'circle-observed',157,40)
        service.refresh=lambda:service.status();transit.prefetch=lambda pairs:None
        real_arrivals=transit.arrivals
        transit.arrivals=lambda route,index:real_arrivals(route,index) if route.get('kind')=='shuttle' else [{'departure_at':time.time()-10,'vehicle_id':'already-departed','full':False}]
        planner=Planner({'routes':self.network['routes']+service.routes},self.graph,transit)
        start=service.routes[1]['stops'][7]
        end=next(s for r in self.network['routes'] for s in r['stops'] if s['id']=='120000150')
        result=planner.plan((start['lat'],start['lon']),(end['lat'],end['lon']),time.time(),'live',PRESETS['fast'])
        connections=[c for c in result['candidates'] if len(c['route_names'])==2 and c['route_names'][0]==service.routes[1]['name']]
        self.assertTrue(connections)
        for c in connections:
            rides=[l for l in c['legs'] if l['type']=='bus']
            if rides[0]['station_id'] in ('snu-101','snu-901'):
                self.assertEqual(rides[0]['arrival_source'],'shuttle_timetable_estimate')
                self.assertIsNone(rides[0]['vehicle_id'])
            else:
                self.assertIn(rides[0]['arrival_source'],('live_shuttle','shuttle_timetable_estimate'))
                if rides[0]['arrival_source']=='live_shuttle':self.assertEqual(rides[0]['vehicle_id'],'circle-observed')
            self.assertEqual(rides[1]['arrival_source'],'service_history_estimate')
            self.assertIsNone(rides[1]['vehicle_id'])
            self.assertTrue(any('実際' in note or '실제 차량은 미확인' in note for note in c['quality_notes']))

if __name__=='__main__':unittest.main(verbosity=2)
