"""Clarified information boundary, physical separation and boarding objective."""
import copy,unittest
from nominal_transfer import NominalTransfers,residual_reference
from behavioral_policy import primary_access_extension
from preferences import Prediction
from fixtures import leg
import test_student_strategy as student_fixture

class NominalTransferTests(unittest.TestCase):
    def network(self):
        vehicles=[{'rid':'A'},{'rid':'B'},{'rid':'C'}]
        schedule=[[(100.+600*j,i,0) for j in range(10)] for i in range(3)]
        stages=[{**leg(rid),'test_node':i} for i,rid in enumerate(['A','B','C'])]
        n=NominalTransfers(schedule,vehicles,lambda e:e['test_node'],{'preparation_seconds':20.})
        return n,stages,schedule,vehicles
    def prediction(self,second=600.):
        interval=second-165.
        return Prediction(second+65.,walk=10.,wait=80.+interval-20.,ride=120.,prep=40.,first_wait=100.,
            wait_squared=100**2+interval**2,wait_cubed=100**3+interval**3,
            boarding_timeline=({'time':100.,'arrival':0.,'preparation_seconds':20.,'node':0,'route':'A','board_index':0},
                               {'time':second,'arrival':165.,'preparation_seconds':20.,'node':1,'route':'B','board_index':0}))
    def test_regular_service_has_half_headway_wait(self):
        self.assertEqual(residual_reference([100.+600*j for j in range(10)],500.),(300.,'hour'))
    def test_unknown_departure_phase_is_not_next_bus_time(self):
        a=residual_reference([100.+600*j for j in range(10)],500.)
        b=residual_reference([400.+600*j for j in range(10)],500.)
        self.assertEqual(a,b)
    def test_bunching_has_residual_penalty_without_new_coefficient(self):
        values=[j*600.+d for j in range(10) for d in [0.,60.]]
        self.assertAlmostEqual(residual_reference(values,500.)[0],246.)
    def test_duplicate_departures_are_one_arrival_opportunity(self):
        self.assertEqual(residual_reference([0.,600.,600.,1200.],500.)[0],300.)
    def test_sparse_hour_uses_calendar_not_exact_next_bus(self):
        self.assertEqual(residual_reference([0.,600.,1200.],10000.),(300.,'calendar_fallback'))
    def test_single_departure_does_not_invent_headway(self):
        with self.assertRaises(ValueError):residual_reference([100.],0.)
    def test_future_wait_uses_headways_and_keeps_current_queue(self):
        n,s,_,_=self.network();p=self.prediction();q=n.outlook(p,s[:2])
        self.assertEqual(q.eta,550.);self.assertEqual(q.wait,380.);self.assertEqual(q.prep,40.)
        self.assertEqual(q.first_wait,100.)
        self.assertEqual(q.wait_squared,100**2+320**2);self.assertEqual(q.wait_cubed,100**3+320**3)
    def test_original_physical_prediction_and_policies_remain_unchanged(self):
        n,s,cal,v=self.network();before=copy.deepcopy((s,cal,v));p=self.prediction();n.outlook(p,s[:2])
        self.assertEqual(p.eta,665.);self.assertEqual((s,cal,v),before)
    def test_unseen_transfer_phase_does_not_change_perceived_cost(self):
        n,s,_,_=self.network()
        a=n.outlook(self.prediction(300.),s[:2]);b=n.outlook(self.prediction(900.),s[:2])
        self.assertEqual((a.eta,a.wait,a.prep),(b.eta,b.wait,b.prep))
    def test_future_occupied_vehicles_cannot_change_headway_reference(self):
        n,s,_,v=self.network();a=n.outlook(self.prediction(),s[:2]);v[1].update(cap=1,onboard=[('ignored',999999)])
        b=n.outlook(self.prediction(),s[:2]);self.assertEqual(a,b)
    def test_primary_boarding_delay_is_included_after_feeder(self):
        n,s,_,_=self.network();p=self.prediction();prefix=primary_access_extension(p,1)
        extension,details=n.primary_extension(p,s[:2],1,prefix)
        self.assertEqual(prefix,65.);self.assertEqual(extension,385.)
        self.assertFalse(details[0]['queue_anticipated']);self.assertFalse(details[0]['capacity_anticipated'])
    def test_direct_first_primary_does_not_get_double_wait(self):
        n,s,_,_=self.network();extension,details=n.primary_extension(self.prediction(),s[:2],0,0.)
        self.assertEqual((extension,details),(0.,()))
    def test_pool_uses_each_selected_members_own_continuation(self):
        n,s,_,_=self.network();wrong={**s[2],'continuation_stages':[]}
        good={**s[0],'continuation_stages':[s[1]]};chain=[{**wrong,'pool':[wrong,good]}]
        self.assertEqual(n.outlook(self.prediction(),chain).eta,550.)
    def test_every_later_queue_has_its_own_nominal_interval(self):
        n,s,_,_=self.network();p=self.prediction()
        row={'time':1000.,'arrival':665.,'preparation_seconds':20.,'node':2,'route':'C','board_index':0}
        p=Prediction(1065.,walk=15.,wait=810.,ride=180.,prep=60.,first_wait=100.,
            wait_squared=100**2+435**2+335**2,wait_cubed=100**3+435**3+335**3,
            boarding_timeline=p.boarding_timeline+(row,))
        q=n.outlook(p,s);self.assertEqual(q.eta,935.);self.assertEqual(q.prep,60.)
        prefix=primary_access_extension(p,1);extension,details=n.primary_extension(p,s,1,prefix)
        self.assertEqual(extension,385.);self.assertEqual(len(details),1)
    def test_policy_uses_new_perception_and_disabled_flag_reproduces_parent(self):
        c,b,p,state,e=student_fixture.StudentStrategy().setup();c['anticipated_transfer_headways']=True
        p.test_fleet[:]=[{'rid':'A'},{'rid':'B'}]
        p.test_schedule[:]=[[(100.+600*j,i,0) for j in range(10)] for i in range(2)]
        chain=[{**leg(r),'test_node':i} for i,r in enumerate(['A','B'])]
        physical=self.prediction();p.predict=lambda *a,**kw:physical
        self.assertEqual(p.decision_predict(chain,0.,state).eta,550.)
        c['anticipated_transfer_headways']=False
        self.assertEqual(p.decision_predict(chain,0.,state).eta,230.)
        self.assertIs(p.predict(chain,0.,state),physical)

if __name__=='__main__':unittest.main()
