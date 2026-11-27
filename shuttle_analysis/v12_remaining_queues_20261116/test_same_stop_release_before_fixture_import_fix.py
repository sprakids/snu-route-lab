"""Same-platform options retain all physical queue and user-rule invariants."""
import copy,unittest
from test_student_strategy import StudentStrategy
from fixtures import leg
from preferences import Prediction

class SameStopRelease(unittest.TestCase):
    def setup(self):
        c,b,p,s,e=StudentStrategy().setup()
        s.update(arrival=0.,entry_eligibility=[('A',0)],queue_ticket=7,used_services=set())
        b['compatible_route_policies']={'0|snu':[{**leg('B'),'test_node':0,'continuation_stages':[]}]}
        p.student_initialize(s)
        p.predict=lambda *a,**kw:Prediction(1000.,first_wait=30.)
        return c,b,p,s,e
    def candidate(self,p,s):
        return next(x for x in p.alternative_choices(s,100.,Prediction(1000.,first_wait=30.)) if x.get('same_stop_pool_update'))
    def test_initial_loyalty_prevents_tactical_expansion(self):
        c,b,p,s,e=self.setup()
        self.assertFalse(any(x.get('same_stop_pool_update') for x in p.alternative_choices(s,100.,Prediction(1000.,first_wait=30.))))
    def test_release_opens_other_legal_service_at_current_platform(self):
        c,b,p,s,e=self.setup();s['student_flexible']=True;x=self.candidate(p,s)
        self.assertEqual({r['rid'] for r in x['replacement_stages'][0]['pool']},{'A','B'})
    def test_pool_selection_preserves_ticket_wait_denials_and_history(self):
        c,b,p,s,e=self.setup();s['student_flexible']=True;s['full_passes']=3
        before=copy.deepcopy({k:s[k] for k in ['arrival','ready_time','stop_entry','queue_ticket','full_passes','history','visited','w']})
        self.assertFalse(p.commit_switch(s,100.,'test',self.candidate(p,s)))
        self.assertEqual(before,{k:s[k] for k in before})
        self.assertEqual(s['eligibility_periods'][0]['from'],0.)
        self.assertEqual(s['eligibility_periods'][1]['from'],100.)
        self.assertTrue(s['queued']);self.assertEqual(e,[])
    def test_used_service_is_not_reintroduced(self):
        c,b,p,s,e=self.setup();s['student_flexible']=True;s['used_services']={('B',0)}
        self.assertFalse(any(x.get('same_stop_pool_update') for x in p.alternative_choices(s,100.,Prediction(1000.,first_wait=30.))))
    def test_wrong_direction_final_service_is_not_reintroduced(self):
        c,b,p,s,e=self.setup();s['student_flexible']=True
        c['terminal_direction_requirements']={'snu':{'B':['home']}}
        b['prepared']['routes']['B']={'stops':[{'direction':'away'}]}
        self.assertFalse(any(x.get('same_stop_pool_update') for x in p.alternative_choices(s,100.,Prediction(1000.,first_wait=30.))))
    def test_return_in_continuation_is_not_reintroduced(self):
        c,b,p,s,e=self.setup();s['student_flexible']=True;s['visited']={2}
        b['compatible_route_policies']['0|snu'][0]['continuation_stages']=[{**leg('C'),'test_node':2}]
        self.assertFalse(any(x.get('same_stop_pool_update') for x in p.alternative_choices(s,100.,Prediction(1000.,first_wait=30.))))
    def test_option_does_not_expand_just_because_it_exists(self):
        c,b,p,s,e=self.setup();s['student_flexible']=True;before=copy.deepcopy(s['stages'])
        self.candidate(p,s);self.assertEqual(before,s['stages'])
    def test_one_tactical_choice_per_platform_despite_extra_route_listings(self):
        c,b,p,s,e=self.setup();s['student_flexible']=True
        b['compatible_route_policies']['0|snu'].extend([{**leg('C'),'test_node':0,'continuation_stages':[]},copy.deepcopy(b['compatible_route_policies']['0|snu'][0])])
        self.assertEqual(sum(bool(x.get('same_stop_pool_update')) for x in p.alternative_choices(s,100.,Prediction(1000.,first_wait=30.))),1)
    def test_disabled_mechanism_preserves_parent_choices(self):
        c,b,p,s,e=self.setup();s['student_flexible']=True;c['same_stop_flexible_pool_choice']=False
        self.assertEqual([x['key'] for x in p.alternative_choices(s,100.,Prediction(1000.,first_wait=30.))],['stay'])
if __name__=='__main__':unittest.main()
