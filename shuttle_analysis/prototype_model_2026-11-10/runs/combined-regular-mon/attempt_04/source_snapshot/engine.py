"""Isolated v9 candidate: different-line walking transfers and terminal walk escape.
The preserved v7 simulator and all scientific datasets remain unchanged.
"""
from collections import deque
from pathlib import Path
import argparse,bisect,copy,heapq,json,math,time,hashlib
import artifacts as base
from artifacts import ROOT as WORK,START,END,EPS
import metrics as v4
from policy import attach_policy
from capacity import seats,balance,capacity_at_clock,batch_size_at_clock
OUT=WORK/'unused_public_output'
SETTINGS={'max_switches':None,'recheck_seconds':60,'minimum_gain_seconds':120,'cooldown_seconds':180}


def stable_uniform(*parts):
    key='walk-choice-v9:'+':'.join(map(str,parts))
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8],'big')/2**64

def walking_weight(meters):
    """Scenario: equal willingness through 500m; sharp decay beyond 1km."""
    if meters<=500:return 1.
    if meters<=1000:return 1.-.7*(meters-500)/500
    return .3*math.exp(-(meters-1000)/150)

def change_probability(gain,full,elapsed,visible,count=0,crowd_pressure=0.):
    ordinary=min(.85,.15+.35*min(1.,gain/600)+.15*max(0.,visible/40-.5))
    ordinary*=.30**count
    urgency=0. if elapsed<900 else 1.-math.exp(-(elapsed-780)/40)
    wait_stress=1.-math.exp(-max(0.,elapsed-120)/1200)
    stress=max(1.-math.exp(-.15*full),wait_stress,urgency,min(.999,crowd_pressure))
    return min(.999999,ordinary+stress-ordinary*stress)

def broaden_compatible_stage(stage,pool,factor):
    if not pool or stage.get('expanded_compatible_pool') or stage.get('choice_pool_locked'):return stage
    return {**stage,'pool':scaled_stages(pool,factor),'expanded_compatible_pool':True}


def stage_choice(stage,rid,board):
    return next((s for s in stage.get('pool',[stage]) if s['rid']==rid and s['board']==board),None)


class QueueView:
    """Sparse weighted prefix indexes, retaining the exact original FIFO order."""
    __slots__=('cache','limit','excluded','totals')
    def __init__(self,cache,limit,excluded=None):
        self.cache=cache;self.limit=limit;self.excluded=excluded
        self.totals=[self.prefix(i,limit) for i in range(len(cache['types']))]
    def prefix(self,kind,position):
        row=self.cache['types'][kind];position=min(position,self.limit)
        count=bisect.bisect_right(row['indices'],position)
        value=row['live_mass'].prefix(count) if 'live_mass' in row else row['prefix'][count]
        if self.excluded and self.excluded[1]==kind and self.excluded[0]<=position:value-=self.excluded[2]
        return max(0.,value)

class LiveMass:
    """Fenwick prefix sums for a queue being boarded within one event."""
    def __init__(self,values):
        self.tree=[0.]*(len(values)+1)
        for i,value in enumerate(values):self.add(i,value)
    def add(self,index,delta):
        i=index+1
        while i<len(self.tree):self.tree[i]+=delta;i+=i&-i
    def prefix(self,count):
        total=0.;i=count
        while i:total+=self.tree[i];i-=i&-i
        return max(0.,total)


def indexed_boardable(rows,vehicles,ready,now,stage,weight,view):
    served=[0.]*len(view.totals);need=weight;cache=view.cache
    start=bisect.bisect_left(rows,(now-EPS,-1,-1))
    for position in range(start,len(rows)):
        when,vid,k=rows[position];vehicle=vehicles[vid]
        if vehicle['last_stop']>=k:continue
        available=vehicle['cap']-sum(s['w'] for target,s in vehicle['onboard'] if target>k)
        if available<=EPS:continue
        kinds=cache['services'].get((vehicle['rid'],k),())
        ahead=math.fsum(max(0.,view.totals[i]-served[i]) for i in kinds)
        choice=stage_choice(stage,vehicle['rid'],k)
        if ahead<=available+EPS:
            for i in kinds:served[i]=view.totals[i]
            available=max(0.,available-ahead)
            if when>=ready-EPS and choice is not None and available>EPS:
                if need<=available+EPS:return when,vid,k,choice
                need-=available
            continue
        # Exact FIFO consumption among eligible patterns. One-pattern services
        # have a scalar prefix; overlapping pools use weighted order statistics.
        if len(kinds)==1:served[kinds[0]]+=available;continue
        low,high=-1,view.limit
        while high-low>1:
            middle=(low+high)//2
            mass=math.fsum(max(0.,view.prefix(i,middle)-served[i]) for i in kinds)
            if mass<=available:low=middle
            else:high=middle
        used=0.
        for i in kinds:
            prefix=max(served[i],view.prefix(i,low));used+=prefix-served[i];served[i]=prefix
        kind=cache['type_at'][high]
        assert kind in kinds
        served[kind]+=max(0.,available-used)
    return None


def first_boardable(rows,vehicles,ready,now,stage,weight,waiting):
    """Forecast from current known queues/onboard loads, never future arrivals.

waiting is the queue ahead of a retained position, or the current entire queue
ahead of a new arrival. Other services can clear compatible waiting passengers.
"""
    if isinstance(waiting,QueueView):return indexed_boardable(rows,vehicles,ready,now,stage,weight,waiting)
    ahead=[[float(s['w']),s['stages'][s['stage']]] for s in waiting]
    need=weight
    start=bisect.bisect_left(rows,(now-EPS,-1,-1))
    for position in range(start,len(rows)):
        when,vid,k=rows[position]
        vehicle=vehicles[vid]
        if vehicle['last_stop']>=k:continue
        available=vehicle['cap']-sum(s['w'] for target,s in vehicle['onboard'] if target>k)
        if available<=EPS:continue
        for other in ahead:
            if other[0]<=EPS or stage_choice(other[1],vehicle['rid'],k) is None:continue
            take=min(available,other[0]);other[0]-=take;available-=take
            if available<=EPS:break
        choice=stage_choice(stage,vehicle['rid'],k)
        if when<ready-EPS or choice is None or available<=EPS:continue
        if need<=available+EPS:return when,vid,k,choice
        need-=available
    return None


def scaled_stages(stages,factor):
    result=[]
    for stage in stages:
        row={**stage,'next_walk':[stage['next_walk'][0],stage['next_walk'][1]*factor]}
        if 'continuation_stages' in stage:row['continuation_stages']=scaled_stages(stage['continuation_stages'],factor)
        if 'pool' in stage:
            row['pool']=[{**s,'next_walk':[s['next_walk'][0],s['next_walk'][1]*factor]} for s in stage['pool']]
            for choice,source in zip(row['pool'],stage['pool']):
                if 'continuation_stages' in source:choice['continuation_stages']=scaled_stages(source['continuation_stages'],factor)
        result.append(row)
    return result


def simulate(bundle,day,scenario,export=True,settings=None):
    settings={**SETTINGS,**(settings or {})};prepared=bundle['prepared'];common=prepared['common']
    config=bundle['prototype_config']
    routes=prepared['routes'];nodes=common['nodes'];ri=common['route_info']
    lookup={n['id']:i for i,n in enumerate(nodes)}
    def node_for(stage):
        key=f"{stage['rid']}|{stage['board']}"
        return lookup[key] if stage['rid'].startswith('shuttle') else bundle['city_node_lookup'][key]
    def current_stage(state):return state['stages'][state['stage']]
    heap=[];serial=0;state_serial=0
    queues=[deque() for _ in nodes];qmass=[0.]*len(nodes);schedule=[[] for _ in nodes]
    premass=[0.]*len(nodes)
    behavior_decisions=[];behavior_counts={};forced_weight=0.
    queue_versions=[0]*len(nodes);group_cache={}
    vehicles=[];finished=[];waits=[];wait_audit=[];events=[];decisions=[];gate_boardings=[];queue_ticket=0
    checks=0;forecast_calls=0
    def push(when,priority,kind,payload):
        nonlocal serial
        serial+=1;heapq.heappush(heap,(float(when),priority,serial,kind,payload))
    def identity():
        nonlocal state_serial
        state_serial+=1;return state_serial
    for rid,info in ri.items():
        clocks=bundle['supply'][scenario][rid]
        prefix=info.get('origin_to_modeled_first_stop_seconds',0.)
        clocks=[clock for clock in clocks for _ in range(batch_size_at_clock(info,clock))]
        for clock in clocks:
            t0=clock+prefix-info['offsets'][info['anchor']]
            # Vehicles already moving at the first displayed time remain included.
            if t0>END or t0+info['offsets'][-1]<0:continue
            vid=len(vehicles)
            vehicle={'id':vid,'rid':rid,'cap':capacity_at_clock({**info,'capacity':info.get('capacity',25 if rid=='shuttle-41914' else 60)},clock),
                     't0':t0,'onboard':[],'load':0.,'legs':[],'last_stop':-1}
            vehicles.append(vehicle)
            for k,offset in enumerate(info['offsets']):
                when=t0+offset;push(when,1,'vehicle',(vid,k))
                if info.get('city'):node=bundle['city_node_lookup'].get(f'{rid}|{k}')
                else:node=lookup.get(f'{rid}|{k}') if k<info['n'] else None
                if node is not None and when<=END:schedule[node].append((when,vid,k))
    for rows in schedule:rows.sort()
    def finish(state,t,unserved=False):
        state.update(queued=False,done=True,unserved=unserved,finish_time=t);finished.append(state)
    def record_wait(state,t,outcome):
        stage=current_stage(state);node=state['node']
        display_end=t+1 if outcome=='unserved' and abs(t-END)<EPS else t
        state['legs']=state['legs']+[[1,state['arrival'],display_end,stage['wait_path'],node,state['first_denied'],-1]]
        waits.append([node,state['arrival'],t,state['w'],state['first_denied'],outcome=='unserved',state['plan'][0],outcome])
        wait_audit.append({'node':node,'arrival':state['arrival'],'ready':state['ready_time'],'end':t,
            'weight':state['w'],'id':state['plan'][0],'ticket':state.get('queue_ticket'),
            'eligibility':state['entry_eligibility'],'outcome':outcome,'vehicle':state.get('boarding_vehicle'),
            'physical_stop_entry':state['stop_entry'],
            'realized_change_count':len(state['history']),'full_passes_seen':state['full_passes'],
            'parent_id':bundle['parent_ids'].get(str(state['plan'][0]),state['plan'][0]),
            'stop_arrival_at':state['arrival'],'ready_at':state['ready_time'],
            'boarding_at':t if outcome=='boarded' else None,'leave_at':t})
    def walk_next(state,t,path,seconds,prep_seconds=20):
        if seconds>EPS:state['legs']=state['legs']+[[0,t,t+seconds,path,-1,-1,-1,bool(state['history'])]]
        t+=seconds
        if state['stage']>=len(state['stages']):finish(state,t);return
        stage=current_stage(state);node=node_for(stage)
        # Considering the first compatible line at the SAME physical queue is
        # an eligibility choice, not a walk or a consumed rerouting decision.
        if state['stage']==len(state['stages'])-1 and not stage.get('expanded_compatible_pool') and not stage.get('choice_pool_locked'):
            pool=bundle.get('compatible_single_stage_pools',{}).get(f"{node}|{state['dest']}",[])
            pool=[s for s in pool if all((x['rid'],x['board']) not in state['used_services']
                                         for x in [s,*s.get('continuation_stages',[])])]
            if pool:
                stage=broaden_compatible_stage(stage,pool,state['factor'])
                state['stages']=list(state['stages']);state['stages'][state['stage']]=stage
        same_stop=state.get('node')==node and seconds<EPS and (not state['legs'] or state['legs'][-1][0]!=3)
        if not same_stop:
            state['visit']+=1;state['stop_entry']=t;state['full_passes']=0
            if config['behavior']=='v9_frozen' and t+1200<=END:push(t+1200,2,'patience',(state,state['visit']))
        state.update(arrival=t,first_denied=-1,node=node,ready_time=t+prep_seconds,queue_ticket=None,
                     entry_eligibility=[(s['rid'],s['board']) for s in stage.get('pool',[stage])],boarding_vehicle=None)
        if state['ready_time']<=END:push(t,0,'arrive',state)
        else:
            if t<=END:record_wait(state,END,'unserved')
            finish(state,max(t,END),True)
    def waiting_before(node,state=None,keep_position=False):
        cached=group_cache.get(node)
        if cached is None or cached['version']!=queue_versions[node]:
            types=[];positions={};lookup_types={};type_at=[];services={}
            for position,other in enumerate(queues[node]):
                stage=current_stage(other)
                key=tuple(sorted((s['rid'],s['board']) for s in stage.get('pool',[stage])))
                if key not in lookup_types:
                    kind=len(types);lookup_types[key]=kind;types.append({'indices':[],'prefix':[0.]})
                    for service in key:services.setdefault(service,[]).append(kind)
                kind=lookup_types[key];row=types[kind]
                row['indices'].append(position);row['prefix'].append(row['prefix'][-1]+other['w'])
                positions[other['sid']]=(position,kind,other['w']);type_at.append(kind)
            cached={'version':queue_versions[node],'types':types,'positions':positions,'type_at':type_at,'services':services}
            group_cache[node]=cached
        position=cached['positions'].get(state['sid']) if state is not None else None
        if position is not None and keep_position:return QueueView(cached,position[0]-1)
        return QueueView(cached,len(cached['type_at'])-1,position)
    def forecast(stages,t,factor,now,owner=None,keep_position=False,prepared_first=False,weight=0.):
        nonlocal forecast_calls
        forecast_calls+=1
        chain=list(stages);i=0
        while chain:
            stage=chain[0]
            node=node_for(stage);ready=t if i==0 and prepared_first else t+20
            ahead=waiting_before(node,owner,keep_position and i==0)
            choice=first_boardable(schedule[node],vehicles,ready,now,stage,weight,ahead)
            if choice is None:return math.inf
            dep,vid,k,chosen=choice;info=ri[vehicles[vid]['rid']]
            end=k+chosen['alight']-chosen['board']
            t=dep+info['offsets'][end]-info['offsets'][k]+chosen['next_walk'][1]*factor
            chain=chosen['continuation_stages'] if 'continuation_stages' in chosen else chain[1:]
            i+=1
            assert i<=8,'Cyclic policy continuation'
        return t
    def reschedule(state,t):
        if not bundle['alternatives'].get(f"{state['node']}|{state['dest']}"):return
        state['check_version']+=1
        t=max(t,state['last_switch']+settings['cooldown_seconds'])
        if t<=END:push(t,2,'recheck',(state,state['check_version']))
    def pattern(stage):return tuple((s['rid'],s['board'],s['alight']) for s in stage.get('pool',[stage]))
    def maybe_switch(state,t,reason,forced=False):
        nonlocal forced_weight
        node=state['node'];factor=state['factor'];stage=current_stage(state)
        ready=t>=state['ready_time']-EPS
        old=forecast(state['stages'][state['stage']:],t,1.,t,state,True,ready,state['w'])
        visible=qmass[node]+premass[node]+(0. if state['queued'] or state.get('preparing') else state['w'])
        elapsed=max(0.,t-state['stop_entry'])
        # A full bus seen before this person arrived is not an experience of
        # being left behind; pooled stops may also have other uncrowded lines.
        full=state['full_passes']
        tolerance=20+15*stable_uniform(state['plan'][0],node,'crowd-tolerance')
        named=nodes[node].get('stop_id') in {'120000167','120000168','120000196','120000197'}
        crowded=named and visible>=tolerance
        crowd_pressure=1./(1.+math.exp(max(-50.,min(50.,(tolerance-visible)/1.5)))) if named else 0.
        capacity=min(capacity_at_clock({**ri[s['rid']],'capacity':ri[s['rid']].get('capacity',25 if s['rid']=='shuttle-41914' else 60)},t) for s in stage.get('pool',[stage]))
        triggered=visible>=max(12.,.6*capacity) or elapsed>=300 or full>0 or crowded or not math.isfinite(old)
        if not forced and not triggered:return False
        if not forced and not crowded and elapsed<900 and t-state['last_switch']<settings['cooldown_seconds']:return False
        # This is a disutility for standing/frustration, not elapsed travel
        # time added again to an ETA. Counts and actual trip clocks stay exact.
        discomfort=90*full+.25*elapsed+6*max(0.,visible-20)+max(0.,elapsed-600)**2/180
        if named:discomfort+=min(1800.,max(0.,visible-tolerance)*120)
        old_cost=old+discomfort if math.isfinite(old) else math.inf
        best=None;best_eta=math.inf;best_score=math.inf if forced else old_cost
        for option in bundle['alternatives'].get(f"{node}|{state['dest']}",[]):
            stages=option['stages'];access=option['walk'][1]*factor
            distance_weight=walking_weight(option.get('walk_meters',option['walk'][1]*1.2))
            # Longer waiting/full-bus experience can overcome ordinary walking
            # reluctance, without imposing a hard time or queue cutoff.
            pressure=max(0.,elapsed-600)/150+.5*full+2*crowd_pressure
            effective_distance_weight=1.-(1.-distance_weight)*math.exp(-pressure)
            if not forced and stable_uniform(state['plan'][0],state['visit'],option['walk'][0],'walking-distance')>=effective_distance_weight:continue
            if option['kind']=='walk_transfer' and access>1800:continue
            if stages:
                first=node_for(stages[0])
                # All admissible same-stop line/suffix choices are already in
                # the boarding policy. Reconsidering them keeps the FIFO ticket
                # and consumes no walking/rerouting budget.
                if first==node:continue
                if first in state['visited'] and stable_uniform(state['plan'][0],state['visit'],'revisit')>=.05:continue
                if first==node and stage.get('forbidden_services'):
                    forbidden={tuple(x) for x in stage['forbidden_services']}
                    kept=[s for s in stages[0].get('pool',[stages[0]]) if (s['rid'],s['board']) not in forbidden]
                    if not kept:continue
                    stages=[{**kept[0],**({'pool':kept} if len(kept)>1 else {}),'choice_pool_locked':True,
                             'forbidden_services':list(forbidden)},*stages[1:]]
                if first==node and pattern(stages[0])==pattern(stage):continue
                if first==node and len(stages)==1 and state['stage']==len(state['stages'])-1:
                    if set(pattern(stages[0])).issubset(set(pattern(stage))):continue
                if forced and first==node:continue
                if first!=node and access>EPS:
                    # Downstream on the same line is possible, but receives an
                    # 8% consideration weight. Mixed pools retain other lines.
                    old_boards={s['rid']:s['board'] for s in stage.get('pool',[stage])}
                    choices=[];forbidden=[]
                    consider_downstream=stable_uniform(state['plan'][0],state['visit'],'downstream-action')<.08
                    for s in stages[0].get('pool',[stages[0]]):
                        if (s['rid'],s['board']) in state['used_services']:continue
                        downstream=s['rid'] in old_boards and s['board']>old_boards[s['rid']]
                        if downstream and not consider_downstream:
                            forbidden.append((s['rid'],s['board']));continue
                        choices.append(s)
                    if not choices:continue
                    stages=[{**choices[0],**({'pool':choices} if len(choices)>1 else {}),'choice_pool_locked':True,
                             'forbidden_services':forbidden},*stages[1:]]
                # No future queue is peeked at. A zero-wait travel lower bound
                # only prunes candidates that cannot beat the current choice.
                lower=t+access
                for st in stages:
                    lower+=20+min(ri[s['rid']]['offsets'][s['alight']]-ri[s['rid']]['offsets'][s['board']]+s['next_walk'][1]*factor for s in st.get('pool',[st]))
                if lower>=best_score-EPS:continue
            eta=forecast(stages,t+access,factor,t,state,False,access<EPS,state['w']) if stages else t+access
            score=eta-(180*math.log(max(distance_weight,1e-12)) if forced else 0.)
            if score<best_score:best_score=score;best_eta=eta;best={**option,'stages':stages}
        if best is None or (not forced and old_cost-best_eta<settings['minimum_gain_seconds']):return False
        count=len(state['history'])
        gain=600 if not math.isfinite(old_cost) else max(0.,old_cost-best_eta)
        probability=change_probability(gain,full,elapsed,visible,count,crowd_pressure)
        if not forced and stable_uniform(state['plan'][0],state['visit'],count,int(elapsed//60),'switch')>=probability:return False
        if state['queued']:
            queues[node].remove(state);qmass[node]-=state['w'];state['queued']=False;queue_versions[node]+=1
        if state.get('preparing'):
            premass[node]-=state['w'];state['preparing']=False
        record_wait(state,t,'switched')
        first=node_for(best['stages'][0]) if best['stages'] else None
        name='목적지까지 도보' if best['kind']=='walk' else best['name']
        if best['stages'] and first!=node:
            name=f"도보→{nodes[first]['name']} · "+'/'.join(routes[s['rid']]['name'] for s in best['stages'][0].get('pool',[best['stages'][0]]))
        decisions.append([t,node,state['w'],state['plan'][0],stage['rid'],best['kind'],name,
                          old if math.isfinite(old) else None,best_eta,reason])
        behavior_decisions.append({'time':t,'origin':node,'target':first,'uid':state['plan'][0],'weight':state['w'],
           'kind':best['kind'],'forced':forced,'crowd_reference':crowded,'reason':reason,'visible_queue':visible,
           'continuous_wait_seconds':elapsed,'full_passes':full,'probability':1. if forced else probability,
           'change_count_before':count,'old_services':state['entry_eligibility'],
           'new_services':[(s['rid'],s['board']) for s in best['stages'][0].get('pool',[best['stages'][0]])] if best['stages'] else [],
           'old_eta':old if math.isfinite(old) else None,'new_eta':best_eta,'standing_disutility_seconds':discomfort})
        if forced:forced_weight+=state['w']
        state['history']=state['history']+[[t,best['kind'],name]];state['last_switch']=t
        state['visited']=state['visited']|{node};state['check_version']+=1
        state['stages']=scaled_stages(best['stages'],factor);state['stage']=0
        access=best['walk'][1]*factor
        # A same-stop change joins behind the people already waiting, with no
        # invented additional walking or repeated completed boarding preparation.
        walk_next(state,t,best['walk'][0],access,0 if access<EPS and ready else 20)
        return True
    policy=attach_policy(bundle,config,node_for,current_stage,forecast,waiting_before,
        schedule,vehicles,queues,qmass,premass,queue_versions,ri,walk_next,record_wait,push,decisions,behavior_decisions)
    if config['behavior']!='v9_frozen':
        maybe_switch=policy.maybe_switch
        reschedule=policy.reschedule
    for plan in prepared['plans'][day]:
        state={'sid':identity(),'plan':plan,'w':plan[3],'stage':0,'stages':plan[6],
               'factor':bundle['walk_scales'][str(plan[0])],'legs':[],'history':[],
               'visit':0,
               'used_services':set(),
               'stop_entry':plan[4],'full_passes':0,'preparing':False,
               'last_switch':-math.inf,'visited':set(),'dest':bundle['destination_keys'][str(plan[0])],
               'queued':False,'done':False,'check_version':0,
               'traits':policy.make_traits(plan[0]),'fare_ledger':policy.empty_ledger(),
               'review_ordinal':0,'hazard_clock':None}
        if config['origin_choice']:push(plan[4],0,'depart',state)
        else:walk_next(state,plan[4],*plan[5])
    next_progress=START
    while heap:
        t,priority,_,kind,payload=heapq.heappop(heap)
        if next_progress<=t<=END:
            progress={'scenario':scenario,'weekday':day,'clock_seconds':t,
                      'queue_weight':math.fsum(qmass),'queued_states':sum(map(len,queues))}
            base.save(WORK/f'progress-{scenario}-{base.DAYS[day]}.json',progress)
            print('CITY_PROGRESS',json.dumps(progress,ensure_ascii=True),flush=True)
            next_progress=(int(t//7200)+1)*7200
        if kind=='depart':
            state=payload;policy.initial_choice(state,t);walk_next(state,t,*state['plan'][5]);continue
        if kind=='arrive':
            state=payload
            if state['done']:continue
            if maybe_switch(state,t,'arrival'):continue
            state['preparing']=True;premass[state['node']]+=state['w']
            push(state['ready_time'],0,'ready',state);continue
        if kind=='patience':
            state,visit=payload
            if state['done'] or state['visit']!=visit or not (state['queued'] or state.get('preparing')):continue
            # Twenty minutes is an audit alarm, not an artificial exit. Any
            # residual is retained and must fail the independent quality gate.
            maybe_switch(state,t,'continuous_wait_20_min_review')
            continue
        if kind=='ready':
            state=payload
            if state['done'] or not state.get('preparing'):continue
            if state.get('preparing'):premass[state['node']]-=state['w'];state['preparing']=False
            queue_ticket+=1;state['queue_ticket']=queue_ticket
            node=state['node'];state['queued']=True;queues[node].append(state);qmass[node]+=state['w'];queue_versions[node]+=1
            reschedule(state,t if config['behavior']!='v9_frozen' else t+settings['recheck_seconds']);continue
        if kind=='recheck':
            state,version=payload
            if not state['queued'] or state['done'] or version!=state['check_version']:continue
            if not maybe_switch(state,t,'queue_recheck'):reschedule(state,t if config['behavior']!='v9_frozen' else t+settings['recheck_seconds'])
            continue
        vid,k=payload;vehicle=vehicles[vid];rid=vehicle['rid'];info=ri[rid]
        before=vehicle['load'];remaining=[];off=0.
        for target,state in vehicle['onboard']:
            if target==k:
                off+=state['w'];stage=current_stage(state);policy.alighted(state,rid,t);state['stage']+=1
                walk_next(state,t,*stage['next_walk'])
            else:remaining.append((target,state))
        vehicle['onboard']=remaining;vehicle['load']-=off
        if abs(vehicle['load'])<EPS:vehicle['load']=0.
        if info.get('city'):node=bundle['city_node_lookup'].get(f'{rid}|{k}')
        else:node=lookup.get(f'{rid}|{k}') if k<info['n'] else None
        boarded=new_denied=eligible_left=0.
        if node is not None and t<=END:
            queue=queues[node];available=seats(vehicle['cap'],vehicle['load']);voluntary=set()
            live=waiting_before(node).cache
            for row in live['types']:
                if 'live_mass' not in row:row['live_mass']=LiveMass([b-a for a,b in zip(row['prefix'],row['prefix'][1:])])
            # Incompatible routes do not block people able to board this service.
            # FIFO is preserved among those eligible for this exact direction/seq.
            for state in list(queue):
                chosen=stage_choice(current_stage(state),rid,k)
                if chosen is None or available<=EPS:continue
                if config['boarding_choice'] and not policy.accept_boarding(state,chosen,vehicle,k,t,available):
                    voluntary.add(state['sid']);continue
                w=min(available,state['w']);stages=list(state['stages']);stages[state['stage']]=dict(chosen)
                selected_stage=state['stage']
                if 'continuation_stages' in chosen:
                    stages=[dict(chosen),*chosen['continuation_stages']];selected_stage=0
                take={**state,'sid':identity(),'w':w,'queued':False,'stages':stages,'stage':selected_stage,'boarding_vehicle':vid,
                      'used_services':state['used_services']|{(rid,k)}}
                end_index=k+chosen['alight']-chosen['board'];end=vehicle['t0']+info['offsets'][end_index]
                policy.boarded(take,rid,chosen,t,end)
                record_wait(take,t,'boarded')
                take['legs']=take['legs']+[[3,t,end,chosen['ride_path'],node,-1,vid]]
                vehicle['onboard'].append((end_index,take));boarded+=w;available-=w;vehicle['load']+=w;qmass[node]-=w
                if state['w']-w<=EPS:state['queued']=False;queue.remove(state)
                else:state['w']-=w
                position,kind,old_mass=live['positions'][state['sid']]
                group=live['types'][kind]
                group['live_mass'].add(bisect.bisect_left(group['indices'],position),-w)
                live['positions'][state['sid']]=(position,kind,max(0.,old_mass-w))
                if 'pool' in current_stage(state) and node==common.get('hot_nodes',{}).get('city_gate'):gate_boardings.append([t,rid,w,state['plan'][0]])
            if boarded>EPS:queue_versions[node]+=1
            for state in list(queue):
                if stage_choice(current_stage(state),rid,k) is None or state['sid'] in voluntary:continue
                eligible_left+=state['w'];assert available<EPS
                state['full_passes']+=1
                if state['first_denied']<0:state['first_denied']=t;new_denied+=state['w']
                reschedule(state,t if config['behavior']!='v9_frozen' else t+.001)
            events.append([t,node,vid,vehicle['cap'],before,off,boarded,vehicle['load'],
                           eligible_left,new_denied,max(0.,qmass[node]),rid,k])
        balance(vehicle['cap'],before,off,boarded,vehicle['load'])
        vehicle['last_stop']=k
        assert -EPS<=vehicle['load']<=vehicle['cap']+EPS,(rid,k,vehicle['load'])
        checks+=1
        if k<len(info['segments']) and (k<info['n'] or vehicle['load']>EPS):
            vehicle['legs'].append([t,vehicle['t0']+info['offsets'][k+1],info['segments'][k],round(vehicle['load'],6)])
    for queue in queues:
        for state in queue:record_wait(state,END,'unserved');finish(state,END,True)
    assert all(v['load']<EPS for v in vehicles)
    assert abs(sum(s['w'] for s in finished)-sum(p[3] for p in prepared['plans'][day]))<1e-5
    for state in finished:
        if not state['legs']:
            p=state['plan'];state['legs']=[[0,p[4],state['finish_time'],p[5][0],-1,-1,-1]]
    # Preserve end-of-window queues on the map, while censoring statistical
    # exposure at END rather than adding the one-second display sentinel.
    display_waits=[r[:2]+[END+1]+r[3:] if r[5] and abs(r[2]-END)<EPS else r for r in waits]
    data=v4.export_run(prepared,day,scenario,finished,display_waits,events,vehicles,decisions,gate_boardings,checks,forecast_calls,False)
    exposure={}
    for node,a,b,w,*_ in waits:
        if START<=a<END:
            for key in ((node,None),(node,int(a//3600))):
                total,seconds=exposure.get(key,(0.,0.));exposure[key]=(total+w,seconds+(b-a)*w)
    for (node,hour),(total,seconds) in exposure.items():
        row=data['daily'][str(node)] if hour is None else data['hourly'][str(node)][str(hour)]
        row['mean_queue_exposure_min']=seconds/total/60 if total>EPS else None
    city_nodes=set(common['city_nodes']);report=data['report']
    report.update(city_vehicle_runs=sum(not v['rid'].startswith('shuttle') for v in vehicles),
        city_speed_revision=common.get('city_speed_revision','fixture'),
        city_boarding_weight=sum(w[3] for w in waits if w[0] in city_nodes and w[7]=='boarded'),
        city_denied_weight=sum(w[3] for w in waits if w[0] in city_nodes and w[4]>=0),
        city_unserved_weight=sum(w[3] for w in waits if w[0] in city_nodes and w[7]=='unserved'),
        city_route_count=sum(bool(info.get('city')) for info in ri.values()),city_capacity_applied=True,external_background_passengers_included=False,
        actual_route_vehicle_capacities_verified=False,
        walk_choice_behavior=True,forced_reconsideration_weight=forced_weight,
        maximum_route_changes=None,target_mean_route_changes=1.,
        realized_mean_route_changes=sum(s['w']*len(s['history']) for s in finished)/sum(s['w'] for s in finished),
        late_arrival_weight=sum(s['w'] for s in finished if not s['unserved'] and s['finish_time']>END))
    data.update(schema_version='prototype_v1',prototype_config=config,policy_report=policy.report(),city_capacity_applied=True,
                event_columns=['time','node','vehicle','capacity','before','off','boarded','onboard','compatible_left','new_denied','physical_queue_left','route','stop_index'])
    if export:
        base.OUT=OUT
        base.packed(WORK/f'{scenario}-{base.DAYS[day]}.json.gz',data)
        base.packed(WORK/f'audit-{scenario}-{base.DAYS[day]}.json.gz',{'waits':waits,'wait_audit':wait_audit,'events':events,'report':report,
            'switches':decisions,'gate_boardings':gate_boardings,'behavior_decisions':behavior_decisions,
            'prototype_config':config,'policy_report':policy.report(),'boarding_choices':policy.boarding_choices,
            'parent_ids':bundle['parent_ids'],
            'vehicles':[{'id':v['id'],'rid':v['rid'],'cap':v['cap'],'t0':v['t0'],'legs':v['legs']} for v in vehicles],
            'legs':[{'id':s['plan'][0],'weight':s['w'],'unserved':s['unserved'],'history':s['history'],
                     'start':s['plan'][4],'legs':s['legs'],'traits':s['traits'].record(),'finish_time':s['finish_time'],
                     'fare_paid':s.get('fare_paid',0.),'parent_id':bundle['parent_ids'].get(str(s['plan'][0]),s['plan'][0])} for s in finished]})
    print('CITY_DONE',scenario,day,json.dumps(report,ensure_ascii=True),flush=True)
    return data

