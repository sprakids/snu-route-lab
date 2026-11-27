import copy,json,math,time,unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
import server
from automatic_queue import AutomaticQueue,grade_signals,multiplier,pressure,queue_at,simulate
from shuttle_timetable import KST
from routing import PRESETS

def stamp(text):return datetime.fromisoformat(text).replace(tzinfo=KST).timestamp()

class QueueMechanicsTests(unittest.TestCase):
    def route(self,alight=2):
        return {'id':'shuttle-41946','n':2,'loop':True,'offsets':[0,30,60,90],'anchor':0,'capacity':60,
                'stops':[{'board_allowed':True},{'board_allowed':True}],
                'flows':[[0,0,480,50.],[0,1,480,30.]],'od':{'0:0':[[alight,1.]],'0:1':[[1,1.]]}}
    def test_upstream_boardings_reduce_downstream_seats_and_preserve_mass(self):
        x=simulate(self.route(),0,0,1,0,lambda i,t:1.)
        row=next(r for r in x['supply'][1] if r['at']==8*3600+390)
        self.assertAlmostEqual(row['free'],10.)
        self.assertAlmostEqual(queue_at(x,1,8*3600+391),20.)
        self.assertAlmostEqual(x['input_mass'],x['boarded_mass']+x['remaining_mass'])
        self.assertLessEqual(x['max_load'],60+1e-8)
    def test_alighting_releases_capacity_before_the_next_queue(self):
        x=simulate(self.route(alight=1),0,0,1,0,lambda i,t:1.)
        row=next(r for r in x['supply'][1] if r['at']==8*3600+390)
        self.assertAlmostEqual(row['free'],60.)
        self.assertAlmostEqual(queue_at(x,1,8*3600+391),0.)
    def test_arrival_bins_do_not_appear_before_walking_arrival_and_prep(self):
        x=simulate(self.route(),0,0,1,0,lambda i,t:1.)
        self.assertEqual(queue_at(x,0,8*3600+34),0.)
        self.assertGreater(queue_at(x,0,8*3600+35),0.)
    def test_more_inflow_and_less_capacity_increase_unserved_backlog(self):
        r=self.route();r['flows']=[[0,0,1259,1000.]]
        low=simulate(r,0,0,.75,0,lambda i,t:1.)
        high=simulate(r,0,0,1.25,.2,lambda i,t:1.)
        self.assertGreater(high['remaining_mass'],low['remaining_mass'])
        self.assertAlmostEqual(high['input_mass'],high['boarded_mass']+high['remaining_mass'])
    def test_bus_observations_are_section_matched_deduplicated_and_time_limited(self):
        node={'city_links':[{'route_id':'r','section_order':'2'}]};now=10000
        vehicles=[{'route_id':'r','id':'one','section_order':'2','provided_at':now-60,'crowd_code':'3'},
                  {'route_id':'r','id':'one','section_order':'2','provided_at':now-15,'crowd_code':'6'},
                  {'route_id':'r','id':'wrong-section','section_order':'3','provided_at':now,'crowd_code':'6'},
                  {'route_id':'r','id':'old','section_order':'2','provided_at':now-601,'crowd_code':'6'},
                  {'route_id':'r','id':'future','section_order':'2','provided_at':now+6,'crowd_code':'6'}]
        values=grade_signals(node,vehicles,now);self.assertEqual(len(values),1);self.assertEqual(values[0]['value'],1.)
        config={'live_max_age_seconds':600,'live_fresh_seconds':90,'live_decay_seconds':180}
        self.assertEqual(pressure(values,now,config),1.)
        self.assertEqual(pressure(values,now+601,config),.5)
        self.assertEqual(pressure(values,now-100,config),.5)
    def test_history_and_live_pressure_change_demand_only_with_bounded_unfitted_weights(self):
        c={'historical_beta':.25,'live_beta':.25,'factor_bounds':[.75,1.25]}
        self.assertEqual(multiplier(None,.5,c),1.)
        self.assertEqual(multiplier(1.,1.,c),1.25)
        self.assertEqual(multiplier(0.,0.,c),.75)
    def test_reconstruction_conserves_mass_and_bounds_packet_discretization(self):
        r=self.route();a=simulate(r,0,0,1,0,lambda i,t:1.,30);b=simulate(r,0,0,1,0,lambda i,t:1.,15)
        self.assertAlmostEqual(a['input_mass'],b['input_mass'])
        self.assertLessEqual(abs(queue_at(a,1,8*3600+391)-queue_at(b,1,8*3600+391)),30/(300/30))
        self.assertAlmostEqual(a['boarded_mass']+a['remaining_mass'],b['boarded_mass']+b['remaining_mass'])

class AutomaticIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=server.Application()
    def setUp(self):
        self.now=stamp('2026-11-09T16:00:00');self.clock=patch('time.time',return_value=self.now);self.clock.start();self.addCleanup(self.clock.stop)
        self.network=patch('urllib.request.urlopen',side_effect=AssertionError('No extra APIs for queue estimation'));self.net=self.network.start();self.addCleanup(self.network.stop)
        t=self.app.transit;t.prefetch=lambda pairs:None;t.arrivals=lambda r,i:[];t.shuttle.refresh=lambda:t.shuttle.status()
        t.snapshot={};t.plan_snapshot={};t.history_snapshot={}
    def admin(self):
        r=self.app.transit.shuttle.routes[0];i=next(i for i,s in enumerate(r['stops']) if s['id']=='snu-410');return r,i
    def test_plan_without_manual_input_uses_automatic_queue_in_total_time(self):
        x=self.app.plan({'origin_id':'snu-410','destination_id':'snu-station','departure_at':self.now,'mode':'live','preset':'fast'})
        self.assertTrue(x['automatic_queue_applied']);self.assertFalse(x['queue_report_applied'])
        self.assertTrue({'shuttle-41841','shuttle-41946','shuttle-41914'} <=
                        {c['boarding'][0]['route_id'] for c in x['strategy_comparison']['shuttle_options']})
        # The newly connected Daehak-dong shuttle may also transfer toward the
        # station, but must not inherit another route's automatic queue profile.
        for c in x['strategy_comparison']['shuttle_options']:
            if c['boarding'][0]['route_id']=='shuttle-41843':self.assertTrue(c['automatic_queues'])
        self.assertEqual(self.net.call_count,0)
        for c in x['candidates']:
            self.assertEqual(c['total_seconds'],sum(l['seconds'] for l in c['legs']))
            for i,l in enumerate(c['legs']):
                if not l.get('automatic_queue'):continue
                self.assertEqual(l['arrival_source'],'shuttle_auto_queue_estimate')
                self.assertEqual(c['legs'][i-1]['seconds'],l['automatic_queue']['expected_wait_seconds'])
                self.assertFalse(l['automatic_queue']['observed_queue']);self.assertFalse(l['automatic_queue']['calibrated'])
                self.assertIsNone(l['crowd_cost']);self.assertIsNone(l['vehicle_id'])
                self.assertNotIn('queue_model',l['arrival_options'][0])
    def test_future_queue_never_uses_current_bus_grades(self):
        r,i=self.admin();model=self.app.transit.automatic_queue
        plain=model.arrival(r,i,self.now+20,[],self.app.transit.shuttle.timetable,self.now,{},False)
        node=model.data['routes'][r['id']]['stops'][i];link=node['city_links'][0]
        snapshot={'vehicles':[{'route_id':link['route_id'],'section_order':link['section_order'],'id':'fake','provided_at':self.now,'crowd_code':'6'}]}
        other=model.arrival(r,i,self.now+20,[],self.app.transit.shuttle.timetable,self.now,snapshot,False)
        self.assertEqual(plain,other);self.assertFalse(other[0]['automatic_queue']['live_signal']['available'])
    def test_unchanged_observation_inputs_reuse_profiles_across_queries(self):
        r,i=self.admin();model=AutomaticQueue(self.app.historical)
        with patch('automatic_queue.simulate',wraps=simulate) as run:
            model.arrival(r,i,self.now+20,[],self.app.transit.shuttle.timetable,self.now,{},True)
            initial=run.call_count;self.assertEqual(initial,24)
            model.arrival(r,i,self.now+51,[],self.app.transit.shuttle.timetable,self.now+31,{},True)
            self.assertEqual(run.call_count,initial)
    def test_shuttle_model_only_policy_ignores_city_bus_crowd_observations(self):
        r,i=self.admin();model=self.app.transit.automatic_queue;node=model.data['routes'][r['id']]['stops'][i];link=node['city_links'][0]
        snapshot={'vehicles':[{'route_id':link['route_id'],'section_order':link['section_order'],'id':'one','provided_at':self.now-15,'crowd_code':'6'}]}
        value=model.arrival(r,i,self.now+20,[],self.app.transit.shuttle.timetable,self.now,snapshot,True)[0]
        q=value['automatic_queue'];self.assertEqual(q['live_signal']['vehicles'],0);self.assertFalse(q['live_signal']['available'])
        self.assertEqual(q['current_demand_multiplier'],1.);self.assertIsNone(value['crowd_cost']);self.assertTrue(q['model_only'])
    def test_no_served_only_average_when_a_central_phase_cannot_board(self):
        r,i=self.admin();model=self.app.transit.automatic_queue.current();mid=stamp('2026-11-09T00:00:00');n=model.data['routes'][r['id']]['n']
        profiles=[]
        for k in range(8):
            rows=[[] for _ in range(n)]
            if k:rows[i]=[{'at':self.now-mid+100,'free':60}]
            profiles.append({'scenario':{'demand':1},'keys':[[] for _ in range(n)],'values':[[] for _ in range(n)],'supply':rows})
        with patch.object(model,'profiles',return_value=(profiles,[[] for _ in range(n)],mid)):
            self.assertEqual(model.arrival(r,i,self.now+20,[],self.app.transit.shuttle.timetable,self.now,{},False),[])
    def test_weekend_and_holiday_have_no_automatic_regular_shuttle(self):
        r,i=self.admin();model=self.app.transit.automatic_queue
        for when in (stamp('2026-11-08T16:00:00'),stamp('2026-10-15T16:00:00')):
            self.assertIsNone(model.arrival(r,i,when,[],self.app.transit.shuttle.timetable,self.now,{},False))
    def test_snapshot_has_all_routes_source_hashes_and_only_aggregate_course_flow(self):
        d=self.app.transit.automatic_queue.data
        self.assertEqual(len(d['routes']),10)
        self.assertEqual(sum(d['routes'][rid]['n'] for rid in ('shuttle-41841','shuttle-41946','shuttle-41914')),43)
        self.assertIn('latest_regular_mon',d['source_sha256']);self.assertIn('travel_clock',d['source_sha256']);self.assertFalse(d['observed_queue'])
        self.assertEqual(d['course_end_events'],6201)
        self.assertEqual(d['reference_scenario']['immediate_trip_share'],.5)
        self.assertNotIn('course_title',json.dumps(d));self.assertFalse(d['model']['calibrated'])

if __name__=='__main__':unittest.main()
