import unittest
from datetime import datetime
from unittest.mock import patch
import server
from routing import PRESETS,distance
from strategies import GATE_STOP,STATION_STOP,GATE_ROUTES,compare_strategies

class StrategyComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=server.Application()
        cls.when=datetime(2026,11,9,17,tzinfo=server.KST).timestamp()

    def setUp(self):
        self.clock=patch('time.time',return_value=self.when);self.clock.start();self.addCleanup(self.clock.stop)
        self.requests=[];self.app.transit.prefetch=lambda pairs:self.requests.extend(pairs)
        self.app.transit.shuttle.refresh=lambda:self.app.transit.shuttle.status()
        self.app.transit.snapshot={};self.app.transit.plan_snapshot={};self.app.transit.history_snapshot={}
        self.app.transit.arrivals=lambda route,index:[]
        self.external=patch('urllib.request.urlopen',side_effect=AssertionError('No external calls in strategy tests'))
        self.network_mock=self.external.start();self.addCleanup(self.external.stop)

    def run_plan(self,origin,live=False,shuttle=True):
        target=self.app.destinations[0]
        result=self.app.planner.plan(origin,(target['lat'],target['lon']),self.when,
                                    'live' if live else 'estimate',PRESETS['fast'],shuttle)
        self.app.historical.attach(result,self.app.planner)
        result['strategy_comparison']=compare_strategies(result)
        self.assertEqual(self.network_mock.call_count,0)
        return result

    def upper_origin(self):
        point=next(o for o in self.app.origins if o['id']=='120000174')
        return point['lat'],point['lon']

    def gate_origin(self):
        stop=self.app.stops[GATE_STOP];return stop['lat'],stop['lon']

    def test_upper_campus_preserves_all_five_direct_gate_options(self):
        result=self.run_plan(self.upper_origin())
        gate=[c for c in result['candidates'] if c['strategy']=='walk_to_gate']
        self.assertEqual({c['legs'][3]['route_id'] for c in gate},GATE_ROUTES)
        self.assertTrue(all(c['walk_m']>1300 for c in gate))
        for c in gate:
            bus=next(l for l in c['legs'] if l['type']=='bus')
            self.assertEqual(bus['station_id'],GATE_STOP)
            self.assertEqual(bus['station_ars'],'21128');self.assertGreater(bus['to_seq'],bus['from_seq'])
            self.assertAlmostEqual(c['total_seconds'],sum(l['seconds'] for l in c['legs']),delta=1)
        self.assertIsNotNone(result['strategy_comparison']['strategies']['shuttle_wait'])

    def test_walking_beyond_two_arrivals_keeps_an_explicit_unknown_vehicle_scenario(self):
        self.app.transit.arrivals=lambda route,index:[] if route.get('kind')=='shuttle' else [
            {'departure_at':self.when+30,'provided_at':self.when,'vehicle_id':'first','full':False},
            {'departure_at':self.when+120,'provided_at':self.when,'vehicle_id':'second','full':False}]
        result=self.run_plan(self.upper_origin(),live=True,shuttle=False)
        gate=[c for c in result['candidates'] if c['strategy']=='walk_to_gate' and not c.get('common_gate_service')]
        self.assertEqual(len(gate),5)
        for c in gate:
            bus=next(l for l in c['legs'] if l['type']=='bus')
            self.assertIn(bus['arrival_source'],('service_history_estimate','city_queue_estimate'));self.assertIsNone(bus['vehicle_id'])
            self.assertTrue(any('실제 차량은 미확인' in n for n in c['quality_notes']))
        self.assertLessEqual(len(self.requests),16)
        gate_requests={r['id'] for r,i in self.requests if r['stops'][i]['id']==GATE_STOP}
        self.assertEqual(gate_requests,GATE_ROUTES)

    def test_full_first_vehicle_uses_next_feasible_vehicle(self):
        self.app.transit.arrivals=lambda route,index:[
            {'departure_at':self.when+30,'provided_at':self.when,'vehicle_id':'full','full':True,'crowd_cost':3},
            {'departure_at':self.when+90,'provided_at':self.when,'vehicle_id':'next','full':False,'crowd_cost':0,'crowd_label':'여유'}]
        result=self.run_plan(self.gate_origin(),live=True,shuttle=False)
        for c in result['candidates']:
            if c['strategy']!='walk_to_gate':continue
            bus=next(l for l in c['legs'] if l['type']=='bus')
            if bus.get('city_wait',{}).get('extra_wait_seconds',0):
                self.assertIsNone(bus['vehicle_id']);self.assertNotEqual(bus['crowd_source'],'observed')
                self.assertEqual(bus['arrival_source'],'city_queue_estimate')
            else:
                self.assertEqual(bus['vehicle_id'],'next');self.assertEqual(bus['crowd_source'],'observed')
                self.assertEqual(bus['crowd_cost'],0)
            self.assertGreaterEqual(bus['departure_at'],self.when+90)

    def test_two_full_vehicles_do_not_become_a_fake_boardable_bus(self):
        self.app.transit.arrivals=lambda route,index:[{'departure_at':self.when+60,'provided_at':self.when,'vehicle_id':'full','full':True}]
        result=self.run_plan(self.gate_origin(),live=True,shuttle=False)
        gate=result['strategy_comparison']['strategies']['walk_to_gate']
        self.assertIsNotNone(gate)
        for b in gate['boarding']:
            self.assertIsNone(b['vehicle_id']);self.assertEqual(b['arrival_source'],'service_history_estimate')
            self.assertGreater(b['departure_at'],self.when+60)

    def test_comparison_selects_shortest_total_independently_of_weighted_card_order(self):
        result=self.run_plan(self.upper_origin())
        expected=min(result['candidates'],key=lambda c:(c['total_seconds'],c['crowd_risk']))
        self.assertEqual(result['strategy_comparison']['recommended_candidate_id'],expected['id'])
        for c in result['candidates']:
            if c['strategy']=='walk_to_gate':
                self.assertTrue(c['historical_demand']['available'])
                self.assertIsNone(c['crowd_cost'])

    def test_live_and_future_rides_can_use_completed_historical_speed(self):
        route=self.app.planner.by_id['100100252'];i=6;j=10
        sections={str(s['seq']):{'speed_kmh':24,'days':3} for s in route['stops'][i+1:j+1]}
        historical={'historical_traffic':{route['id']:{'weekday':0,'hour':17,'dates':['20261019','20261026','20261102'],'sections':sections}}}
        self.app.transit.plan_snapshot=historical
        self.app.transit.history_snapshot=historical
        for live in (True,False):
            value=self.app.planner.ride_estimate(route,i,j,self.when,live)
            self.assertEqual(value['source'],'historical_section_speed')
            self.assertEqual(value['current_segments'],0)

    def test_fresh_cache_does_not_make_an_expired_provider_eta_live(self):
        route=self.app.planner.by_id['100100252'];index=6
        self.app.transit.cache[(route['id'],route['stops'][index]['seq'])]={
            'fetched_at':self.when,'values':[{'provided_at':self.when-151,'departure_at':self.when+90}]}
        # Call the implementation; other tests replace arrivals with controlled fixtures.
        self.assertEqual(server.Transit.arrivals(self.app.transit,route,index),[])

if __name__=='__main__':unittest.main()
