"""User-shaped primary-stop planning without future transfer-wait anticipation."""
import copy,unittest
from unittest.mock import patch
import test_student_strategy as student_fixture
from fixtures import leg
from preferences import Prediction,choose as real_choose
from behavioral_policy import primary_access_extension,split_primary_stops

class PrimaryStop(unittest.TestCase):
    def test_direct_boarding_score_has_no_added_access(self):
        p=Prediction(200.,first_wait=100.,boarding_timeline=({'time':100.,'arrival':0.,'node':1},))
        self.assertEqual(primary_access_extension(p,1),0.)
    def test_transfer_wait_does_not_enter_access_score(self):
        for wait in [30.,600.,3600.]:
            p=Prediction(1000.+wait,first_wait=100.,boarding_timeline=({'time':100.,'arrival':0.,'node':0},{'time':400.+wait,'arrival':400.,'node':1}))
            self.assertEqual(primary_access_extension(p,1),300.)
    def test_intermediate_transfer_wait_and_preparation_are_not_anticipated(self):
        p=Prediction(2200.,boarding_timeline=({'time':100.,'arrival':0.,'node':0},{'time':1000.,'arrival':300.,'node':1},{'time':2000.,'arrival':1500.,'node':2}))
        self.assertEqual(primary_access_extension(p,2),700.)
    def test_each_pool_members_own_primary_stop_is_split(self):
        cfg={};nf=lambda e:e['test_node']
        a={**leg('A'),'test_node':0,'continuation_stages':[{**leg('C'),'test_node':2}]}
        b={**leg('B'),'test_node':1,'continuation_stages':[{**leg('D'),'test_node':3}]}
        raw=[{**a,'pool':[a,b]}];before=copy.deepcopy(raw)
        groups=split_primary_stops(raw,'snu',cfg,nf)
        self.assertEqual(set(groups),{2,3});self.assertEqual(raw,before)
        self.assertEqual(groups[2][0]['pool'][0]['rid'],'A');self.assertEqual(groups[3][0]['pool'][0]['rid'],'B')
    def test_internal_suffix_does_not_replace_snu_primary_city_stop(self):
        cfg={};nf=lambda e:e['test_node']
        chain=[{**leg('A'),'test_node':1},{**leg('shuttle-41914'),'test_node':2}]
        self.assertEqual(set(split_primary_stops(chain,'snu',cfg,nf)),{1})
        self.assertEqual(set(split_primary_stops(chain,'dorm_ug',cfg,nf)),{2})
    def test_myopic_suffix_ignores_future_queue_capacity_but_normal_review_does_not(self):
        c,b,p,s,e=student_fixture.StudentStrategy().setup()
        p.test_fleet[:]=[{'id':0,'rid':'A','last_stop':-1,'cap':50,'onboard':[],'times':[100.,160.]},
                         {'id':1,'rid':'B','last_stop':-1,'cap':50,'onboard':[(1,{'w':50})],'times':[300.,360.]},
                         {'id':2,'rid':'B','last_stop':-1,'cap':50,'onboard':[],'times':[600.,660.]}]
        p.test_schedule[:]=[[(100.,0,0)],[(300.,1,0),(600.,2,0)]]
        b['prepared']['common']['route_info']['B']=copy.deepcopy(b['prepared']['common']['route_info']['A'])
        b['prepared']['routes']['B']=copy.deepcopy(b['prepared']['routes']['A']);b['prepared']['routes']['B']['name']='B'
        chain=[{**leg('A'),'test_node':0},{**leg('B'),'test_node':1}]
        normal=p.predict(chain,0.,s);myopic=p.predict(chain,0.,s,initial_myopic=True)
        self.assertEqual(normal.boarding_timeline[1]['time'],600.)
        self.assertEqual(myopic.boarding_timeline[1]['time'],300.)
        self.assertFalse(myopic.boarding_timeline[1]['transfer_queue_anticipated'])
        self.assertEqual(p.test_fleet[1]['onboard'][0][1]['w'],50)
    def grouped_keys(self,group_primary):
        c,b,p,s,e=student_fixture.StudentStrategy().setup();s['queued']=False;c['city_initial_group_primary_stop']=group_primary
        rows=[('A',0),('B',1),('C',3),('D',4)]
        p.test_fleet[:]=[{'id':i,'rid':rid,'last_stop':-1,'cap':50,'onboard':[],'times':[100.,160.]} for i,(rid,n) in enumerate(rows)]
        p.test_schedule[:]=[[] for _ in range(5)]
        for vid,(rid,node) in enumerate(rows):p.test_schedule[node]=[(100.+j*600,vid,0) for j in range(8)]
        common=b['prepared']['common'];origin=tuple(common['paths'][0][0]);key=repr(('301','snu',origin))
        sources=[]
        for rid,node in [('A',0),('B',1)]:sources.append({'key':rid,'walk':[0,30.],'stages':[{**leg(rid),'test_node':node},{**leg('C'),'test_node':3}]})
        sources.append({'key':'D','walk':[0,30.],'stages':[{**leg('D'),'test_node':4}]});b['student_origin_catalog'][key]=sources
        def predict(chain,at,state,access=0,*args,**kw):
            first=chain[0]['test_node'];target=3 if chain[0]['rid']!='D' else 4
            timeline=[{'time':100.,'arrival':30.,'node':first}]
            if target!=first:timeline.append({'time':400.,'arrival':200.,'node':target})
            return Prediction(1000.,first_wait=70.,boarding_timeline=tuple(timeline))
        p.predict=predict;captured=[]
        def choose(cs,*args,**kw):captured.extend(str(x['key']) for x in cs);return real_choose(cs,*args,**kw)
        with patch('behavioral_policy.choose',side_effect=choose):p.initial_choice(s,0.)
        return set(captured)
    def test_two_access_stops_to_one_primary_stop_receive_one_choice(self):
        self.assertEqual(self.grouped_keys(True),{'3','4'})
        self.assertEqual(self.grouped_keys(False),{'0','1','4'})
if __name__=='__main__':unittest.main()
