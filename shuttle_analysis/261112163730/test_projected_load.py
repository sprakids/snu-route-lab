"""Same FIFO seat accounting for time and fallback crowding, not field validation."""
import unittest
from artifacts import ROOT,read
from fixtures import fixture,leg,vehicle,waiter
from fares import FareLedger
from preferences import traits
from policy import attach_policy
import engine
class ProjectedLoad(unittest.TestCase):
    def test_forty_known_ahead_in44seat_bus_are_not_empty_future(self):
        v=vehicle(cap=44);v['times']=[100.,160.];args=([(100.,0,0)],[v],20,20,leg(),1,[waiter(40)])
        old=engine.first_boardable(*args,indivisible=True)
        new=engine.first_boardable(*args,indivisible=True,project_load=True)
        self.assertEqual(old,new[:4]);self.assertEqual(new[4]['free_after_known_ahead'],4)
        self.assertEqual(new[4]['projected_after_self'],41)
    def test_indexed_and_list_projections_agree(self):
        v=vehicle(cap=44);v['times']=[100.,160.];rows=[(100.,0,0)]
        cache={'types':[{'indices':[0],'prefix':[0.,40.]}],'type_at':[0],'services':{('A',0):[0]}}
        left=engine.first_boardable(rows,[v],20,20,leg(),1,[waiter(40)],indivisible=True,project_load=True)
        right=engine.first_boardable(rows,[v],20,20,leg(),1,engine.QueueView(cache,0),indivisible=True,project_load=True)
        self.assertEqual(left,right)
    def test_second_same_time_bus_receives_only_residual_ahead(self):
        fleet=[{**vehicle(cap=44),'id':i,'times':[100.,160.]} for i in range(2)]
        result=engine.first_boardable([(100.,0,0),(100.,1,0)],fleet,20,20,leg(),1,[waiter(67)],indivisible=True,project_load=True)
        self.assertEqual(result[:3],(100.,1,0));self.assertEqual(result[4]['projected_after_self'],24)
        self.assertEqual([v['onboard'] for v in fleet],[[],[]])
    def test_existing_onboard_and_ahead_conserve_capacity(self):
        v=vehicle(cap=44,onboard=[(1,{'w':5})]);v['times']=[100.,160.]
        r=engine.first_boardable([(100.,0,0)],[v],20,20,leg(),1,[waiter(10)],indivisible=True,project_load=True)
        self.assertEqual(r[4]['projected_after_self'],16)
        self.assertEqual(r[4]['free_after_known_ahead'],29)
    def test_alighting_before_boarding_is_not_counted_as_retained_load(self):
        v=vehicle(cap=44,onboard=[(0,{'w':40})]);v['times']=[100.,160.]
        r=engine.first_boardable([(100.,0,0)],[v],20,20,leg(),1,[],indivisible=True,project_load=True)
        self.assertEqual(r[4]['projected_after_self'],1)
    def test_past_residual_proxy_is_included_and_labelled_not_observed(self):
        v=vehicle(cap=44);v.update(times=[100.,160.],seat_history={('A',0):[(0.,3.),(10.,3.)]})
        r=engine.first_boardable([(100.,0,0)],[v],20,20,leg(),1,[waiter(1)],indivisible=True,project_load=True)
        self.assertEqual(r[4]['projected_after_self'],43)
        self.assertFalse(r[4]['is_observed_occupancy'])
    def policy_fixture(self,enabled=True,evidence=None):
        cfg=read(ROOT/'config.json');cfg['project_queue_load_for_crowding']=enabled
        b=fixture([('A',1,100)],cfg)
        if evidence:b['empirical_evidence']=evidence
        fleet=[{**vehicle(cap=44),'times':[100.,160.]}]
        p=attach_policy(b,cfg,lambda s:0,lambda s:s['stages'][s['stage']],None,lambda *a:[waiter(40)],
          [[(100.,0,0)]],fleet,[],[],[],[],b['prepared']['common']['route_info'],None,None,None,[],[])
        s={'w':1.,'ready_time':20.,'stop_entry':0.,'full_passes':0,'history':[],'fare_ledger':FareLedger(),
          'traits':traits(1,cfg),'stages':[leg()],'stage':0}
        return p,s,fleet
    def test_policy_fallback_uses_same_projected_load_without_changing_eta(self):
        p,s,fleet=self.policy_fixture();new=p.predict(s['stages'],0.,s)
        p0,s0,_=self.policy_fixture(False);old=p0.predict(s0['stages'],0.,s0)
        self.assertEqual(new.eta,old.eta);self.assertEqual(new.eta,165.)
        self.assertAlmostEqual(new.crowd_exposure,60*(41/44)**2)
        self.assertAlmostEqual(old.crowd_exposure,60*(1/44)**2)
        self.assertEqual(fleet[0]['onboard'],[])
    def test_current_boarding_uses_actual_current_onboard_not_queue_twice(self):
        p,s,fleet=self.policy_fixture();fleet[0]['onboard']=[(1,{'w':40})]
        pred=p.predict(s['stages'],100.,s,keep=True,override=(100.,fleet[0],0,leg()))
        self.assertAlmostEqual(pred.crowd_exposure,60*(41/44)**2)
        self.assertEqual(pred.boarding_load_projections[0]['basis'],'actual_current_simulated_onboard_at_boarding_opportunity')
    def test_empirical_ordinal_cost_is_not_replaced_by_numeric_projection(self):
        class Evidence:
            def context(self,*args):return 30.,{'ordinal_proxy':True}
        p,s,_=self.policy_fixture(evidence=Evidence());pred=p.predict(s['stages'],0.,s)
        self.assertEqual(pred.crowd_exposure,30.)
        self.assertFalse(pred.boarding_load_projections[0]['used_for_fallback_crowding_cost'])
if __name__=='__main__':unittest.main()
