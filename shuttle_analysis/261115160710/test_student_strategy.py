import copy,unittest,math
from artifacts import ROOT,read
from fixtures import fixture,leg
from preferences import Prediction,traits
from fares import FareLedger
from policy import attach_policy
from behavioral_policy import mode_of,personal_patience,terminal_allowed,boarding_score,frustration,complete_signature,remove_redundant

class StudentStrategy(unittest.TestCase):
    def setup(self):
        c=read(ROOT/'config.json');b=fixture([('A',1,100)],c);b['student_origin_catalog']={}
        events=[];fleet=[{'id':i,'rid':'A','last_stop':-1,'cap':50,'onboard':[],'times':[5000.,5060.]} for i in range(3)];schedule=[[(5000.,0,0)]]
        p=attach_policy(b,c,lambda s:s.get('test_node',0),lambda s:s['stages'][s['stage']],None,lambda *a:[],
          schedule,fleet,[[]],[0.],[0.],[0],{},None,None,lambda *a:events.append(a),[],[])
        p.test_schedule=schedule;p.test_fleet=fleet
        s={'plan':[123,'301','snu',1.,0.,[0,1.],[leg()]],'stages':[leg()],'stage':0,'dest':'snu','w':1.,'history':[],
          'visited':set(),'node':0,'stop_entry':0.,'full_passes':0,'ready_time':20.,'done':False,'queued':True,'preparing':False,
          'traits':traits(123,c),'fare_ledger':FareLedger(),'factor':1.,'check_version':0,'review_ordinal':0,'visit':1,'completed_wait_seconds':0.}
        return c,b,p,s,events
    def test_opposite_terminal_direction_is_removed_from_pool(self):
        c,b,p,s,e=self.setup();c['terminal_direction_requirements']={'snu':{'A':['home']}}
        b['prepared']['routes']['A']['stops']=[{'direction':'away'}]
        bad={**leg('A'),'test_node':1};good={**leg('B'),'test_node':2};result=p.student_filter_stages(s,[{**bad,'pool':[bad,good]}],False)
        self.assertEqual([x['rid'] for x in result[0]['pool']],['B'])
    def test_correct_terminal_direction_remains_available(self):
        c,b,p,s,e=self.setup();c['terminal_direction_requirements']={'snu':{'A':['home']}}
        b['prepared']['routes']['A']['stops']=[{'direction':'home'}]
        self.assertIsNotNone(p.student_filter_stages(s,[{**leg('A'),'test_node':1}],False))
    def test_opposite_branch_can_still_make_a_valid_intermediate_transfer(self):
        c,b,p,s,e=self.setup();c['terminal_direction_requirements']={'snu':{'A':['home']}}
        b['prepared']['routes']['A']['stops']=[{'direction':'away'}]
        chain=[{**leg('A'),'test_node':1},{**leg('B'),'test_node':2}]
        self.assertIsNotNone(p.student_filter_stages(s,chain,False))
    def test_unknown_required_terminal_direction_is_not_assumed_correct(self):
        c,b,p,s,e=self.setup();c['terminal_direction_requirements']={'snu':{'A':['home']}}
        b['prepared']['routes']['A']['stops']=[{}]
        self.assertIsNone(p.student_filter_stages(s,[{**leg('A'),'test_node':1}],False))
    def test_patience_is_fixed_per_person_with_heterogeneity(self):
        c=read(ROOT/'config.json');values=[personal_patience(i,'shuttle',c) for i in range(2000)]
        self.assertEqual(values[12],personal_patience(12,'shuttle',c));self.assertLess(min(values),1200);self.assertGreater(max(values),1200)
        self.assertAlmostEqual(sorted(values)[1000],1200,delta=40)
    def test_shuttle_loyalty_until_personal_patience(self):
        c,b,p,s,e=self.setup();s['stages']=[leg('shuttle-X')];p.student_initialize(s);p.predict=lambda *a,**k:Prediction(5000,first_wait=4900)
        limit=s['student_patience_seconds'];s['full_passes']=20
        self.assertFalse(frustration(limit-1,limit,20,20,'shuttle',c));self.assertTrue(frustration(limit,limit,0,0,'shuttle',c))
        self.assertFalse(p.student_mode_allowed(s,[leg('A')],100))
    def test_two_full_buses_and_two_more_are_both_required(self):
        c=read(ROOT/'config.json')
        self.assertFalse(frustration(300,1200,1,5,'city',c));self.assertFalse(frustration(300,1200,2,1,'city',c))
        self.assertTrue(frustration(300,1200,2,2,'city',c))
    def test_long_wait_can_trigger_without_observing_two_buses(self):
        c=read(ROOT/'config.json');self.assertTrue(frustration(1300,1200,0,0,'city',c))
    def test_earliest_stop_includes_access_walk(self):
        near=Prediction(2000,first_wait=100);far=Prediction(1500,first_wait=20)
        self.assertLess(boarding_score(near,30),boarding_score(far,300))
    def test_station_long_terminal_walk_not_restored_by_large_change_count(self):
        c=read(ROOT/'config.json');self.assertFalse(terminal_allowed('snu',2500,c));self.assertTrue(terminal_allowed('snu',500,c))
        self.assertTrue(terminal_allowed('dorm_ug',1500,c))
    def test_no_return_filter_preserves_valid_compatible_service(self):
        c,b,p,s,e=self.setup();s['visited']={2}
        bad={**leg('A'),'test_node':2};good={**leg('B'),'test_node':1}
        result=p.student_filter_stages(s,[{**bad,'pool':[bad,good]}],False)
        self.assertEqual([r['rid'] for r in result[0]['pool']],['B'])
    def test_no_return_applies_to_future_transfer_as_well(self):
        c,b,p,s,e=self.setup();s['visited']={2}
        self.assertIsNone(p.student_filter_stages(s,[{**leg(),'test_node':1},{**leg('B'),'test_node':2}],False))
    def test_intrinsic_chain_cycle_is_rejected(self):
        c,b,p,s,e=self.setup()
        self.assertIsNone(p.student_filter_stages(s,[{**leg(),'test_node':1},{**leg('B'),'test_node':1}],False))
    def test_arriving_again_does_not_bypass_visited_rule(self):
        c,b,p,s,e=self.setup();s['visited']={0};s['queued']=False
        self.assertIsNone(p.student_filter_stages(s,[leg()],True))
    def test_dormitory_has_separate_walk_reconsideration_scale(self):
        c,b,p,s,e=self.setup();c['dorm_walk_patience_factor']=.6;p.student_initialize(s);base=p.student_patience(s);s['dest']='dorm_ug'
        self.assertAlmostEqual(p.student_patience(s),base*.6)
    def test_ready_to_board_compatible_vehicle_is_accepted(self):
        c,b,p,s,e=self.setup();self.assertTrue(p.accept_boarding(s,leg(),{'id':0,'rid':'A'},0,100,1))
    def test_patience_review_is_not_forced_abandonment(self):
        c,b,p,s,e=self.setup();p.student_initialize(s);p.predict=lambda *a,**k:Prediction(500.,first_wait=100.);p.reschedule(s,20)
        self.assertEqual(e[0][2],'recheck');self.assertAlmostEqual(e[0][0],p.student_patience(s))
        self.assertTrue(s['queued']);self.assertEqual(s['history'],[])
    def test_profile_is_not_redrawn_after_copy_and_mode_change(self):
        c,b,p,s,e=self.setup();p.student_initialize(s);before=s['student_patience_seconds'];t=copy.deepcopy(s)
        t['stages']=[leg('shuttle-X')];p.student_initialize(t);self.assertEqual(t['student_patience_seconds'],before)
    def test_filter_does_not_mutate_source_strategy(self):
        c,b,p,s,e=self.setup();chain=[leg()];before=copy.deepcopy(chain);p.student_filter_stages(s,chain)
        self.assertEqual(chain,before)
    def test_transit_option_cannot_hide_a_far_final_station_walk(self):
        c,b,p,s,e=self.setup();b['physical_paths'].append({'meters':2000.,'seconds':1500.,'stairs_meters':0.})
        route={**leg(),'next_walk':[1,1500.]}
        self.assertIsNone(p.student_filter_stages(s,[route],False))
    def test_initial_city_choice_uses_boarding_time_including_walk(self):
        c,b,p,s,e=self.setup();s['queued']=False
        origin=tuple(b['prepared']['common']['paths'][0][0]);key=repr(('301','snu',origin))
        b['student_origin_catalog'][key]=[{'key':'near','walk':[0,30.],'stages':[leg('A')]},{'key':'far','walk':[0,300.],'stages':[leg('A')]}]
        p.predict=lambda stages,at,state,access=0,*args,**kw:Prediction(2000.,first_wait=100. if access==30. else 20.)
        p.initial_choice(s,0.);self.assertEqual(s['plan'][5][1],30.)
    def test_remaining_passes_count_distinct_compatible_vehicles(self):
        c,b,p,s,e=self.setup();s['full_passes']=2;p.test_schedule[0]=[(100.,0,0),(200.,1,0),(300.,2,0)]
        stressed,age,more=p.student_review_context(s,50.,Prediction(500.,first_wait=350.))
        self.assertTrue(stressed);self.assertEqual(more,3)
    def test_expired_patience_with_no_alternative_does_not_delete_or_force(self):
        c,b,p,s,e=self.setup();p.student_initialize(s);p.predict=lambda *args,**kw:Prediction(5000.,first_wait=3000.)
        self.assertFalse(p.maybe_switch(s,2000.,'queue_recheck'));self.assertTrue(s['queued']);self.assertEqual(s['history'],[])
    def test_current_stop_cannot_reappear_in_new_transfer_tail(self):
        c,b,p,s,e=self.setup();s['arrival']=0.
        self.assertIsNone(p.student_filter_stages(s,[{**leg(),'test_node':1},{**leg('B'),'test_node':0}],False))
    def test_forecast_wait_can_exceed_patience_before_elapsed_wait_does(self):
        c,b,p,s,e=self.setup();p.student_initialize(s);limit=s['student_patience_seconds']
        stressed,age,more=p.student_review_context(s,100.,Prediction(5000.,first_wait=limit+1))
        self.assertTrue(stressed);self.assertLess(age,limit)
    def test_invalid_incumbent_is_not_returned_as_boardable(self):
        c,b,p,s,e=self.setup();s['visited']={2}
        bad={**leg(),'continuation_stages':[{**leg('B'),'test_node':2}]}
        self.assertEqual(p.complete_same_stop(s,bad,0)['pool'],[])
    def test_different_transfer_suffixes_are_not_deduplicated_or_dominated(self):
        a={**leg('A'),'continuation_stages':[leg('X')]};b={**leg('A'),'continuation_stages':[leg('Y')]};c={**leg('B'),'continuation_stages':[leg('Z')]}
        narrow=[a];broad=[{**b,'pool':[b,c]}]
        self.assertNotEqual(complete_signature(narrow),complete_signature(broad))
        candidates=[{'key':'fast-X','option':{'walk':[0,1.],'stages':narrow}},{'key':'slow-Y','option':{'walk':[0,1.],'stages':broad}}]
        self.assertEqual(len(remove_redundant(candidates)),2)
    def test_extra_service_does_not_dominate_when_it_must_be_boarded(self):
        a={**leg('A'),'continuation_stages':[leg('X')]};b={**leg('B'),'continuation_stages':[leg('Y')]}
        candidates=[{'key':'narrow','option':{'walk':[0,1.],'stages':[a]}},{'key':'broad','option':{'walk':[0,1.],'stages':[{**a,'pool':[a,b]}]}}]
        self.assertEqual([c['key'] for c in remove_redundant(candidates)],['narrow','broad'])
    def test_fast_late_bus_is_not_pruned_by_slow_early_bus_pool(self):
        a=leg('A');b=leg('B')
        candidates=[{'key':'A-only','cost':6.,'option':{'walk':[0,1.],'stages':[a]}},
          {'key':'A-or-B','cost':31.,'option':{'walk':[0,1.],'stages':[{**a,'pool':[a,b]}]}}]
        self.assertEqual([c['key'] for c in remove_redundant(candidates)],['A-only','A-or-B'])
    def test_identical_policy_is_deduplicated_at_lowest_cost(self):
        o={'walk':[0,1.],'stages':[leg('A')]}
        result=remove_redundant([{'key':'bad','cost':10.,'option':o},{'key':'good','cost':5.,'option':copy.deepcopy(o)}])
        self.assertEqual([r['key'] for r in result],['good'])
    def test_locked_policy_is_not_silently_expanded(self):
        c,b,p,s,e=self.setup();b['compatible_route_policies']={'0|snu':[leg('B')]}
        locked={**leg('A'),'pool':[leg('A')],'choice_pool_locked':True}
        self.assertEqual({e['rid'] for e in p.complete_same_stop(s,locked,0)['pool']},{'A'})
    def test_locked_route_pool_is_honored_by_actual_engine(self):
        import contextlib,io,tempfile
        from pathlib import Path
        from unittest.mock import patch
        import engine
        from artifacts import START
        c=read(ROOT/'config.json');c.update(behavior='sequential',origin_choice=True,operations='baseline',boarding_choice=True)
        b=fixture([('A',1.,300.),('B',.1,200.)],c);plan=b['prepared']['plans']['월'][0]
        plan[5][1]=83.25;plan[6][0]['choice_pool_locked']=True
        b['prepared']['plans']['월']=[plan];b['source_parent_mass']={'1':1.};b['parent_ids']={'1':1};b['walk_scales']={'1':1.};b['destination_keys']={'1':'snu'}
        b['student_origin_catalog']={};b['compatible_route_policies']={'0|snu':[leg('A'),leg('B')]}
        with tempfile.TemporaryDirectory() as folder,patch.object(engine,'WORK',Path(folder)),contextlib.redirect_stdout(io.StringIO()):
            engine.simulate(b,'월','regular');audit=read(Path(folder)/'audit-regular-mon.json.gz')
        boarded=[e for e in audit['events'] if e[6]>0]
        self.assertTrue(boarded);self.assertEqual({e[11] for e in boarded},{'A'})
    def test_last_gate_does_not_offer_a_trip_back_into_campus(self):
        c,b,p,s,e=self.setup();c['gate_fallback_node']=0;p.student_initialize(s)
        alternatives=p.alternative_choices(s,3000.,Prediction(4000.,first_wait=1000.))
        self.assertEqual([x['key'] for x in alternatives],['stay'])
    def test_last_gate_accepts_all_declared_destination_services(self):
        c,b,p,s,e=self.setup();c['gate_fallback_node']=0;b['compatible_route_policies']={'0|snu':[leg('A'),leg('B')]}
        locked={**leg('A'),'pool':[leg('A')],'choice_pool_locked':True}
        self.assertEqual({x['rid'] for x in p.complete_same_stop(s,locked,0)['pool']},{'A','B'})
    def test_last_gate_wait_is_not_a_forced_teleport_or_loss(self):
        c,b,p,s,e=self.setup();c['gate_fallback_node']=0
        self.assertFalse(p.maybe_switch(s,10000.,'queue_recheck'));self.assertTrue(s['queued']);self.assertEqual(s['history'],[])
    def test_processed_current_time_bus_is_not_an_additional_future_pass(self):
        c,b,p,s,e=self.setup();s['full_passes']=2;p.test_schedule[0]=[(100.,0,0),(160.,1,0),(220.,2,0)];p.test_fleet[0]['last_stop']=0
        stressed,age,more=p.student_review_context(s,100.,Prediction(500.,first_wait=120.))
        self.assertEqual(more,1);self.assertFalse(stressed)
    def test_unprocessed_same_time_bus_still_is_a_future_opportunity(self):
        c,b,p,s,e=self.setup();s['full_passes']=2;p.test_schedule[0]=[(100.,0,0),(160.,1,0),(220.,2,0)]
        stressed,age,more=p.student_review_context(s,100.,Prediction(500.,first_wait=120.))
        self.assertEqual(more,2);self.assertTrue(stressed)
    def test_current_processing_bus_is_not_counted_twice(self):
        c,b,p,s,e=self.setup();s['full_passes']=2;p.test_schedule[0]=[(100.,0,0),(160.,1,0),(220.,2,0)];p.test_fleet[0]['processing_stop']=0
        self.assertEqual(p.student_review_context(s,100.,Prediction(500.,first_wait=120.))[2],1)
    def test_destination_is_part_of_feasibility_cache_key(self):
        c,b,p,s,e=self.setup();b['physical_paths'].append({'meters':2000.,'seconds':1500.,'stairs_meters':0.})
        chain=[{**leg(),'test_node':1,'next_walk':[1,1500.]}];s['dest']='dorm_ug';self.assertIsNotNone(p.student_filter_stages(s,chain,False))
        s['dest']='snu';self.assertIsNone(p.student_filter_stages(s,chain,False))

if __name__=='__main__':unittest.main()
