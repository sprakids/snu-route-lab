import unittest,math,contextlib,io,tempfile
from pathlib import Path
from unittest.mock import patch
from artifacts import ROOT,read,START,END
from preferences import traits,Prediction,cost,choose,walking_weight
from hazard import ReviewClock,interval_probability,integrated
from physics import segment_seconds
from fares import FareLedger,board,alight
from fixtures import fixture,leg,vehicle,waiter
from capacity import capacity_at_clock,batch_size_at_clock
from dwell import Vehicle,simulate_batch
import engine
from policy import attach_policy

class PrimitiveTests(unittest.TestCase):
    def setUp(self):self.config=read(ROOT/'config.json')
    def test_tastes_are_persistent_and_individual(self):
        a=traits(123,self.config);self.assertEqual(a,traits(123,self.config));self.assertNotEqual(a,traits(124,self.config))
    def test_preference_does_not_change_physical_eta(self):
        p=Prediction(600,walk=600);a=traits(123,self.config);eta=p.eta
        self.assertNotAlmostEqual(cost(p,a),10);self.assertEqual(p.eta,eta)
        self.assertEqual(segment_seconds(1000),750)
    def test_convex_wait_preference_changes_cost_without_adding_travel_time(self):
        bundle=fixture([('A',1,100)],self.config)
        policy=attach_policy(bundle,self.config,None,None,None,None,[],[],[],[],[],[],{},None,None,None,[],[])
        state={'traits':traits(1,self.config),'history':[],'stop_entry':0.,'full_passes':0}
        plain=Prediction(600,wait=600,first_wait=600)
        convex=Prediction(600,wait=600,first_wait=600,wait_squared=600**2)
        self.assertAlmostEqual(policy.generalized(convex,state)-policy.generalized(plain,state),10*state['traits'].wait)
        self.assertEqual((plain.eta,convex.eta),(600,600));self.assertEqual(state['history'],[])
    def test_stairs_time_is_local_not_added_to_every_segment(self):
        total=segment_seconds(100)+segment_seconds(100,stairs=True)
        self.assertEqual(total,75+225);self.assertNotEqual(total,600)
    def test_hazard_composes_across_time_steps(self):
        p=interval_probability(0,600,0,1,1,self.config)
        for dt in (1,5,15,60):
            survival=math.prod(1-interval_probability(a,min(600,a+dt),0,1,1,self.config) for a in range(0,600,dt))
            self.assertAlmostEqual(1-survival,p,places=12)
    def test_same_hazard_event_after_many_information_updates(self):
        a=ReviewClock.start(0,0,0,0,123,1,self.config);b=ReviewClock.start(0,0,0,0,123,1,self.config)
        due=a.due(self.config)
        for t in range(1,int(due)):
            b.update(t,0,0,self.config)
        self.assertAlmostEqual(b.due(self.config),due,places=8)
    def test_change_decay_unbounded_and_full_wait_raise_hazard(self):
        ordinary={**self.config,'review_age_stress_rate_per_second':0,'review_full_stress_rate_per_second':0}
        h=[integrated(0,60,n,0,1,ordinary) for n in range(101)]
        self.assertTrue(all(a>b>0 for a,b in zip(h,h[1:])))
        self.assertAlmostEqual(h[1]/h[0],.3)
        self.assertGreater(integrated(600,660,3,2,1,self.config),integrated(0,60,3,0,1,self.config))
        self.assertGreater(integrated(600,660,100,2,1,self.config),0)
    def test_past_full_passages_change_forecast_not_real_current_vehicle_capacity(self):
        v=vehicle();v.update(times=[100.,200.],seat_history={('A',0):[(0.,0.),(10.,0.)]})
        self.assertIsNone(engine.first_boardable([(100.,0,0)],[v],20,20,leg(),1,[]))
        self.assertEqual(v['cap'],50)
        self.assertEqual(engine.first_boardable([(100.,0,0)],[v],100,100,leg(),1,[])[0],100)
    def test_duplicate_options_do_not_amplify_choice(self):
        options=[{'key':'A','cost':10},{'key':'B','cost':11}]
        for uid in range(100):
            self.assertEqual(choose(options,uid,'e',self.config)['key'],choose(options+[options[0]]*20,uid,'e',self.config)['key'])
    def test_live_prefix_updates_after_each_boarding_without_rebuild(self):
        live=engine.LiveMass([10.,20.,30.]);self.assertEqual(live.prefix(3),60.)
        live.add(0,-10.);live.add(1,-5.)
        self.assertEqual([live.prefix(i) for i in range(4)],[0,0,15,45])
        cache={'types':[{'indices':[0,1,2],'prefix':[0,10,30,60],'live_mass':live}]}
        view=engine.QueueView(cache,2)
        self.assertEqual(view.totals,[45]);self.assertEqual(view.prefix(0,1),15)
    def test_walking_plateau_and_tail(self):
        self.assertEqual([walking_weight(d) for d in [0,100,500]],[1,1,1]);self.assertAlmostEqual(walking_weight(1000),.3)
        self.assertLess(walking_weight(1500),.02)
    def test_incremental_fare_not_full_fare_for_each_ride(self):
        f,l=board(FareLedger(),'village',60000,1200,1000);self.assertEqual(f,1200)
        l=alight(l,'village',60100,1200)
        f,l=board(l,'city',60200,1500,2000);self.assertEqual(f,300)
        l=alight(l,'city',60400,1500)
        f,l=board(l,'city-other',60500,1500,2000);self.assertEqual(f,0)
    def test_free_shuttle_does_not_reset_paid_transfer_clock(self):
        f,l=board(FareLedger(),'city',60000,1500,1000);l=alight(l,'city',60100,1500)
        f,q=board(l,'shuttle-x',60200,0,1000);q=alight(q,'shuttle-x',60300,0)
        self.assertEqual(q.last_alight,60100);self.assertEqual(f,0)
        f,q=board(q,'other',62100,1500,1000);self.assertEqual(f,1500)
    def test_capacity_full_then_third_bus_and_alighting(self):
        rows=[(100.,0,0),(200.,1,0),(300.,2,0)]
        fleet=[vehicle(onboard=[(1,{'w':50})]),vehicle(onboard=[(1,{'w':50})]),vehicle()]
        result=engine.first_boardable(rows,fleet,0,0,leg(),1,[])
        self.assertEqual((result[0],result[1]),(300,2))
        fleet[0]['onboard']=[(0,{'w':50})]
        self.assertEqual(engine.first_boardable(rows,fleet,0,0,leg(),1,[])[0],100)
    def test_eligibility_direction_and_pool(self):
        rows=[(100.,0,0)];self.assertEqual(engine.first_boardable(rows,[vehicle()],0,0,leg(),1,[waiter(100,'B')])[0],100)
        pool={**leg(),'pool':[leg(),leg('B')]};self.assertEqual(engine.first_boardable(rows,[vehicle('B')],0,0,pool,1,[])[3]['rid'],'B')
        self.assertIsNone(engine.first_boardable(rows,[vehicle()],0,0,leg(board=1,alight=2),1,[]))
    def test_vehicle_periods_use_terminal_dispatch_and_batch_boundaries(self):
        info={'capacity':44,'capacity_periods':[{'start_second':75600,'capacity':60}],
              'dispatch_batches':[{'start_second':54000,'end_second':68400,'vehicles':2}]}
        self.assertEqual(capacity_at_clock(info,75599),44);self.assertEqual(capacity_at_clock(info,75600),60)
        self.assertEqual([batch_size_at_clock(info,t) for t in (53999,54000,68399,68400)],[1,2,2,1])
    def test_batch_has_two_vehicles_and_separate_boarding_and_departure(self):
        fleet=[Vehicle('first',60,44,0,0,2,30),Vehicle('second',60,44,0,0,2,30)]
        out=simulate_batch(fleet,[(i,0,0) for i in range(67)],'fill_first')
        person=out['passengers'][-1];self.assertEqual(person['vehicle'],'second')
        self.assertEqual(person['boarding_at'],60+23*2);self.assertEqual(person['post_boarding_seconds'],30)
        self.assertEqual(sum(p['vehicle']=='first' for p in out['passengers']),44)
        self.assertEqual(sum(p['vehicle']=='second' for p in out['passengers']),23)
    def test_boarding_process_not_replaced_with_88_seat_instant_bus(self):
        fleet=[Vehicle('first',60,44,10,0,2,30),Vehicle('second',60,44,10,0,2,30)]
        out=simulate_batch(fleet,[(i,0,0) for i in range(75)])
        self.assertEqual(sum(p['censored'] for p in out['passengers']),7)

class IntegrationTests(unittest.TestCase):
    def run_case(self,bundle):
        with tempfile.TemporaryDirectory() as folder:
            engine.WORK=Path(folder)
            with contextlib.redirect_stdout(io.StringIO()):data=engine.simulate(bundle,'월','regular')
            audit=read(Path(folder)/'audit-regular-mon.json.gz')
        return data,audit
    def test_shared_capacity_fifo_and_residual(self):
        data,audit=self.run_case(fixture([('A',75,100)]))
        self.assertEqual([e[6] for e in audit['events']],[50,25]);self.assertEqual([e[8] for e in audit['events']],[25,0])
        self.assertEqual(data['report']['final_weight'],75)
        self.assertEqual([w['id'] for w in audit['wait_audit'] if w['outcome']=='boarded'],[1,1])
    def test_two_same_time_buses_finish_before_reconsideration(self):
        cfg={'behavior':'sequential','arrival_review_probability':0,'review_base_rate_per_second':0,
             'review_age_stress_rate_per_second':0,'review_full_stress_rate_per_second':0}
        b=fixture([('A',75,100)],cfg);b['supply']['regular']['A']=[START+100,START+100]
        b['alternatives']['0|snu']=[{'kind':'walk','name':'walk','walk':[0,600.],'walk_meters':500.,'stages':[]}]
        def pick(candidates,*args):return next((c for c in candidates if c.get('option')),candidates[0] if candidates else None)
        with patch('policy.choose',side_effect=pick):data,audit=self.run_case(b)
        self.assertEqual([r['end'] for r in audit['wait_audit']],[START+100,START+100])
        self.assertEqual(data['report']['final_weight'],75);self.assertEqual(audit['behavior_decisions'],[])
    def test_full_service_triggers_real_alternative_choice_without_time_cutoff(self):
        cfg={'behavior':'sequential','arrival_review_probability':0,'review_base_rate_per_second':0,
             'review_age_stress_rate_per_second':0,'review_full_stress_rate_per_second':0}
        b=fixture([('A',75,100)],cfg);b['supply']['regular']['A']=[START+100]
        b['alternatives']['0|snu']=[{'kind':'walk','name':'walk','walk':[0,600.],'walk_meters':500.,'stages':[]}]
        def pick(candidates,*args):return next((c for c in candidates if c.get('option')),candidates[0] if candidates else None)
        with patch('policy.choose',side_effect=pick):data,audit=self.run_case(b)
        changed=next(r for r in audit['wait_audit'] if r['outcome']=='switched')
        self.assertAlmostEqual(changed['end'],START+100.001);self.assertEqual(changed['weight'],25)
        self.assertEqual(audit['behavior_decisions'][0]['reason'],'service_rejected_or_full')
        self.assertFalse(audit['behavior_decisions'][0]['forced']);self.assertEqual(data['report']['final_weight'],75)
    def test_missed_preparation_service_triggers_review_without_changing_ready_clock(self):
        cfg={'behavior':'sequential','arrival_review_probability':0,'review_base_rate_per_second':0,
             'review_age_stress_rate_per_second':0,'review_full_stress_rate_per_second':0}
        b=fixture([('A',10,10)],cfg);b['supply']['regular']['A']=[START+10,START+1300]
        b['alternatives']['0|snu']=[{'kind':'walk','name':'walk','walk':[0,600.],'walk_meters':500.,'stages':[]}]
        def pick(candidates,*args):return next((c for c in candidates if c.get('option')),candidates[0] if candidates else None)
        with patch('policy.choose',side_effect=pick):data,audit=self.run_case(b)
        row=audit['wait_audit'][0]
        self.assertEqual(row['ready_at'],START+21);self.assertAlmostEqual(row['leave_at'],START+21.001)
        self.assertEqual(row['full_passes_seen'],0)
        self.assertEqual(audit['behavior_decisions'][0]['reason'],'service_missed_during_preparation')
        self.assertFalse(audit['behavior_decisions'][0]['forced']);self.assertEqual(data['report']['final_weight'],10)
    def test_preparation_information_does_not_force_change_or_remove_long_wait(self):
        cfg={'behavior':'sequential','arrival_review_probability':0,'review_base_rate_per_second':0,
             'review_age_stress_rate_per_second':0,'review_full_stress_rate_per_second':0}
        b=fixture([('A',10,10)],cfg);b['supply']['regular']['A']=[START+10,START+1300]
        data,audit=self.run_case(b)
        self.assertAlmostEqual(audit['wait_audit'][0]['end']-audit['wait_audit'][0]['arrival'],1299)
        self.assertEqual(audit['behavior_decisions'],[]);self.assertEqual(data['report']['unserved_trip_weight'],0)
    def test_unserved_and_long_waits_are_preserved_without_forcing(self):
        b=fixture([('A',120,100)],{'behavior':'sequential','arrival_review_probability':0,'review_base_rate_per_second':0})
        data,audit=self.run_case(b);self.assertEqual(data['report']['unserved_trip_weight'],20)
        self.assertTrue(any(r['end']-r['arrival']>1200 for r in audit['wait_audit']))
        self.assertTrue(all(not x['forced'] for x in audit['behavior_decisions']))
    def test_preparation_times_remain_separate(self):
        data,audit=self.run_case(fixture([('A',10,100)]))
        row=audit['wait_audit'][0];self.assertEqual(row['ready_at']-row['stop_arrival_at'],20)
        self.assertEqual(row['boarding_at'],row['leave_at']);self.assertGreater(row['boarding_at'],row['ready_at'])
    def test_cancelled_before_ready_keeps_visit_not_ready_entry(self):
        b=fixture([('A',10,100)],{'behavior':'sequential','arrival_review_probability':1})
        b['alternatives']['0|snu']=[{'kind':'walk','name':'walk','walk':[0,600.],'walk_meters':500.,'stages':[]}]
        def pick(candidates,*args):return next((c for c in candidates if c.get('option')),None)
        with patch('policy.choose',side_effect=pick):data,audit=self.run_case(b)
        row=audit['wait_audit'][0];self.assertIsNone(row['ticket']);self.assertLess(row['leave_at'],row['ready_at'])
        self.assertEqual(sum(s['weight'] for s in audit['legs']),10)
        self.assertEqual(data['report']['city_boarding_weight'],0)
    def test_fifo_is_among_compatible_services(self):
        data,audit=self.run_case(fixture([('A',60,100),('B',20,110)]))
        first=audit['events'][0];self.assertEqual((first[6],first[8]),(50,10))
        event=next(e for e in audit['events'] if e[11]=='B');self.assertEqual(event[6],20)

if __name__=='__main__':unittest.main()
