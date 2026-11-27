"""Source strategy intent, internal access, ambiguity and released switching."""
import copy,unittest
import test_student_strategy as student_fixture
from fixtures import leg
from preferences import Prediction
from behavioral_policy import trunk_modes
from engine import CommittedArrivals

class TrunkPreservation(unittest.TestCase):
    def setup(self):return student_fixture.StudentStrategy().setup()
    def test_internal_access_is_not_commute_shuttle_preference(self):
        c,b,p,s,e=self.setup()
        self.assertEqual(trunk_modes([leg('shuttle-41914'),leg('A')],c),{'city'})
        self.assertEqual(trunk_modes([leg('A'),leg('shuttle-41914')],c),{'city'})
    def test_commute_shuttle_after_city_access_is_shuttle_primary(self):
        c,b,p,s,e=self.setup()
        self.assertEqual(trunk_modes([leg('A'),leg('shuttle-41841')],c),{'shuttle'})
    def test_every_pool_members_own_suffix_defines_the_allowed_set(self):
        c,b,p,s,e=self.setup()
        direct={**leg('A'),'continuation_stages':[]}
        access={**leg('B'),'continuation_stages':[leg('shuttle-41841')]}
        self.assertEqual(trunk_modes([{**direct,'pool':[direct,access]}],c),{'city','shuttle'})
    def test_unreleased_city_intent_filters_unrecorded_shuttle_trunk(self):
        c,b,p,s,e=self.setup();p.student_initialize(s)
        self.assertIsNone(p.student_filter_stages(s,[{**leg('A'),'test_node':1},{**leg('shuttle-41841'),'test_node':2}],False))
        self.assertEqual(s['student_preferred_mode'],'city')
    def test_released_city_intent_can_switch_to_commute_shuttle(self):
        c,b,p,s,e=self.setup();p.student_initialize(s);s['student_flexible']=True
        self.assertIsNotNone(p.student_filter_stages(s,[{**leg('A'),'test_node':1},{**leg('shuttle-41841'),'test_node':2}],False))
    def test_ambiguous_source_retains_both_intents_without_imputing_a_share(self):
        c,b,p,s,e=self.setup()
        direct={**leg('A'),'test_node':1,'continuation_stages':[]}
        access={**leg('B'),'test_node':1,'continuation_stages':[{**leg('shuttle-41841'),'test_node':2}]}
        s['stages']=[{**direct,'pool':[direct,access]}];p.student_initialize(s)
        self.assertEqual(set(s['student_preferred_trunk_modes']),{'city','shuttle'})
        result=p.student_filter_stages(s,s['stages'],False)
        self.assertEqual(trunk_modes(result,c),{'city','shuttle'})
    def test_enroute_boarding_does_not_bypass_unreleased_trunk(self):
        c,b,p,s,e=self.setup();p.student_initialize(s)
        self.assertFalse(p.student_mode_allowed(s,[leg('A'),leg('shuttle-41841')],100.))
        s['student_flexible']=True
        self.assertTrue(p.student_mode_allowed(s,[leg('A'),leg('shuttle-41841')],100.))
    def test_already_ridden_city_is_retained_through_an_internal_suffix(self):
        c,b,p,s,e=self.setup();p.student_initialize(s);s['student_last_main_mode']='city'
        result=p.student_filter_stages(s,[{**leg('shuttle-41914'),'test_node':1}],False)
        self.assertIsNotNone(result)
    def initial(self,enabled):
        c,b,p,s,e=self.setup();c['initial_trunk_preservation']=enabled;c['city_initial_information']='legacy_exact';s['queued']=False
        origin=tuple(b['prepared']['common']['paths'][0][0]);key=repr(('301','snu',origin))
        good=[{**leg('A'),'test_node':1}]
        bad=[{**leg('A'),'test_node':1},{**leg('shuttle-41841'),'test_node':2}]
        b['student_origin_catalog'][key]=[{'key':'direct','walk':[0,30.],'stages':good},{'key':'unrecorded-trunk-change','walk':[0,30.],'stages':bad}]
        p.predict=lambda stages,*a,**kw:Prediction(2000.,first_wait=10. if trunk_modes(stages,c)=={'shuttle'} else 100.)
        p.initial_choice(s,0.)
        return trunk_modes(s['stages'],c),s
    def test_real_initial_choice_preserves_primary_mode_and_does_not_add_a_change(self):
        modes,s=self.initial(True)
        self.assertEqual(modes,{'city'});self.assertEqual(s['history'],[])
        self.assertEqual(s['student_preferred_mode'],'city')
    def test_disabled_boundary_reproduces_legacy_unrecorded_change(self):
        self.assertEqual(self.initial(False)[0],{'shuttle'})
    def test_pending_policy_refresh_preserves_time_mass_and_order(self):
        r=CommittedArrivals(1);state={'sid':7,'node':0,'ready_time':100.,'w':2.}
        r.register(state,leg('A'),10.)
        old=r.forecast(0,20.,200.)[0].copy()
        self.assertTrue(r.update_services(state,leg('B')))
        new=r.forecast(0,20.,200.)[0]
        self.assertEqual(new['services'],(('B',0),))
        self.assertEqual({k:v for k,v in old.items() if k!='services'},{k:v for k,v in new.items() if k!='services'})
    def test_queued_person_is_not_reintroduced_into_pending_forecast(self):
        r=CommittedArrivals(1);state={'sid':7,'node':0,'ready_time':100.,'w':2.}
        r.register(state,leg('A'),10.);r.cancel(7)
        self.assertFalse(r.update_services(state,leg('B')))
        self.assertEqual(r.forecast(0,200.,300.),())
if __name__=='__main__':unittest.main()
