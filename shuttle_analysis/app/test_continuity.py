import json,math,tempfile,time,unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
from continuity import Continuity
from walking_profile import WALK_MPS,seconds
from automatic_queue import simulate,queue_at
from routing import WalkingGraph
from shuttle_timetable import KST
import server

def stamp(s):return datetime.fromisoformat(s).replace(tzinfo=KST).timestamp()

class ContinuityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.network=json.loads((Path(__file__).parent/'data/network.json').read_text(encoding='utf-8'))
        cls.route=cls.network['routes'][0]
    def setUp(self):self.now=stamp('2026-11-08T16:00:00');self.model=Continuity()

    def test_user_average_walking_pace_is_4p8_also_on_routes_with_stairs(self):
        self.assertAlmostEqual(WALK_MPS,4/3)
        self.assertAlmostEqual(seconds(1000),750.)
        self.assertAlmostEqual(seconds(1000,100),750.)
        payload={'elements':[{'type':'node','id':1,'lat':37.46,'lon':126.95},
          {'type':'node','id':2,'lat':37.46,'lon':126.951},{'type':'way','nodes':[1,2],'tags':{'highway':'footway'}}]}
        graph=WalkingGraph(payload);edge=graph.edges[1][0]
        self.assertAlmostEqual(edge[1],edge[2]/WALK_MPS)

    def test_future_or_current_day_grade_aggregates_cannot_leak_into_prior(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'model.json';p.write_text(json.dumps({'grades':[['2026-11-08',self.route['id'],1,16,0,0,999,0]],'headways':[],'transitions':[],'dates':['2026-11-08']}))
            counts,cohort,dates=Continuity(p).counts(self.route['id'],1,self.now,self.now)
        self.assertEqual(sum(counts),0);self.assertEqual(dates,[])

    def test_fresh_matching_grade_is_observed_but_future_boarding_is_estimated(self):
        e={'provided_at':self.now,'crowd_code':'5'}
        fresh=self.model.predict_crowd(self.route,0,self.now+40,self.now,e,1)
        later=self.model.predict_crowd(self.route,0,self.now+300,self.now,e,1)
        self.assertEqual(fresh['crowd_source'],'observed');self.assertEqual(fresh['crowd_cost'],2)
        self.assertEqual(later['crowd_source'],'observation_simulation_estimate');self.assertIsNone(later['crowd_cost'])
        self.assertEqual(later['prediction_horizon_seconds'],300);self.assertFalse(later['calibrated'])

    def test_unknown_grade_gets_a_conservative_scenario_not_an_empty_bus(self):
        route=next(r for r in self.network['routes'] if r['id']=='120900011')
        r=self.model.predict_crowd(route,0,self.now,self.now,{'crowd_code':'0','provided_at':self.now},1)
        self.assertEqual(r['crowd_source'],'simulation_scenario_estimate');self.assertIsNone(r['crowd_cost'])
        self.assertGreaterEqual(r['crowd_risk'],2.5);self.assertFalse(r['calibrated'])

    def test_proxy_and_future_queries_never_claim_a_current_vehicle_grade(self):
        e={'provided_at':self.now,'crowd_code':'6','is_proxy':True}
        r=self.model.predict_crowd(self.route,0,self.now,self.now,e,1)
        self.assertNotEqual(r['crowd_source'],'observed')
        a=self.model.predict_crowd(self.route,0,self.now+86400,self.now,e,1,False)
        b=self.model.predict_crowd(self.route,0,self.now+86400,self.now,{},None,False)
        self.assertEqual(a,b)

    def test_estimation_remains_finite_after_the_old_10_minute_cutoff(self):
        for age in (91,600,601,3600,21601):
            r=self.model.predict_crowd(self.route,0,self.now,self.now,{'crowd_code':'4','provided_at':self.now-age},1)
            self.assertTrue(math.isfinite(r['crowd_estimate']));self.assertIsNone(r['crowd_cost'])
            self.assertNotEqual(r['crowd_source'],'unavailable');self.assertLessEqual(r['crowd_risk'],3)

    def test_old_eta_is_only_an_anchor_for_an_unidentified_service_opportunity(self):
        t=server.Transit(self.network);rid=self.route['id'];seq=self.route['stops'][0]['seq']
        t.cache[(rid,seq)]={'fetched_at':self.now,'values':[{'provided_at':self.now-200,'departure_at':self.now+100,'vehicle_id':'old-private-id'}]}
        with patch('time.time',return_value=self.now),patch('urllib.request.urlopen',side_effect=AssertionError('No provider calls')):
            self.assertEqual(t.arrivals(self.route,0),[])
            r=t.forecast_service(self.route,0,self.now+20,[],True)
        self.assertIsNone(r['vehicle_id']);self.assertIsNone(r['provided_at'])
        self.assertEqual(r['based_on_observed_at'],self.now-200)
        self.assertIn('last_arrival',r['arrival_forecast']['source'])

    def test_full_observation_is_not_rebound_to_a_boardable_forecast(self):
        t=server.Transit(self.network);known=[{'provided_at':self.now,'departure_at':self.now+60,'vehicle_id':'full','full':True}]
        with patch('time.time',return_value=self.now):r=t.forecast_service(self.route,0,self.now+20,known,True)
        self.assertIsNone(r['vehicle_id']);self.assertFalse(r['full']);self.assertGreater(r['departure_at'],self.now+60)
        self.assertTrue(r['arrival_forecast']['conditional_after_known_services'])

    def test_latest_ready_flow_does_not_add_a_second_20_second_preparation(self):
        r={'id':'shuttle-41946','n':1,'loop':True,'offsets':[0,30],'anchor':0,'capacity':60,
            'stops':[{'board_allowed':True}],'ready_flows':[[0,0,8*3600,10.]],'flows':[],'od':{}}
        x=simulate(r,0,.5,1,0,lambda *args:1.,15)
        self.assertEqual(queue_at(x,0,8*3600+7),0)
        self.assertEqual(queue_at(x,0,8*3600+8),10.)
        self.assertAlmostEqual(x['input_mass'],x['boarded_mass']+x['remaining_mass'])

    def test_shuttle_forecast_preview_does_not_call_the_operator(self):
        with patch('urllib.request.urlopen',side_effect=AssertionError('No upstream calls')):
            app=server.Application();t=app.transit
            with patch('time.time',return_value=stamp('2026-11-09T16:00:00')):
                for line in t.shuttle.lines.values():line.refresh=lambda:(_ for _ in ()).throw(AssertionError('No BUSIN refresh'))
                r=t.shuttle.routes[0]
                response=t.arrival_preview([{'route_id':r['id'],'seq':2,'forecast_only':True}])
        self.assertEqual(response['position_calls_triggered'],0)
        self.assertIsNotNone(response['stops'][0]['arrival_forecast'])
        self.assertTrue(all(v.get('vehicle_id') is None for v in response['stops'][0]['values']))
        q=response['stops'][0]['values'][0]['automatic_queue']
        self.assertEqual(q['model_id'],'V261125170855')
        self.assertEqual(q['algorithm_id'],'snu-terminal-wait-v1')
        self.assertEqual(q['crowd_model_id'],q['model_id'])
        self.assertIsNotNone(q['expected_load_ratio'])

if __name__=='__main__':unittest.main()
