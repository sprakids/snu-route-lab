"""Perceived routing costs must never masquerade as physical trip forecasts."""
import unittest,copy
import test_student_strategy as student_fixture
from fixtures import leg
from policy import attach_policy
from preferences import Prediction

class ReviewPerception(unittest.TestCase):
    def setup(self):
        c,b,p,s,e=student_fixture.StudentStrategy().setup()
        s.update(arrival=0.,entry_eligibility=[('A',0)],used_services=set())
        return c,b,p,s,e
    def example(self):
        # 100s first wait incl20prep; 60ride+5walk; then435s incl20prep;
        # another60ride+5walk. Physical ETA665, perceived ETA230.
        return Prediction(665.,walk=10.,wait=495.,ride=120.,prep=40.,first_wait=100.,
            wait_squared=100**2+435**2,wait_cubed=100**3+435**3,
            boarding_timeline=({'time':100.,'arrival':0.,'preparation_seconds':20.,'node':0},
                               {'time':600.,'arrival':165.,'preparation_seconds':20.,'node':1}))
    def test_decision_cost_omits_only_unseen_transfer_wait(self):
        c,b,p,s,e=self.setup();original=self.example();p.predict=lambda *args,**kw:original
        perceived=p.decision_predict([],0.,s)
        self.assertEqual(perceived.eta,230.);self.assertEqual(perceived.wait,80.);self.assertEqual(perceived.prep,20.)
        self.assertEqual(original.eta,665.);self.assertEqual(s['completed_wait_seconds'],0.)
    def test_disabled_flag_keeps_the_full_forecast(self):
        c,b,p,s,e=self.setup();c['myopic_transfer_review']=False;original=self.example();p.predict=lambda *a,**kw:original
        self.assertIs(p.decision_predict([],0.,s),original)
    def test_unknown_operational_suffix_does_not_remove_perceived_feasible_option(self):
        c,b,p,s,e=self.setup();p.student_initialize(s);s['student_flexible']=True
        b['alternatives']['0|snu']=[{'kind':'transit','name':'access then main','walk':[0,30.],'walk_meters':111.,
            'stages':[{**leg('A'),'test_node':1},{**leg('B'),'test_node':2}]}]
        calls=[]
        def predict(*args,**kw):
            calls.append(kw.get('initial_myopic',False))
            return self.example() if kw.get('initial_myopic') else None
        p.predict=predict
        cs=p.alternative_choices(s,0.,None)
        self.assertEqual(len(cs),1);self.assertEqual(cs[0]['prediction'].eta,230.)
        self.assertTrue(calls and all(calls))
    def test_committed_move_keeps_unknown_physical_eta_separate_from_perception(self):
        c,b,_,s,e=self.setup();s['queued']=False;decisions=[];behavior=[];walks=[]
        p=attach_policy(b,c,lambda x:x.get('test_node',0),lambda x:x['stages'][x['stage']],None,lambda *a:[],
            [[],[]],[],[[],[]],[0.,0.],[0.,0.],[0,0],{},lambda *a:walks.append(a),lambda *a:None,lambda *a:None,decisions,behavior)
        p.student_initialize(s);s['student_flexible']=True;p.predict=lambda *a,**kw:None
        option={'kind':'transit','name':'access','walk':[0,30.],'stages':[{**leg('A'),'test_node':1}]}
        selected={'key':'new','cost':10.,'prediction':self.example(),'option':option}
        self.assertTrue(p.commit_switch(s,100.,'test',selected,None))
        self.assertIsNone(behavior[0]['new_eta']);self.assertIsNone(behavior[0]['physical_prediction'])
        self.assertEqual(behavior[0]['perceived_prediction']['eta'],665.)
        self.assertIsNone(decisions[0][8]);self.assertEqual(walks[0][3],30.)
if __name__=='__main__':unittest.main()
