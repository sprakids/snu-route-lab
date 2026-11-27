"""Finite-capacity city/shuttle vehicles, shared city stops, and queue rerouting."""
from collections import deque
from pathlib import Path
import argparse,bisect,copy,heapq,json,math,time
import capacity_model as base
import adaptive_capacity_model as v4
from prepare_city import prepare,planned_departures,WORK,OUT

START,END,EPS=base.START,base.END,base.EPS
SETTINGS=dict(v4.SETTINGS)


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
        value=row['prefix'][bisect.bisect_right(row['indices'],position)]
        if self.excluded and self.excluded[1]==kind and self.excluded[0]<=position:value-=self.excluded[2]
        return max(0.,value)


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
        if 'pool' in stage:
            row['pool']=[{**s,'next_walk':[s['next_walk'][0],s['next_walk'][1]*factor]} for s in stage['pool']]
        result.append(row)
    return result


def simulate(bundle,day,scenario,export=True,settings=None):
    settings={**SETTINGS,**(settings or {})};prepared=bundle['prepared'];common=prepared['common']
    routes=prepared['routes'];nodes=common['nodes'];ri=common['route_info']
    lookup={n['id']:i for i,n in enumerate(nodes)}
    def node_for(stage):
        key=f"{stage['rid']}|{stage['board']}"
        return lookup[key] if stage['rid'].startswith('shuttle') else bundle['city_node_lookup'][key]
    def current_stage(state):return state['stages'][state['stage']]
    heap=[];serial=0;state_serial=0
    queues=[deque() for _ in nodes];qmass=[0.]*len(nodes);schedule=[[] for _ in nodes]
    queue_versions=[0]*len(nodes);group_cache={}
    vehicles=[];finished=[];waits=[];events=[];decisions=[];gate_boardings=[]
    checks=0;forecast_calls=0
    def push(when,priority,kind,payload):
        nonlocal serial
        serial+=1;heapq.heappush(heap,(float(when),priority,serial,kind,payload))
    def identity():
        nonlocal state_serial
        state_serial+=1;return state_serial
    for rid,info in ri.items():
        clocks=planned_departures(info['plan']) if info.get('city') else base.dispatches(rid,scenario)
        prefix=info.get('origin_to_modeled_first_stop_seconds',0.)
        for clock in clocks:
            t0=clock+prefix-info['offsets'][info['anchor']]
            # Vehicles already moving at the first displayed time remain included.
            if t0>END or t0+info['offsets'][-1]<0:continue
            vid=len(vehicles)
            vehicle={'id':vid,'rid':rid,'cap':info.get('capacity',25 if rid=='shuttle-41914' else 60),
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
    def walk_next(state,t,path,seconds,prep_seconds=20):
        if seconds>EPS:state['legs']=state['legs']+[[0,t,t+seconds,path,-1,-1,-1,bool(state['history'])]]
        t+=seconds
        if state['stage']>=len(state['stages']):finish(state,t);return
        stage=current_stage(state);node=node_for(stage)
        state.update(arrival=t,first_denied=-1,node=node,ready_time=t+prep_seconds)
        if state['ready_time']<=END:push(state['ready_time'],0,'ready',state)
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
        for i,stage in enumerate(stages):
            node=node_for(stage);ready=t if i==0 and prepared_first else t+20
            ahead=waiting_before(node,owner,keep_position and i==0)
            choice=first_boardable(schedule[node],vehicles,ready,now,stage,weight,ahead)
            if choice is None:return math.inf
            dep,vid,k,chosen=choice;info=ri[vehicles[vid]['rid']]
            end=k+chosen['alight']-chosen['board']
            t=dep+info['offsets'][end]-info['offsets'][k]+chosen['next_walk'][1]*factor
        return t
    def reschedule(state,t):
        if len(state['history'])>=settings['max_switches']:return
        if not bundle['alternatives'].get(f"{state['node']}|{state['dest']}"):return
        state['check_version']+=1
        t=max(t,state['last_switch']+settings['cooldown_seconds'])
        if t<=END:push(t,2,'recheck',(state,state['check_version']))
    def pattern(stage):return tuple((s['rid'],s['board'],s['alight']) for s in stage.get('pool',[stage]))
    def maybe_switch(state,t,reason):
        if len(state['history'])>=settings['max_switches'] or t-state['last_switch']<settings['cooldown_seconds']:return False
        node=state['node'];factor=state['factor'];stage=current_stage(state)
        old=forecast(state['stages'][state['stage']:],t,1.,t,state,True,True,state['w'])
        best=None;best_eta=old
        for option in bundle['alternatives'].get(f"{node}|{state['dest']}",[]):
            stages=option['stages'];access=option['walk'][1]*factor
            if stages:
                first=node_for(stages[0])
                if first==node and pattern(stages[0])==pattern(stage):continue
                if first!=node and first in state['visited']:continue
            eta=forecast(stages,t+access,factor,t,state,False,access<EPS,state['w']) if stages else t+access
            if eta<best_eta:best_eta=eta;best=option
        if best is None or not v4.should_switch(t,old,best_eta,len(state['history']),state['last_switch'],settings):return False
        if state['queued']:
            queues[node].remove(state);qmass[node]-=state['w'];state['queued']=False;queue_versions[node]+=1
        record_wait(state,t,'switched')
        name='목적지까지 도보' if best['kind']=='walk' else best['name']
        decisions.append([t,node,state['w'],state['plan'][0],stage['rid'],best['kind'],name,
                          old if math.isfinite(old) else None,best_eta,reason])
        state['history']=state['history']+[[t,best['kind'],name]];state['last_switch']=t
        state['visited']=state['visited']|{node};state['check_version']+=1
        state['stages']=scaled_stages(best['stages'],factor);state['stage']=0
        access=best['walk'][1]*factor
        # A same-stop change joins behind the people already waiting, with no
        # invented additional walking or repeated completed boarding preparation.
        walk_next(state,t,best['walk'][0],access,0 if access<EPS else 20)
        return True
    for plan in prepared['plans'][day]:
        state={'sid':identity(),'plan':plan,'w':plan[3],'stage':0,'stages':plan[6],
               'factor':bundle['walk_scales'][str(plan[0])],'legs':[],'history':[],
               'last_switch':-math.inf,'visited':set(),'dest':bundle['destination_keys'][str(plan[0])],
               'queued':False,'done':False,'check_version':0}
        walk_next(state,plan[4],*plan[5])
    next_progress=START
    while heap:
        t,priority,_,kind,payload=heapq.heappop(heap)
        if next_progress<=t<=END:
            progress={'scenario':scenario,'weekday':day,'clock_seconds':t,
                      'queue_weight':math.fsum(qmass),'queued_states':sum(map(len,queues))}
            base.save(WORK/f'progress-{scenario}-{base.DAYS[day]}.json',progress)
            print('CITY_PROGRESS',json.dumps(progress,ensure_ascii=True),flush=True)
            next_progress=(int(t//7200)+1)*7200
        if kind=='ready':
            state=payload
            if state['done']:continue
            if maybe_switch(state,t,'arrival'):continue
            node=state['node'];state['queued']=True;queues[node].append(state);qmass[node]+=state['w'];queue_versions[node]+=1
            reschedule(state,t+settings['recheck_seconds']);continue
        if kind=='recheck':
            state,version=payload
            if not state['queued'] or state['done'] or version!=state['check_version']:continue
            if not maybe_switch(state,t,'queue_recheck'):reschedule(state,t+settings['recheck_seconds'])
            continue
        vid,k=payload;vehicle=vehicles[vid];rid=vehicle['rid'];info=ri[rid]
        before=vehicle['load'];remaining=[];off=0.
        for target,state in vehicle['onboard']:
            if target==k:
                off+=state['w'];stage=current_stage(state);state['stage']+=1
                walk_next(state,t,*stage['next_walk'])
            else:remaining.append((target,state))
        vehicle['onboard']=remaining;vehicle['load']-=off
        if abs(vehicle['load'])<EPS:vehicle['load']=0.
        if info.get('city'):node=bundle['city_node_lookup'].get(f'{rid}|{k}')
        else:node=lookup.get(f'{rid}|{k}') if k<info['n'] else None
        boarded=new_denied=eligible_left=0.
        if node is not None and t<=END:
            queue=queues[node];available=vehicle['cap']-vehicle['load']
            # Incompatible routes do not block people able to board this service.
            # FIFO is preserved among those eligible for this exact direction/seq.
            for state in list(queue):
                chosen=stage_choice(current_stage(state),rid,k)
                if chosen is None or available<=EPS:continue
                w=min(available,state['w']);stages=list(state['stages']);stages[state['stage']]=dict(chosen)
                take={**state,'sid':identity(),'w':w,'queued':False,'stages':stages}
                end_index=k+chosen['alight']-chosen['board'];end=vehicle['t0']+info['offsets'][end_index]
                record_wait(take,t,'boarded')
                take['legs']=take['legs']+[[3,t,end,chosen['ride_path'],node,-1,vid]]
                vehicle['onboard'].append((end_index,take));boarded+=w;available-=w;vehicle['load']+=w;qmass[node]-=w
                if state['w']-w<=EPS:state['queued']=False;queue.remove(state)
                else:state['w']-=w
                if 'pool' in current_stage(state):gate_boardings.append([t,rid,w,state['plan'][0]])
            if boarded>EPS:queue_versions[node]+=1
            for state in list(queue):
                if stage_choice(current_stage(state),rid,k) is None:continue
                eligible_left+=state['w'];assert available<EPS
                if state['first_denied']<0:state['first_denied']=t;new_denied+=state['w']
                reschedule(state,t+.001)
            events.append([t,node,vid,vehicle['cap'],before,off,boarded,vehicle['load'],
                           eligible_left,new_denied,max(0.,qmass[node]),rid])
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
    data=v4.export_run(prepared,day,scenario,finished,waits,events,vehicles,decisions,gate_boardings,checks,forecast_calls,False)
    city_nodes=set(common['city_nodes']);report=data['report']
    report.update(city_vehicle_runs=sum(not v['rid'].startswith('shuttle') for v in vehicles),
        city_boarding_weight=sum(w[3] for w in waits if w[0] in city_nodes and w[7]=='boarded'),
        city_denied_weight=sum(w[3] for w in waits if w[0] in city_nodes and w[4]>=0),
        city_unserved_weight=sum(w[3] for w in waits if w[0] in city_nodes and w[7]=='unserved'),
        city_route_count=sum(bool(info.get('city')) for info in ri.values()),city_capacity_applied=True,external_background_passengers_included=False,
        actual_route_vehicle_capacities_verified=False,
        late_arrival_weight=sum(s['w'] for s in finished if not s['unserved'] and s['finish_time']>END))
    data.update(schema_version=5,city_capacity_applied=True,
                event_columns=['time','node','vehicle','capacity','before','off','boarded','onboard','compatible_left','new_denied','physical_queue_left','route'])
    if export:
        base.OUT=OUT
        base.public(f'{scenario}-{base.DAYS[day]}.json',data)
        base.packed(WORK/f'audit-{scenario}-{base.DAYS[day]}.json.gz',{'waits':waits,'events':events,'report':report,
            'switches':decisions,'gate_boardings':gate_boardings,
            'legs':[{'id':s['plan'][0],'weight':s['w'],'unserved':s['unserved'],'history':s['history'],
                     'start':s['plan'][4],'legs':s['legs']} for s in finished]})
    print('CITY_DONE',scenario,day,json.dumps(report,ensure_ascii=True),flush=True)
    return data


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--day',choices=list(base.DAYS));parser.add_argument('--scenario',choices=list(base.SCENARIOS));args=parser.parse_args()
    start=time.perf_counter();bundle=prepare();OUT.mkdir(parents=True,exist_ok=True);base.OUT=OUT
    common=bundle['prepared']['common']
    common['city_route_stops']={rid:[{k:s.get(k) for k in ('id','seq','name','ars','lat','lon')} for s in route['stops']]
                               for rid,route in bundle['prepared']['routes'].items() if not rid.startswith('shuttle')}
    official={r['rid']:r['metadata'] for r in bundle['city_sources']['plans']['routes']}
    for row in common['city_services']:
        row['official_origin']=official[row['route_id']]['stStationNm']
        row['official_end']=official[row['route_id']]['edStationNm']
    base.public('common.json',common);charts={}
    for scenario in ([args.scenario] if args.scenario else base.SCENARIOS):
        charts[scenario]={}
        for day in ([args.day] if args.day else base.DAYS):
            d=simulate(bundle,day,scenario);charts[scenario][base.DAYS[day]]={k:d[k] for k in ('hourly','daily','report')}
    if not args.day and not args.scenario:
        old=base.read(base.ROOT/'public/data/capacity_v4/charts.json')
        base.public('charts.json',{'scenarios':charts,'legacy_wait_charts':old['legacy_wait_charts'],'adaptive':True,'city_capacity_applied':True})
    base.save(WORK/'run_verification.json',{'status':'PASS','settings':SETTINGS,'elapsed_seconds':time.perf_counter()-start,
        'runs':[v['report'] for s in charts.values() for v in s.values()],
        'previous_v3_v4_preserved':True,'city_reference_capacity_large':50,'city_reference_capacity_village':24,
        'capacities_are_verified_route_assignments':False,'historical_load_sum_used_as_seats':False})


if __name__=='__main__':main()
