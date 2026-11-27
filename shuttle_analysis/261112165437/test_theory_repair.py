"""Mechanism invariants. These are not field-accuracy tests."""
import unittest
from artifacts import ROOT,read
from preferences import choose,Prediction,traits
from policy import cumulative_wait_discomfort,strategy_taste_key,attach_policy
from fixtures import fixture,leg
class TheoryRepair(unittest.TestCase):
    def setUp(self):self.cfg=read(ROOT/'config.json')
    def test_same_information_does_not_redraw_tastes(self):
        self.cfg['persistent_strategy_utility']=True  # Sensitivity-mode contract, not an estimated default.
        choices=[{'key':'A','cost':10},{'key':'B','cost':11}]
        for uid in range(40):
            expected=choose(choices,uid,('reroute',0),self.cfg)['key']
            self.assertEqual({choose(choices,uid,('reroute',n),self.cfg)['key'] for n in range(100)},{expected})
    def test_execution_label_does_not_change_incumbent_taste(self):
        self.cfg['persistent_strategy_utility']=True
        a=[{'key':'walk_to_A','taste_key':'A','cost':10},{'key':'walk_to_B','taste_key':'B','cost':11}]
        b=[{'key':'stay','taste_key':'A','cost':10},{'key':'walk_to_B','taste_key':'B','cost':11}]
        for uid in range(100):self.assertEqual(choose(a,uid,0,self.cfg)['taste_key'],choose(b,uid,999,self.cfg)['taste_key'])
    def test_cumulative_wait_is_partition_invariant(self):
        g=lambda a,w:cumulative_wait_discomfort(a,w,self.cfg)
        for a in (0.,120.,600.,1000.):
            self.assertAlmostEqual(g(a,1200),g(a,600)+g(a+600,600),places=9)
            self.assertAlmostEqual(g(a,900),g(a,100)+g(a+100,300)+g(a+400,500),places=9)
            self.assertEqual(g(a,0),0.)
    def test_walking_to_another_queue_does_not_erase_wait_burden(self):
        cfg=self.cfg;b=fixture([('A',1,100)],cfg)
        p=attach_policy(b,cfg,None,None,None,None,[],[],[],[],[],[],{},None,None,None,[],[])
        pred=Prediction(1200,wait=600,ride=600,first_wait=600,wait_squared=360000,wait_cubed=216000000)
        state={'traits':traits(1,cfg),'history':[],'stop_entry':0.,'full_passes':0,'completed_wait_seconds':600.}
        state_fresh={**state,'completed_wait_seconds':0.}
        self.assertGreater(p.generalized(pred,state,True),p.generalized(pred,state_fresh,True))
        eta=pred.eta;p.generalized(pred,state);self.assertEqual(pred.eta,eta)
    def test_no_hard_change_limit_and_original_distance_weights(self):
        self.assertIsNone(self.cfg['maximum_route_changes']);self.assertEqual(self.cfg['repeat_multiplier'],.3)
    def test_canonical_strategy_key_ignores_execution_dict_identity(self):
        self.assertEqual(strategy_taste_key([leg()],'snu'),strategy_taste_key([dict(leg())],'snu'))
if __name__=='__main__':unittest.main()
