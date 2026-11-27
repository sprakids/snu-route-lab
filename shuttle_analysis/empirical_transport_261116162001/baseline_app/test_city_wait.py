import copy,json,unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from prepare_city_queue import first_boardable
from simulation_kernel import first_boardable as reference_fifo
from city_wait import profile,project,full_risk
from continuity import Continuity
from shuttle_timetable import KST
from queue_release import compatibility,validate_city
import server

def stamp(text):return datetime.fromisoformat(text).replace(tzinfo=KST).timestamp()

class CityFifoTests(unittest.TestCase):
    def test_compatible_fifo_matches_frozen_kernel_without_source_exits(self):
        wanted={('a',0)};events=[(100,('b',0),4),(200,('a',0),2),(300,('a',0),5)]
        waiting=[(5,{('a',0),('b',0)},None),(3,{('a',0)},None),(100,{('c',0)},None)]
        at,skips,first=first_boardable(events,waiting,90,wanted)
        vehicles=[{'rid':pair[0],'cap':free,'last_stop':-1,'onboard':[]} for t,pair,free in events]
        queue=[{'w':w,'stage':0,'stages':[{'pool':[{'rid':rid,'board':i,'alight':i+1} for rid,i in pairs]}]} for w,pairs,e in waiting]
        expected=reference_fifo([(t,vid,pair[1]) for vid,(t,pair,free) in enumerate(events)],vehicles,90,90,{'rid':'a','board':0,'alight':1},1,queue)
        self.assertEqual(at,expected[0]);self.assertEqual((skips,first),(1,200))
        self.assertEqual(waiting[0][0],5)
    def test_exits_free_queues_and_missed_buses_cannot_be_reused(self):
        at,skips,first=first_boardable([(50,('a',0),100),(100,('a',0),2),(200,('a',0),2)],[(10,{('a',0)},150)],90,{('a',0)})
        self.assertEqual((at,skips,first),(200,1,100))
    def test_incompatible_passengers_never_consume_seats(self):
        self.assertEqual(first_boardable([(100,('a',0),1)],[(1000,{('b',0)},None)],90,{('a',0)})[0],100)

class CityWaitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads((Path(__file__).parent/'data/auto_queue_inputs.json').read_bytes())
        cls.city=cls.data['city_wait'];cls.app=server.Application()
    def setUp(self):
        self.now=stamp('2026-11-09T16:00:00');self.route=self.app.network['routes'][0];self.seq=self.route['stops'][0]['seq'];self.key=f'{self.route["id"]}:{self.seq}'
    def history(self,day='2026-11-08',full=5,n=50):
        return {'crowd_history':{self.route['id']:{'hour':16,'weekday':0,'dates':[day],'cohort':'pooled_hour',
            'counts':[20,10,10,10],'availability':{'5':[full,n]},'sections':{str(self.seq):{'counts':[20,10,10,10],'dates':[day],'availability':{'5':[full,n]}}}}}}
    def stub(self,data=None):
        model=SimpleNamespace(data=data or self.data,config={'id':'261109160000'})
        transit=SimpleNamespace(now=lambda:self.now,interval=lambda r,t:10,in_service=lambda r,t:True,plan_snapshot={},history_snapshot={})
        return model,transit
    def test_eight_routes_and_gate_pool_have_verified_directional_curves(self):
        validate_city(self.city)
        self.assertEqual({s['route_id'] for s in self.city['services'].values() if s.get('route_id')},{r['id'] for r in self.app.network['routes']})
        self.assertIn('pool:120000029',self.city['services'])
        self.assertEqual(len(self.city['profiles']),5*len(self.city['services']))
    def test_weekends_and_missing_stops_are_unknown_cohorts_not_empty_queues(self):
        self.assertFalse(profile(self.city,self.key,stamp('2026-11-08T16:00:00'))['available'])
        self.assertFalse(profile(self.city,'unknown:1',self.now)['available'])
    def test_censored_phases_do_not_create_a_served_only_average(self):
        data=copy.deepcopy(self.city);data['profiles']['0:'+self.key]=[[960,None,None,50.,1]]
        result=profile(data,self.key,self.now);self.assertFalse(result['available']);self.assertIsNone(result['extra_wait_seconds'])
    def test_delay_uses_simulation_but_never_invents_vehicle_identity(self):
        data=copy.deepcopy(self.data);data['city_wait']['profiles']['0:'+self.key]=[[960,120,1,50,0]]
        data['city_wait']['services'][self.key]['reference_headway_seconds']=600
        model,t=self.stub(data);base={'departure_at':self.now+60,'provided_at':self.now,'vehicle_id':'observed','crowd_cost':2,'full':False}
        result=project(model,t,self.route,0,self.now,base,True,headway=600)
        self.assertEqual(result['departure_at'],self.now+180);self.assertEqual(result['city_wait']['extra_wait_seconds'],120)
        self.assertIsNone(result['vehicle_id']);self.assertIsNone(result['provided_at']);self.assertEqual(base['vehicle_id'],'observed')
        self.assertFalse(result['city_wait']['observed_queue']);self.assertFalse(result['city_wait']['grade_to_seats_conversion'])
    def test_binary_full_risk_is_not_added_twice_to_simulated_capacity_delay(self):
        data=copy.deepcopy(self.data);data['city_wait']['profiles']['0:'+self.key]=[[960,120,1,50,0]]
        data['city_wait']['services'][self.key]['reference_headway_seconds']=600
        model,t=self.stub(data);base={'departure_at':self.now+60,'provided_at':self.now,'vehicle_id':'observed','crowd_cost':2,'full':False}
        result=project(model,t,self.route,0,self.now,base,True,history=self.history(),headway=600)
        self.assertEqual(result['city_wait']['extra_wait_seconds'],120)
        self.assertTrue(result['city_wait']['empirical_full_risk']['available'])
    def test_current_and_future_binary_labels_cannot_enter_prior(self):
        for day in ('2026-11-09','2026-11-10'):
            self.assertFalse(full_risk(self.history(day),self.route['id'],self.seq,self.now,self.now,'5')['available'])
        self.assertTrue(full_risk(self.history(),self.route['id'],self.seq,self.now,self.now,'5')['available'])
    def test_latest_saved_crowd_labels_feed_continuity_without_refitting_test_dates(self):
        counts,cohort,dates=Continuity().counts(self.route['id'],self.seq,self.now,self.now,self.history()['crowd_history'])
        self.assertEqual(counts,[20,10,10,10]);self.assertIn('shared_',cohort);self.assertIn('pooled_dates',cohort)
        counts,cohort,dates=Continuity().counts(self.route['id'],self.seq,self.now,self.now,self.history('2026-11-09')['crowd_history'])
        self.assertNotEqual(counts,[20,10,10,10])
    def test_historical_queries_ignore_current_vehicle_full_grade(self):
        model,t=self.stub();base={'departure_at':self.now+60,'vehicle_id':None,'provided_at':None}
        a=project(model,t,self.route,0,self.now,base,False,history=self.history())
        b=project(model,t,self.route,0,self.now,{**base,'provided_at':self.now,'crowd_cost':0},False,history=self.history())
        self.assertEqual(a['city_wait'],b['city_wait'])
    def test_network_changes_reject_city_contract(self):
        data=copy.deepcopy(self.city);data['network_sha256']='0'*64
        with self.assertRaises(ValueError):validate_city(data)
    def test_release_compatibility_covers_city_members(self):
        data=copy.deepcopy(self.data);key=next(iter(data['city_wait']['services']))
        data['city_wait']['services'][key]['members']=[['other',1]]
        self.assertNotEqual(compatibility(data),compatibility(self.data))
    def test_real_plan_applies_the_same_model_to_city_and_shuttle_legs(self):
        with patch('urllib.request.urlopen',side_effect=AssertionError('No provider calls')),patch('time.time',return_value=self.now):
            result=self.app.plan({'origin_id':'snu-410','destination_id':'snu-station','mode':'estimate','departure_at':self.now})
        self.assertTrue(result['city_wait_model_applied']);self.assertTrue(result['automatic_queue_applied'])
        ids={l['city_wait']['model_id'] for c in result['candidates'] for l in c['legs'] if l.get('city_wait')}
        self.assertEqual(ids,{result['prediction_model']['queue_model']})
        for c in result['candidates']:
            self.assertAlmostEqual(c['total_seconds'],sum(l['seconds'] for l in c['legs']),delta=1)

if __name__=='__main__':unittest.main()
