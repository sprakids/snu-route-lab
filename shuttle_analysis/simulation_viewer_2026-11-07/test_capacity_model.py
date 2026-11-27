"""Small analytically solvable FIFO and transfer cases, independent of course inputs."""
import unittest
from unittest.mock import patch
import capacity_model as m

R1='shuttle-41841';R2='shuttle-daehak';T=m.START
def fixture(plans,nodes=None,info=None):
    if nodes is None:nodes=[{'id':R1+'|0','route':R1,'name':'A','lat':37.,'lon':127.}]
    if info is None:info={R1:{'n':2,'offsets':[0.,120.],'segments':[0],'anchor':0}}
    return {'common':{'nodes':nodes,'route_info':info,'hot_nodes':{h:0 for _,_,h in m.HOT}},
            'routes':{},'plans':{'월':plans}}
def stage(rid=R1,board=0,alight=1,walk=0):
    return {'rid':rid,'board':board,'alight':alight,'wait_path':0,'ride_path':0,
            'city_wait':20,'ride_seconds':120,'next_walk':[0,walk]}
def plan(uid,w,stages=None,start=T-30):return [uid,'fixture','snu',w,start,[0,0],stages or [stage()]]
def run(prepared,dispatch):
    audit={}
    def sink(w,e,f):audit.update(waits=w,events=e,finished=f)
    with patch.object(m,'dispatches',side_effect=lambda rid,scenario:dispatch[rid]):
        report,_,_=m.simulate(prepared,'월','regular',False,sink)
    return report,audit

class CapacityCases(unittest.TestCase):
    def test_full_60_then_15_stay_for_next_bus(self):
        r,a=run(fixture([plan(1,75)]),{R1:[T,T+180]})
        first,second=a['events'];self.assertEqual((first[6],first[7],first[8]),(60,60,15))
        self.assertEqual((second[6],second[8]),(15,0))
        late=next(w for w in a['waits'] if w[3]==15)
        self.assertEqual((late[2],late[4]),(T+180,T))
        self.assertEqual(r['input_weight'],r['final_weight'])
    def test_upstream_load_uses_downstream_seats(self):
        nodes=[{'id':R1+'|0'},{'id':R1+'|1'}]
        info={R1:{'n':3,'offsets':[0.,60.,120.],'segments':[0,0],'anchor':0}}
        _,a=run(fixture([plan(1,50,[stage(alight=2)]),plan(2,20,[stage(board=1,alight=2)])],nodes,info),{R1:[T,T+180]})
        row=next(e for e in a['events'] if e[1]==1)
        self.assertEqual((row[4],row[6],row[7],row[8]),(50,10,60,10))
    def test_alight_before_board_frees_seats(self):
        nodes=[{'id':R1+'|0'},{'id':R1+'|1'}]
        info={R1:{'n':3,'offsets':[0.,60.,120.],'segments':[0,0],'anchor':0}}
        _,a=run(fixture([plan(1,50,[stage(alight=1)]),plan(2,60,[stage(board=1,alight=2)])],nodes,info),{R1:[T]})
        row=next(e for e in a['events'] if e[1]==1)
        self.assertEqual((row[5],row[6],row[7],row[8]),(50,60,60,0))
    def test_late_first_ride_delays_transfer(self):
        nodes=[{'id':R1+'|0'},{'id':R2+'|0'}]
        info={rid:{'n':2,'offsets':[0.,120.],'segments':[0],'anchor':0} for rid in (R1,R2)}
        p=plan(1,75,[stage(R1,walk=30),stage(R2)])
        _,a=run(fixture([p],nodes,info),{R1:[T,T+180],R2:[T+180,T+360]})
        final=sorted(a['finished'],key=lambda s:s['w'],reverse=True)
        departures=[[l[1] for l in s['legs'] if l[0]==3] for s in final]
        self.assertEqual(departures,[[T,T+180],[T+180,T+360]])
        for s in final:
            for first,second in zip(s['legs'],s['legs'][1:]):self.assertAlmostEqual(first[2],second[1])
    def test_last_bus_leaves_unserved_queue(self):
        r,a=run(fixture([plan(1,75)]),{R1:[T]})
        self.assertEqual(r['finished_weight'],60);self.assertEqual(r['unserved_trip_weight'],15)
        stranded=next(w for w in a['waits'] if w[5]);self.assertEqual((stranded[2],stranded[3],stranded[4]),(m.END+1,15,T))
    def test_headway_scenarios_keep_service_boundaries(self):
        for scenario in m.SCENARIOS:
            snu=m.dispatches(R1,scenario);window=[t for t in snu if 900*60<=t<1140*60]
            self.assertTrue(all(b-a==m.SCENARIOS[scenario]['snu_peak'] for a,b in zip(window,window[1:])))
            reverse=m.dispatches('shuttle-41914',scenario)
            self.assertEqual((reverse[0],reverse[-1]),(590*60,1030*60))
            self.assertEqual(snu.count(1270*60),2)
if __name__=='__main__':unittest.main()
