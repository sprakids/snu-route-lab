"""A waiting-utility sensitivity must preserve physical time and review logic."""
import copy
import unittest
from artifacts import ROOT, read
from fixtures import fixture
from hazard import integrated
from policy import attach_policy, cumulative_wait_discomfort
from preferences import Prediction, cost, traits

class LinearWaitSensitivity(unittest.TestCase):
    def setup(self):
        cfg=read(ROOT/'config.json')
        bundle=fixture([('A',1,100)],cfg)
        p=attach_policy(bundle,cfg,None,None,None,None,[],[],[],[],[],[],{},None,None,None,[],[])
        state={'traits':traits(17,cfg),'history':[],'stop_entry':0.,'full_passes':0,'completed_wait_seconds':900.}
        pred=Prediction(1600.,wait=280.,prep=20.,ride=300.,first_wait=300.,wait_squared=90000.,wait_cubed=27000000.)
        return cfg,p,state,pred

    def test_linear_component_retains_all_existing_mode_costs(self):
        cfg,p,s,pred=self.setup()
        self.assertEqual(p.generalized(pred,s,True),cost(pred,s['traits'],0,True,cfg['fare_in_choice']))

    def test_elapsed_time_does_not_multiply_prospective_cost(self):
        cfg,p,s,pred=self.setup()
        fresh={**s,'stop_entry':1000.,'completed_wait_seconds':0.}
        self.assertEqual(p.generalized(pred,s,True),p.generalized(pred,fresh,True))
        self.assertEqual(p.generalized(pred,s),p.generalized(pred,fresh))

    def test_denied_boarding_cost_is_retained_for_incumbent_only(self):
        cfg,p,s,pred=self.setup()
        full={**s,'full_passes':3}
        self.assertAlmostEqual(p.generalized(pred,full)-p.generalized(pred,s),
            s['traits'].wait*cfg['waiting_discomfort_full_sensitivity']*3*pred.first_wait/60)
        self.assertEqual(p.generalized(pred,full,True),p.generalized(pred,s,True))

    def test_decision_utility_never_changes_elapsed_or_future_physical_time(self):
        cfg,p,s,pred=self.setup();original=copy.deepcopy(s);components=pred.components()
        for changing in [False,True]:p.generalized(pred,s,changing)
        self.assertEqual(s,original);self.assertEqual(pred.components(),components)

    def test_disabling_student_wrapper_preserves_old_polynomial(self):
        cfg,p,s,pred=self.setup();cfg['student_strategy']=False
        a=s['completed_wait_seconds']+1000.
        expected=cost(pred,s['traits'])+s['traits'].wait*cumulative_wait_discomfort(a,300.,cfg)/60
        self.assertAlmostEqual(p.generalized(pred,s),expected)

    def test_age_and_denial_still_raise_reconsideration_rate(self):
        cfg,p,s,pred=self.setup()
        fresh=integrated(0.,60.,0,0,1.,cfg)
        self.assertGreater(integrated(1200.,1260.,0,0,1.,cfg),fresh)
        self.assertGreater(integrated(0.,60.,0,2,1.,cfg),fresh)
        self.assertIsNone(cfg['maximum_route_changes'])

if __name__=='__main__':unittest.main()
