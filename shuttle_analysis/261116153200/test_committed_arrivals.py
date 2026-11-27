"""Causal information, FIFO/time feasibility, and weighted multi-service forecast."""
import copy,random,unittest
from engine import CommittedArrivals,QueueView,first_boardable

def stage(*rids):
    rows=[{'rid':rid,'board':0} for rid in rids]
    return {**rows[0],'pool':rows}
def bus(vid,at,rid='A',cap=1.):
    return {'id':vid,'rid':rid,'times':[at,at+10],'cap':cap,'onboard':[],'last_stop':-1}
def person(sid,ready,weight=1.,node=0):return {'sid':sid,'ready_time':ready,'w':weight,'node':node}
def waiter(w,*rids):return {'w':w,'stages':[stage(*rids)],'stage':0}
def view_of(waiting):
    types=[];lookup={};services={};type_at=[]
    for i,p in enumerate(waiting):
        key=tuple(sorted((s['rid'],s['board']) for s in p['stages'][0]['pool']))
        if key not in lookup:
            lookup[key]=len(types);types.append({'indices':[],'prefix':[0.]})
            for service in key:services.setdefault(service,[]).append(lookup[key])
        kind=lookup[key];row=types[kind];row['indices'].append(i);row['prefix'].append(row['prefix'][-1]+p['w']);type_at.append(kind)
    return QueueView({'types':types,'services':services,'type_at':type_at},len(waiting)-1)
class CommittedForecast(unittest.TestCase):
    def test_not_yet_departed_plan_is_not_information(self):
        r=CommittedArrivals(1);r.register(person(1,150),stage('A'),100)
        self.assertEqual(r.forecast(0,50,200),())
        self.assertEqual(len(r.forecast(0,100,200)),1)
    def test_only_predecessors_not_later_or_equal_ready(self):
        r=CommittedArrivals(1)
        for sid,at in [(1,80),(2,90),(3,100)]:r.register(person(sid,at),stage('A'),10)
        self.assertEqual([x['sid'] for x in r.forecast(0,20,90)],[1])
    def test_retained_fifo_ticket_cannot_be_overtaken(self):
        r=CommittedArrivals(1);r.register(person(1,80),stage('A'),10)
        self.assertEqual(r.forecast(0,20,90,retained_queued=True),())
    def test_owner_excluded_and_cancelled_or_rerouted_not_duplicated(self):
        r=CommittedArrivals(2);r.register(person(1,120),stage('A'),100);r.register(person(1,80,node=1),stage('B'),10)
        self.assertEqual(r.forecast(0,20,200),())
        self.assertEqual(r.forecast(1,20,200,owner=1),())
        self.assertEqual(len(r.forecast(1,100,200)),1)
        r.cancel(1);self.assertEqual(r.forecast(1,110,200),())
    def test_approaching_predecessor_changes_first_boardable_bus(self):
        r=CommittedArrivals(1);r.register(person(1,80),stage('A'),10);pending=r.forecast(0,20,90)
        fleet=[bus(0,100),bus(1,200)];rows=[(100,0,0),(200,1,0)]
        self.assertEqual(first_boardable(rows,fleet,90,20,stage('A'),1,[])[0],100)
        self.assertEqual(first_boardable(rows,fleet,90,20,stage('A'),1,[],pending_arrivals=pending)[0],200)
    def test_pending_person_cannot_take_bus_before_ready(self):
        r=CommittedArrivals(1);r.register(person(1,80),stage('A'),10);pending=r.forecast(0,20,90)
        fleet=[bus(0,50),bus(1,100),bus(2,200)];rows=[(v['times'][0],v['id'],0) for v in fleet]
        self.assertEqual(first_boardable(rows,fleet,90,20,stage('A'),1,[],pending_arrivals=pending)[0],200)
    def test_paired44_capacity_and_projected_load_share_same_fifo(self):
        r=CommittedArrivals(1);r.register(person(1,80,67),stage('A'),10);pending=r.forecast(0,20,90)
        fleet=[bus(0,100,cap=44),bus(1,100,cap=44)]
        result=first_boardable([(100,0,0),(100,1,0)],fleet,90,20,stage('A'),1,[],indivisible=True,project_load=True,pending_arrivals=pending)
        self.assertEqual(result[1],1);self.assertEqual(result[4]['known_ahead_boarded_here'],23)
        self.assertEqual(result[4]['projected_after_self'],24)
    def test_inputs_do_not_mutate_and_other_service_cannot_clear_demand(self):
        r=CommittedArrivals(1);r.register(person(1,80),stage('A'),10);pending=r.forecast(0,20,90)
        fleet=[bus(0,90,'B'),bus(1,100),bus(2,200)];rows=[(v['times'][0],v['id'],0) for v in fleet]
        before=copy.deepcopy((fleet,pending))
        self.assertEqual(first_boardable(rows,fleet,90,20,stage('A'),1,[],pending_arrivals=pending)[0],200)
        self.assertEqual(before,(fleet,pending))
    def test_randomized_list_and_indexed_against_time_ordered_oracle(self):
        rng=random.Random(1112)
        for trial in range(150):
            waiting=[waiter(rng.uniform(.1,3),*rng.choice([('A',),('B',),('A','B')])) for _ in range(rng.randrange(0,12))]
            r=CommittedArrivals(1)
            for sid in range(rng.randrange(1,8)):r.register(person(sid,rng.uniform(25,89),rng.uniform(.1,3)),stage(*rng.choice([('A',),('B',),('A','B')])),10)
            pending=r.forecast(0,20,90);fleet=[bus(i,40+i*30,rng.choice(['A','B']),rng.uniform(1,8)) for i in range(9)]
            rows=[(v['times'][0],i,0) for i,v in enumerate(fleet)]
            # Independent flat FIFO of ready-time stamped people.
            people=[[-1.,p['w'],{s['rid'] for s in p['stages'][0]['pool']}] for p in waiting]+[[p['ready'],p['weight'],{rid for rid,k in p['services']}] for p in pending]
            people.sort(key=lambda p:p[0]);expected=None
            for at,vid,k in rows:
                free=fleet[vid]['cap'];rid=fleet[vid]['rid']
                for p in people:
                    if p[0]<=at and rid in p[2]:take=min(free,p[1]);p[1]-=take;free-=take
                if at>=90 and free>=1-1e-6:expected=(at,vid,k);break
            for queue in (waiting,view_of(waiting)):
                result=first_boardable(rows,fleet,90,20,stage('A','B'),1,queue,indivisible=True,pending_arrivals=pending)
                self.assertEqual(result[:3] if result else None,expected,trial)
if __name__=='__main__':unittest.main()
