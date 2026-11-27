"""Known policy coverage and unambiguous same-service continuation selection."""
import copy,unittest
from fixtures import leg
from direct_restoration import known_direct_registry,append_origin_options,same_service_direct_policy
from engine import stage_choice
from preferences import Prediction
import test_student_strategy as fixtures

class DirectRestoration(unittest.TestCase):
    def bundle(self):
        direct={**leg('A'),'alight':2,'test_node':0,'continuation_stages':[]}
        via={**leg('A'),'alight':1,'test_node':0,'continuation_stages':[{**leg('shuttle-41841'),'test_node':1}]}
        b={'compatible_route_policies':{'0|snu':[via]},'compatible_single_stage_pools':{'0|snu':[direct]},
           'physical_paths':[{'seconds':30.}], 'prepared':{'plans':{'월':[[1,'301','snu',1.]]}}}
        return b,direct,via
    def test_restore_direct_instead_of_overwriting_transfer_policy(self):
        b,direct,via=self.bundle();registry,report=known_direct_registry(b,lambda e:e['test_node'])
        self.assertEqual(registry['0|snu'][0]['alight'],2)
        self.assertEqual(registry['0|snu'][0]['continuation_stages'],[])
        self.assertEqual(b['compatible_route_policies']['0|snu'],[via])
        self.assertEqual(report['restored_count'],1)
    def test_registry_does_not_mutate_any_original_bundle_field(self):
        b,direct,via=self.bundle();before=copy.deepcopy(b)
        known_direct_registry(b,lambda e:e['test_node']);self.assertEqual(b,before)
    def test_existing_direct_with_other_final_walk_id_is_not_another_service(self):
        b,direct,via=self.bundle();old=copy.deepcopy(direct);old['next_walk'][0]=99
        b['compatible_route_policies']['0|snu'].append(old)
        registry,report=known_direct_registry(b,lambda e:e['test_node'])
        self.assertEqual(registry,{});self.assertEqual(report['restored_count'],0)
    def test_duplicate_single_stage_service_is_only_recovered_once(self):
        b,direct,via=self.bundle();b['compatible_single_stage_pools']['0|snu']*=2
        registry,report=known_direct_registry(b,lambda e:e['test_node'])
        self.assertEqual(len(registry['0|snu']),1)
    def test_other_destinations_are_not_changed(self):
        b,direct,via=self.bundle();b['compatible_single_stage_pools']['0|nak']=[direct]
        registry,report=known_direct_registry(b,lambda e:e['test_node'])
        self.assertNotIn('0|nak',registry)
    def test_platform_mismatch_is_rejected(self):
        b,direct,via=self.bundle()
        with self.assertRaises(AssertionError):known_direct_registry(b,lambda e:9)
    def test_origin_reuses_walk_and_preserves_all_existing_options(self):
        b,direct,via=self.bundle();b['restored_direct_policies']=known_direct_registry(b,lambda e:0)[0]
        target={'old':{'walk':[0,30.],'stages':[via],'key':'old'}};before=copy.deepcopy(target)
        self.assertEqual(append_origin_options(target,0,0,b),1)
        self.assertEqual(target['old'],before['old']);self.assertEqual(len(target),2)
        new=next(v for k,v in target.items() if k!='old')
        self.assertEqual(new['walk'],[0,30.]);self.assertEqual(new['stages'][0]['continuation_stages'],[])
    def test_origin_append_is_idempotent(self):
        b,direct,via=self.bundle();b['restored_direct_policies']=known_direct_registry(b,lambda e:0)[0];target={}
        append_origin_options(target,0,0,b);before=copy.deepcopy(target)
        self.assertEqual(append_origin_options(target,0,0,b),0);self.assertEqual(target,before)
    def test_same_service_replaces_alighting_policy_without_shadowed_duplicate(self):
        b,direct,via=self.bundle();out=same_service_direct_policy([via],direct)
        self.assertEqual(len(out[0]['pool']),1);self.assertEqual(stage_choice(out[0],'A',0)['alight'],2)
        self.assertEqual(stage_choice(out[0],'A',0)['continuation_stages'],[])
    def test_new_service_preserves_every_incumbent(self):
        b,direct,via=self.bundle();extra={**leg('B'),'test_node':0}
        out=same_service_direct_policy([extra],direct)
        self.assertEqual({(e['rid'],e['board']) for e in out[0]['pool']},{('A',0),('B',0)})
    def test_identical_policy_is_not_another_random_alternative(self):
        b,direct,via=self.bundle();self.assertIsNone(same_service_direct_policy([direct],direct))
    def test_replacement_inputs_are_immutable(self):
        b,direct,via=self.bundle();before=copy.deepcopy((direct,via));same_service_direct_policy([via],direct)
        self.assertEqual((direct,via),before)
    def test_ambiguous_incumbent_is_rejected(self):
        b,direct,via=self.bundle()
        with self.assertRaises(ValueError):same_service_direct_policy([{**via,'pool':[via,direct]}],direct)
    def test_early_commitment_still_blocks_same_stop_change(self):
        c,b,p,s,ev=fixtures.StudentStrategy().setup()
        s.update(arrival=0.,entry_eligibility=[('A',0)],queue_ticket=7,used_services=set())
        p.student_initialize(s);b['restored_direct_policies']={'0|snu':[{**leg('A'),'alight':2,'test_node':0,'continuation_stages':[]}]}
        p.predict=lambda *a,**k:Prediction(500.,first_wait=100.)
        choices=p.alternative_choices(s,50.,Prediction(500.,first_wait=100.))
        self.assertEqual([x['key'] for x in choices],['stay']);self.assertFalse(s['student_flexible'])
    def test_actual_same_stop_update_retains_fifo_wait_denials_and_change_history(self):
        c,b,p,s,ev=fixtures.StudentStrategy().setup();c['restore_known_snu_direct_policies']=True
        s.update(arrival=0.,entry_eligibility=[('A',0)],queue_ticket=7,used_services=set())
        p.student_initialize(s);s['student_flexible']=True
        b['restored_direct_policies']={'0|snu':[{**leg('A'),'alight':2,'test_node':0,'continuation_stages':[]}]}
        def predict(chain,at,*args,**kwargs):
            direct=stage_choice(chain[0],'A',0)['alight']==2
            return Prediction(at+1400.+(100. if direct else 700.),wait=1400.,ride=100. if direct else 700.,first_wait=1400.)
        p.predict=predict
        choices=p.alternative_choices(s,100.,predict(s['stages'],100.))
        selected=next(x for x in choices if x.get('same_stop_pool_update'))
        keys=['arrival','ready_time','stop_entry','queue_ticket','full_passes','history','visited','w']
        before=copy.deepcopy({k:s[k] for k in keys})
        self.assertFalse(p.commit_switch(s,100.,'test',selected))
        self.assertEqual({k:s[k] for k in keys},before);self.assertEqual(ev,[])
        self.assertEqual(stage_choice(s['stages'][0],'A',0)['alight'],2)
        self.assertEqual(s['eligibility_periods'][-1]['services'],[('A',0)])

if __name__=='__main__':unittest.main()
