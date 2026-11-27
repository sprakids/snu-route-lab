"""Additional nonzero-stop/onboard/history scenarios without editing the active candidate."""
from pathlib import Path
import copy,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'261112210916'))
from engine import CommittedArrivals,QueueView,first_boardable
def leg():return {'rid':'A','board':1}
def vehicle(i,at,cap=10.,onboard=None,last_stop=0,history=None):
    return {'id':i,'rid':'A','cap':cap,'times':[0.,at,at+50],'onboard':onboard or [],'last_stop':last_stop,'seat_history':history or {}}
def pending(weight=4.):
    r=CommittedArrivals(1);r.register({'sid':1,'node':0,'w':weight,'ready_time':80.},leg(),10.)
    return r.forecast(0,20.,90.)
class AdditionalTimedCoverage(unittest.TestCase):
    def test_alighting_and_historical_reservation_separate_from_known_people(self):
        v=vehicle(0,100,onboard=[(1,{'w':5.}),(2,{'w':3.})],history={('A',1):[(5.,8.),(15.,6.)]})
        current=[{'w':1.,'stages':[leg()],'stage':0}]
        view=QueueView({'types':[{'indices':[0],'prefix':[0.,1.]}],'services':{('A',1):[0]},'type_at':[0]},0)
        for q in (current,view):
            before=copy.deepcopy(v)
            result=first_boardable([(100.,0,1)],[v],90.,20.,leg(),1.,q,indivisible=True,project_load=True,pending_arrivals=pending())
            self.assertEqual(result[:3],(100.,0,1));p=result[4]
            self.assertEqual(p['known_retained_onboard'],3.);self.assertEqual(p['known_ahead_boarded_here'],5.)
            self.assertEqual(p['unidentified_reserved_capacity'],1.);self.assertEqual(p['projected_after_self'],9.)
            self.assertEqual(p['quota_implied_load_upper_proxy'],10.);self.assertEqual(v,before)
    def test_already_passed_vehicle_cannot_clear_pending_traffic(self):
        fleet=[vehicle(0,100,last_stop=1),vehicle(1,150)]
        result=first_boardable([(100.,0,1),(150.,1,1)],fleet,90.,20.,leg(),1.,[],indivisible=True,project_load=True,pending_arrivals=pending())
        self.assertEqual(result[:3],(150.,1,1));self.assertEqual(result[4]['known_ahead_boarded_here'],4.)
        self.assertEqual(result[4]['projected_after_self'],5.)
    def test_indivisible_person_does_not_accumulate_fractional_seats(self):
        fleet=[vehicle(i,100.+i*50,cap=1.,onboard=[(2,{'w':.4})]) for i in range(2)]
        rows=[(v['times'][1],i,1) for i,v in enumerate(fleet)]
        self.assertIsNone(first_boardable(rows,fleet,90.,20.,leg(),1.,[],indivisible=True,pending_arrivals=pending(.1)))
        divisible=first_boardable(rows,fleet,90.,20.,leg(),1.,[],indivisible=False,pending_arrivals=pending(.1))
        self.assertEqual(divisible[:3],(150.,1,1))
if __name__=='__main__':unittest.main()
