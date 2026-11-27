"""Small physical-time/choice-cost integration regressions, not field calibration."""
import math,unittest
from artifacts import ROOT,read
from fixtures import fixture,leg,vehicle
from preferences import traits,cost
from fares import FareLedger
from policy import attach_policy

class PredictionIntegration(unittest.TestCase):
    def setup_policy(self,flag=True):
        cfg=read(ROOT/'config.json');cfg['integrate_future_wait_discomfort']=flag
        b=fixture([('A',.05,100),('B',.05,220)],cfg)
        fleet=[{**vehicle('A'),'id':0,'times':[100.,160.]},{**vehicle('B'),'id':1,'times':[220.,280.]}]
        schedule=[[(100.,0,0),(220.,1,0)]]
        p=attach_policy(b,cfg,lambda s:0,lambda s:s['stages'][s['stage']],None,lambda *a:[],schedule,fleet,
                        [],[],[],[],b['prepared']['common']['route_info'],None,None,None,[],[])
        state={'w':.05,'ready_time':20.,'stop_entry':0.,'full_passes':0,'history':[],'fare_ledger':FareLedger(),
               'traits':traits(1,cfg),'stages':[leg('A'),leg('B')],'stage':0}
        return cfg,p,state,fleet
    def test_predict_passes_preparation_inclusive_wait_cubes_to_cost(self):
        cfg,p,s,fleet=self.setup_policy();pred=p.predict(s['stages'],0.,s)
        self.assertEqual((pred.eta,pred.walk,pred.wait,pred.prep,pred.ride),(285.,10.,115.,40.,120.))
        self.assertEqual(pred.wait_cubed,100.**3+55.**3)
        self.assertEqual(pred.wait_squared,100.**2+55.**2)
        old={**cfg,'integrate_future_wait_discomfort':False}
        plain=cost(pred,s['traits'],0,True,False)+s['traits'].wait*pred.wait_squared/(60*cfg['predicted_queue_curvature_scale_seconds'])
        expected=s['traits'].wait*pred.wait_cubed/(3*60*cfg['waiting_discomfort_age_scale_seconds']**2)
        self.assertAlmostEqual(p.generalized(pred,s,True)-plain,expected)
        self.assertEqual(pred.eta,285.)
    def test_boarding_now_has_no_sunk_first_wait_but_keeps_onward_queue_growth(self):
        cfg,p,s,fleet=self.setup_policy();s['full_passes']=5
        pred=p.predict(s['stages'],100.,s,keep=True,override=(100.,fleet[0],0,leg('A')))
        self.assertEqual(pred.eta,285.);self.assertEqual(pred.first_wait,0.)
        self.assertEqual(pred.wait_cubed,55.**3)
        base=cost(pred,s['traits'],0,False,False)+s['traits'].wait*pred.wait_squared/(60*cfg['predicted_queue_curvature_scale_seconds'])
        expected=s['traits'].wait*55.**3/(3*60*cfg['waiting_discomfort_age_scale_seconds']**2)
        self.assertAlmostEqual(p.generalized(pred,s)-base,expected)
    def test_disabled_flag_retains_R9_cost_on_positive_current_age(self):
        cfg,p,s,fleet=self.setup_policy(False);s['stop_entry']=-90.;s['full_passes']=2
        pred=p.predict(s['stages'],0.,s)
        expected=cost(pred,s['traits'],0,False,False)+s['traits'].wait*pred.wait_squared/(60*cfg['predicted_queue_curvature_scale_seconds'])
        expected+=s['traits'].wait*pred.first_wait/60*(cfg['waiting_discomfort_full_sensitivity']*2+(90/cfg['waiting_discomfort_age_scale_seconds'])**2)
        self.assertAlmostEqual(p.generalized(pred,s),expected)

if __name__=='__main__':unittest.main()
