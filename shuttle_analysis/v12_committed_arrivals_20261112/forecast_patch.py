"""Causal committed approaches; physical queues, tastes and walk preference unchanged."""
from pathlib import Path
def replace(p,old,new):
    s=p.read_text(encoding='utf8');assert s.count(old)==1,(p,old[:70],s.count(old));p.write_text(s.replace(old,new),encoding='utf8')

ADDITION='''class CommittedArrivals:
    """Only approaches already started at the information time, not future plans."""
    def __init__(self,nodes):
        self.entries={};self.active=[{} for _ in range(nodes)];self.future=[];self.serial=0;self.now=-math.inf
        self.queries=self.nonempty=0;self.maximum_candidates=0;self.maximum_mass=0.
    def cancel(self,sid):
        old=self.entries.pop(sid,None)
        if old is not None:self.active[old['node']].pop(sid,None)
    def register(self,state,stage,departed_at):
        self.cancel(state['sid']);self.serial+=1
        services=tuple(sorted({(s['rid'],s['board']) for s in stage.get('pool',[stage])}))
        row={'sid':state['sid'],'node':state['node'],'start':departed_at,'ready':state['ready_time'],
             'weight':state['w'],'services':services,'serial':self.serial}
        self.entries[row['sid']]=row
        if departed_at<=self.now+EPS:self.active[row['node']][row['sid']]=row
        else:heapq.heappush(self.future,(departed_at,self.serial,row['sid']))
    def advance(self,now):
        assert now>=self.now-EPS,('Information clock went backward',now,self.now)
        self.now=now
        while self.future and self.future[0][0]<=now+EPS:
            _,serial,sid=heapq.heappop(self.future);row=self.entries.get(sid)
            if row is not None and row['serial']==serial:self.active[row['node']][sid]=row
    def forecast(self,node,now,ego_ready,owner=None,retained_queued=False):
        self.advance(now);self.queries+=1
        # Later queue entries cannot overtake an already-issued FIFO ticket.
        if retained_queued:return ()
        rows=[r for r in self.active[node].values() if r['sid']!=owner and r['ready']<ego_ready-EPS]
        assert all(r['start']<=now+EPS for r in rows)
        rows.sort(key=lambda r:(r['ready'],r['serial']))
        if rows:self.nonempty+=1
        self.maximum_candidates=max(self.maximum_candidates,len(rows))
        self.maximum_mass=max(self.maximum_mass,math.fsum(r['weight'] for r in rows))
        return tuple(rows)
    def report(self):
        return {'queries':self.queries,'nonempty_queries':self.nonempty,'maximum_candidate_count':self.maximum_candidates,'remaining_commitments':len(self.entries),
          'maximum_candidate_mass':self.maximum_mass,'information_scope':'already-started model approaches and preparation; no future departures or later realized changes',
          'not_observed_student_tracking':True,'same_ready_time_tie':'unresolved future ties excluded; retained issued FIFO tickets preserved'}


def consume_current_view(view,served,kinds,available):
    ahead=math.fsum(max(0.,view.totals[i]-served[i]) for i in kinds)
    if ahead<=available+EPS:
        for i in kinds:served[i]=view.totals[i]
        return max(0.,available-ahead)
    if len(kinds)==1:served[kinds[0]]+=available;return 0.
    low,high=-1,view.limit
    while high-low>1:
        middle=(low+high)//2
        mass=math.fsum(max(0.,view.prefix(i,middle)-served[i]) for i in kinds)
        if mass<=available:low=middle
        else:high=middle
    used=0.
    for i in kinds:
        prefix=max(served[i],view.prefix(i,low));used+=prefix-served[i];served[i]=prefix
    kind=view.cache['type_at'][high];assert kind in kinds
    served[kind]+=max(0.,available-used)
    return 0.


def timed_boardable(rows,vehicles,ready,now,stage,weight,waiting,pending,indivisible=False,project_load=False):
    # Current ready queue is ahead of all not-yet-ready commitments.
    view=waiting if isinstance(waiting,QueueView) else None
    served=[0.]*len(view.totals) if view is not None else None
    ahead=None if view is not None else [[float(s['w']),s['stages'][s['stage']]] for s in waiting]
    future=[[r['ready'],float(r['weight']),r['services']] for r in pending]
    assert all(r['start']<=now+EPS and r['ready']<ready-EPS for r in pending)
    need=weight;start=bisect.bisect_left(rows,(now-EPS,-1,-1))
    for when,vid,k in rows[start:]:
        vehicle=vehicles[vid]
        if vehicle['last_stop']>=k:continue
        available=vehicle['cap']-sum(s['w'] for target,s in vehicle['onboard'] if target>k)
        available=forecast_available(vehicle,k,now,available)
        if available<=EPS:continue
        before=available
        if view is not None:
            available=consume_current_view(view,served,view.cache['services'].get((vehicle['rid'],k),()),available)
        else:
            for other in ahead:
                if other[0]<=EPS or stage_choice(other[1],vehicle['rid'],k) is None:continue
                take=min(available,other[0]);other[0]-=take;available-=take
                if available<=EPS:break
        for other in future:
            if available<=EPS:break
            if other[0]>when+EPS:break
            if other[1]<=EPS or (vehicle['rid'],k) not in other[2]:continue
            take=min(available,other[1]);other[1]-=take;available-=take
        choice=stage_choice(stage,vehicle['rid'],k)
        if when<ready-EPS or choice is None or available<=EPS:continue
        if need<=available+EPS:
            result=boarding_projection(when,vid,k,choice,vehicle,available,need,project_load,before)
            if project_load:result[4].update(committed_candidate_count=len(pending),
                committed_candidate_mass=math.fsum(r['weight'] for r in pending),
                forecast_information_time=now,ego_ready_time=ready,
                pending_mass_scope='candidate approaches ready before ego, not observed people or all boardings on this vehicle')
            return result
        if not indivisible:need-=available
    return None


'''

def apply(work):
    p=work/'engine.py'
    replace(p,'def first_boardable(rows,vehicles,ready,now,stage,weight,waiting,indivisible=False,project_load=False):',
      ADDITION+'def first_boardable(rows,vehicles,ready,now,stage,weight,waiting,indivisible=False,project_load=False,pending_arrivals=()):')
    replace(p,'    if isinstance(waiting,QueueView):return indexed_boardable',
      '    if pending_arrivals:return timed_boardable(rows,vehicles,ready,now,stage,weight,waiting,pending_arrivals,indivisible,project_load)\n    if isinstance(waiting,QueueView):return indexed_boardable')
    replace(p,'Forecast from current known queues/onboard loads, never future arrivals.',
      'Forecast current queues and optional already-started timed commitments; no future departures.')
    replace(p,"    preparing_states=[{} for _ in nodes]", "    preparing_states=[{} for _ in nodes]\n    committed=CommittedArrivals(len(nodes))")
    replace(p,"    def finish(state,t,unserved=False):\n", "    def finish(state,t,unserved=False):\n        committed.cancel(state['sid'])\n")
    replace(p,"    def walk_next(state,t,path,seconds,prep_seconds=20):\n", "    def walk_next(state,t,path,seconds,prep_seconds=20):\n        committed.cancel(state['sid']);approach_started=t\n")
    replace(p,"        if state['ready_time']<=END:push(t,0,'arrive',state)",
      "        if state['ready_time']<=END:\n            if config.get('forecast_committed_arrivals'):committed.register(state,stage,approach_started)\n            push(t,0,'arrive',state)")
    replace(p,"        schedule,vehicles,queues,qmass,premass,queue_versions,ri,walk_next,record_wait,push,decisions,behavior_decisions)",
      "        schedule,vehicles,queues,qmass,premass,queue_versions,ri,walk_next,record_wait,push,decisions,behavior_decisions,committed=committed)")
    replace(p,"        if kind=='ready':\n            state=payload", "        if kind=='ready':\n            state=payload\n            committed.cancel(state['sid'])")
    p=work/'policy.py'
    replace(p,'queues,qmass,premass,queue_versions,ri,walk_next,record_wait,push,decisions,behavior_decisions):',
      'queues,qmass,premass,queue_versions,ri,walk_next,record_wait,push,decisions,behavior_decisions,committed=None):')
    replace(p,"                    choice=first_boardable(rows,vehicles,ready,now,stage,request,view,indivisible=whole,project_load=config.get('project_queue_load_for_crowding',False))",
      """                    pending=committed.forecast(node,now,ready,state.get('sid'),keep and count==0 and state.get('queued',False)) if committed is not None and config.get('forecast_committed_arrivals') else ()
                    choice=first_boardable(rows,vehicles,ready,now,stage,request,view,indivisible=whole,project_load=config.get('project_queue_load_for_crowding',False),pending_arrivals=pending)""")
    replace(p,"                'selected_cost':selected['cost'],'joint_action_count':len(options),'selected_key':selected['key']})",
      """                'selected_cost':selected['cost'],'joint_action_count':len(options),'selected_key':selected['key'],
                'board_prediction':ride.components() if ride else None,
                'wait_prediction':future.components() if future else None,
                'selected_prediction':selected['prediction'].components(),
                'traits':state['traits'].record(),'completed_wait_seconds':state.get('completed_wait_seconds',0.),
                'physical_stop_entry':state['stop_entry'],'full_passes':state['full_passes'],'change_count':len(state['history'])})""")
    replace(p,"                    'initial_plan_changes':self.initial_choices,", "                    'committed_approach_forecast':committed.report() if committed is not None else None,\n                    'initial_plan_changes':self.initial_choices,")
