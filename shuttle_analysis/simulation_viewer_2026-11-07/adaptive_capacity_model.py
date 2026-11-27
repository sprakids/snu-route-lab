"""Queue-observing rerouting. The forecast sees current state, not future arrivals."""
from pathlib import Path
from collections import deque,defaultdict,Counter
import bisect,hashlib,heapq,json,math,time,argparse
import numpy as np
import capacity_model as base
from prepare_adaptive import prepare,WORK,ROOT

OUT=ROOT/'public/data/capacity_v4'
START,END,EPS=base.START,base.END,base.EPS
SETTINGS={'recheck_seconds':60,'minimum_gain_seconds':120,'cooldown_seconds':180,'max_switches':2}

def city_departure(routes,rid,board,ready,day):
    """One deterministic common phase per route/day; planned interval, not live ETA."""
    h=float(routes[rid]['interval_minutes'])*60
    digest=hashlib.sha256(f'20261106|{day}|{rid}'.encode()).digest()
    phase=int.from_bytes(digest[:8],'big')/2**64*h
    # A consistent stop clock along a route. Only current/past state enters it.
    offset=0.
    for a,b in zip(routes[rid]['stops'][:board],routes[rid]['stops'][1:board+1]):
        offset+=max(float(b.get('segment_m') or 0),base.distance(base.point(a),base.point(b)))/5+15
    anchor=8*3600+phase+offset
    k=math.ceil((ready-anchor)/h-1e-10)
    result=anchor+max(k,math.ceil((8*3600-anchor)/h))*h
    return result if result<=END else math.inf

def queue_departure(schedule,vehicles,node,ready,ahead,weight=0.):
    """Use queue ahead and current modeled onboard destinations; no future inflows."""
    rows=schedule[node];i=bisect.bisect_left(rows,(ready-EPS,-1,-1))
    need=ahead+weight
    for when,vid,k in rows[i:]:
        v=vehicles[vid]
        if v['last_stop']>=k:continue
        occupied=sum(s['w'] for target,s in v['onboard'] if target>k)
        available=max(0.,v['cap']-occupied)
        if available<=EPS:continue
        if need<=available+EPS:return when
        need-=available
    return math.inf

def should_switch(now,old_eta,new_eta,count,last_switch,settings=SETTINGS):
    return (count<settings['max_switches'] and now-last_switch>=settings['cooldown_seconds']
            and math.isfinite(new_eta) and new_eta+settings['minimum_gain_seconds']<=old_eta)

def simulate(bundle,day,scenario,export=True,settings=None):
    settings={**SETTINGS,**(settings or {})};prepared=bundle['prepared'];common=prepared['common']
    routes=prepared['routes'];nodes=common['nodes'];ri=common['route_info']
    lookup={n['id']:i for i,n in enumerate(nodes)}
    heap=[];serial=0;state_serial=0;queues=[deque() for _ in nodes];qmass=[0.]*len(nodes)
    finished=[];waits=[];events=[];vehicles=[];decisions=[];gate_boardings=[];checks=0
    schedule=[[] for _ in nodes];forecast_calls=0
    def push(t,priority,kind,payload):
        nonlocal serial
        serial+=1;heapq.heappush(heap,(float(t),priority,serial,kind,payload))
    def state_id():
        nonlocal state_serial
        state_serial+=1;return state_serial
    for rid,info in ri.items():
        for clock in base.dispatches(rid,scenario):
            vid=len(vehicles);t0=clock-info['offsets'][info['anchor']]
            v={'id':vid,'rid':rid,'cap':25 if rid=='shuttle-41914' else 60,'t0':t0,
               'onboard':[],'load':0.,'legs':[],'last_stop':-1};vehicles.append(v)
            for k,offset in enumerate(info['offsets']):
                when=t0+offset;push(when,1,'vehicle',(vid,k))
                node=lookup.get(f'{rid}|{k}') if k<info['n'] else None
                if node is not None and when<=END:schedule[node].append((when,vid,k))
    for rows in schedule:rows.sort()
    def finish(s,unserved=False):
        s['queued']=False;s['done']=True;s['unserved']=unserved;finished.append(s)
    def record_wait(s,t,outcome):
        st=s['stages'][s['stage']];node=s['node']
        s['legs']=s['legs']+[[1,s['arrival'],t,st['wait_path'],node,s['first_denied'],-1]]
        waits.append([node,s['arrival'],t,s['w'],s['first_denied'],outcome=='unserved',s['plan'][0],outcome])
    def selected_city(st,ready):
        choices=st.get('pool',[st])
        choice=min(choices,key=lambda x:(city_departure(routes,x['rid'],x['board'],ready,day),x['rid']))
        return choice,city_departure(routes,choice['rid'],choice['board'],ready,day)
    def walk_next(s,t,path,duration):
        if duration>EPS:s['legs']=s['legs']+[[0,t,t+duration,path,-1,-1,-1,bool(s['history'])]]
        t+=duration
        if s['stage']>=len(s['stages']):finish(s);return
        st=s['stages'][s['stage']]
        if st['rid'].startswith('shuttle'):
            s.update(arrival=t,first_denied=-1,node=lookup[f"{st['rid']}|{st['board']}"])
            if t+20<=END:push(t+20,0,'ready',s)
            else:
                s['legs']=s['legs']+[[1,t,max(t,END)+1,st['wait_path'],s['node'],-1,-1]]
                if t<=END:waits.append([s['node'],t,END+1,s['w'],-1,True,s['plan'][0],'unserved'])
                finish(s,True)
        else:
            chosen,dep=selected_city(st,t+20) if st.get('dynamic_city') or 'pool' in st else (st,t+st['city_wait'])
            if dep>END:
                s['legs']=s['legs']+[[1,t,max(t,END)+1,st['wait_path'],-1,-1,-1]];finish(s,True);return
            end=dep+chosen['ride_seconds']
            s['legs']=s['legs']+[[1,t,dep,st['wait_path'],-1,-1,-1],
                                  [2,dep,end,chosen['ride_path'],-1,-1,-1,chosen['rid']]]
            if 'pool' in st:gate_boardings.append([dep,chosen['rid'],s['w'],s['plan'][0]])
            push(end,0,'city_alight',s)
    def forecast(stages,t,factor,first_node=None,ahead=0.,weight=0.):
        nonlocal forecast_calls
        forecast_calls+=1
        for i,st in enumerate(stages):
            if st['rid'].startswith('shuttle'):
                node=lookup[f"{st['rid']}|{st['board']}"]
                before=ahead if i==0 and node==first_node else qmass[node]
                dep=queue_departure(schedule,vehicles,node,t+20,before,weight)
                if not math.isfinite(dep):return math.inf
                # Actual shuttle timing is indexed by stop offsets, not a separate
                # approximate ride duration used only by candidate pruning.
                t=dep+ri[st['rid']]['offsets'][st['alight']]-ri[st['rid']]['offsets'][st['board']]
            elif st.get('dynamic_city') or 'pool' in st:
                chosen,dep=selected_city(st,t+20);t=dep+chosen['ride_seconds']
            else:t+=st['city_wait']+st['ride_seconds']
            t+=st['next_walk'][1]*factor
        return t
    def reschedule(s,t):
        s['check_version']+=1
        if t<=END:push(t,2,'recheck',(s,s['check_version']))
    def maybe_switch(s,t,ahead,reason):
        if len(s['history'])>=settings['max_switches'] or t-s['last_switch']<settings['cooldown_seconds']:return False
        node=s['node'];factor=s['factor'];st=s['stages'][s['stage']]
        old=forecast(s['stages'][s['stage']:],max(t-20,s['arrival']),1.,node,ahead,s['w'])
        best=None;best_eta=old
        for option in bundle['alternatives'][f"{node}|{s['dest']}"]:
            stages=option['stages']
            if stages and stages[0]['rid'].startswith('shuttle'):
                first=lookup[f"{stages[0]['rid']}|{stages[0]['board']}"]
                if first==node or first in s['visited']:continue
            # A traveller already on a two-ride path can still leave for a new
            # local alternative; the two-change cap and visited set prevent loops.
            eta=forecast(stages,t+option['walk'][1]*factor,factor,weight=s['w']) if stages else t+option['walk'][1]*factor
            if eta<best_eta:best_eta=eta;best=option
        if best is None or not should_switch(t,old,best_eta,len(s['history']),s['last_switch'],settings):return False
        if s['queued']:
            queues[node].remove(s);qmass[node]-=s['w'];s['queued']=False
        record_wait(s,t,'switched')
        newname='목적지까지 도보' if best['kind']=='walk' else best['name']
        record=[t,node,s['w'],s['plan'][0],st['rid'],best['kind'],newname,
            old if math.isfinite(old) else None,best_eta,reason]
        decisions.append(record)
        s['history']=s['history']+[[t,best['kind'],newname]];s['last_switch']=t
        s['visited']=s['visited']|{node};s['check_version']+=1
        # Alternative walking times use this same particle's speed multiplier.
        s['stages']=[{**x,'next_walk':[x['next_walk'][0],x['next_walk'][1]*factor]} for x in best['stages']]
        s['stage']=0
        walk_next(s,t,best['walk'][0],best['walk'][1]*factor)
        return True
    # Stored original next-walk durations already carry the individual factor.
    # The stay forecast uses factor 1; raw alternative candidates use factor.
    for plan in prepared['plans'][day]:
        factor=bundle['walk_scales'][str(plan[0])]
        s={'sid':state_id(),'plan':plan,'w':plan[3],'stage':0,'stages':plan[6],
           'factor':factor,'legs':[],'history':[],'last_switch':-math.inf,
           'visited':set(),'dest':bundle['destination_keys'][str(plan[0])],
           'queued':False,'done':False,'check_version':0}
        walk_next(s,plan[4],*plan[5])
    while heap:
        t,priority,_,kind,payload=heapq.heappop(heap)
        if kind=='ready':
            s=payload
            if s['done']:continue
            if maybe_switch(s,t,qmass[s['node']],'arrival'):continue
            node=s['node'];s['queued']=True;queues[node].append(s);qmass[node]+=s['w']
            reschedule(s,t+settings['recheck_seconds']);continue
        if kind=='recheck':
            s,version=payload
            if not s['queued'] or s['done'] or s['check_version']!=version:continue
            ahead=0.
            for other in queues[s['node']]:
                if other is s:break
                ahead+=other['w']
            if not maybe_switch(s,t,ahead,'queue_recheck'):reschedule(s,t+settings['recheck_seconds'])
            continue
        if kind=='city_alight':
            s=payload;st=s['stages'][s['stage']];s['stage']+=1;walk_next(s,t,*st['next_walk']);continue
        vid,k=payload;v=vehicles[vid];info=ri[v['rid']];before=v['load'];remaining=[];off=0.
        for target,s in v['onboard']:
            if target==k:
                off+=s['w'];st=s['stages'][s['stage']];s['stage']+=1;walk_next(s,t,*st['next_walk'])
            else:remaining.append((target,s))
        v['onboard']=remaining;v['load']-=off
        if abs(v['load'])<EPS:v['load']=0.
        node=lookup.get(f"{v['rid']}|{k}") if k<info['n'] else None
        boarded=new_denied=0.;left=0.
        if node is not None and t<=END:
            queue=queues[node];available=v['cap']-v['load']
            while queue and available>EPS:
                s=queue[0];w=min(available,s['w']);take={**s,'sid':state_id(),'w':w,'queued':False}
                st=s['stages'][s['stage']];end_index=k+st['alight']-st['board'];end=v['t0']+info['offsets'][end_index]
                record_wait(take,t,'boarded')
                take['legs']=take['legs']+[[3,t,end,st['ride_path'],node,-1,vid]]
                v['onboard'].append((end_index,take));boarded+=w;available-=w;v['load']+=w;qmass[node]-=w
                if s['w']-w<=EPS:s['queued']=False;queue.popleft()
                else:s['w']-=w
            left=max(0.,qmass[node])
            if left>EPS:
                assert available<EPS
                for s in list(queue):
                    if s['first_denied']<0:s['first_denied']=t;new_denied+=s['w']
                    reschedule(s,t+.001)
            events.append([t,node,vid,v['cap'],before,off,boarded,v['load'],left,new_denied])
        v['last_stop']=k
        assert -EPS<=v['load']<=v['cap']+EPS
        checks+=1
        if k<len(info['segments']) and (k<info['n'] or v['load']>EPS):
            v['legs'].append([t,v['t0']+info['offsets'][k+1],info['segments'][k],round(v['load'],6)])
    for queue in queues:
        for s in queue:record_wait(s,END+1,'unserved');finish(s,True)
    assert all(v['load']<EPS for v in vehicles)
    assert abs(sum(s['w'] for s in finished)-sum(p[3] for p in prepared['plans'][day]))<1e-5
    return export_run(prepared,day,scenario,finished,waits,events,vehicles,decisions,gate_boardings,checks,forecast_calls,export)

def export_run(prepared,day,scenario,finished,waits,events,vehicles,decisions,gate_boardings,checks,forecast_calls,export):
    common=prepared['common'];nodes=common['nodes'];frame_step=5;frames=(END-START)//frame_step+1
    diff=np.zeros((2,len(nodes),frames+1));hourly=defaultdict(list);daily=defaultdict(list)
    changes=[defaultdict(lambda:[0.,0.]) for _ in nodes]
    def add(which,node,a,b,w):
        i=max(0,int(math.ceil((a-START)/frame_step-1e-8)));j=min(frames,int(math.ceil((b-START)/frame_step-1e-8)))
        if i<j:diff[which,node,i]+=w;diff[which,node,j]-=w
    for row in waits:
        node,a,b,w,denied,unserved,identity,outcome=row;add(0,node,a,b,w)
        changes[node][a][0]+=w;changes[node][b][0]-=w
        if denied>=0:
            add(1,node,denied,b,w);changes[node][denied][1]+=w;changes[node][b][1]-=w
        if START<=a<END:hourly[node,int(a//3600)].append(row);daily[node].append(row)
    def stats(rows):
        served=[r for r in rows if r[7]=='boarded'];sw=sum(r[3] for r in served);total=sum(r[3] for r in rows)
        return {'arrival_weight':total,'served_weight':sw,'unserved_weight':sum(r[3] for r in rows if r[7]=='unserved'),
            'switched_weight':sum(r[3] for r in rows if r[7]=='switched'),
            'mean_wait_min':sum((r[2]-r[1])*r[3] for r in served)/sw/60 if sw>EPS else None,
            'p90_wait_min':base.percentile([((r[2]-r[1])/60,r[3]) for r in served],.9),
            'mean_queue_exposure_min':sum((r[2]-r[1])*r[3] for r in rows)/total/60 if total>EPS else None,
            'denied_weight':sum(r[3] for r in rows if r[4]>=0),
            'denied_share':sum(r[3] for r in rows if r[4]>=0)/total if total>EPS else None}
    hour_stats={str(n):{str(h):stats(hourly[n,h]) for h in range(11,24)} for n in range(len(nodes))}
    day_stats={str(n):stats(daily[n]) for n in range(len(nodes))}
    values=np.cumsum(diff,axis=2)[:,:,:frames].transpose(0,2,1);assert values.min()>-1e-5;values=np.maximum(values,0)
    timelines=[]
    for ch in changes:
        q=d=0.;rows=[]
        for t,(dq,dd) in sorted(ch.items()):
            q+=dq;d+=dd;assert q>-1e-5 and d>-1e-5 and d<=q+1e-5
            if t<=END:rows.append([round(t,3),round(max(0.,q),6),round(max(0.,d),6)])
        timelines.append(rows)
    trips=[]
    for s in finished:
        p=s['plan'];legs=s['legs']
        if not legs or legs[0][1]>END or legs[-1][2]<START:continue
        for a,b in zip(legs,legs[1:]):assert abs(a[2]-b[1])<1e-5,(a,b)
        signature=f"{p[0]}|{s['w']:.7f}|"+';'.join(f'{l[0]}:{l[1]:.3f}:{l[2]:.3f}' for l in legs if l[0] in (1,3))
        digest=hashlib.sha256(signature.encode()).digest();full=int(s['w']//2);tail=s['w']-full*2
        count=full+(int.from_bytes(digest[:8],'big')/2**64<tail/2)
        compact=[[l[0],round(l[1],3),round(l[2],3),*l[3:5],round(l[5],3),*l[6:]] for l in legs if l[2]-l[1]>EPS]
        for i in range(count):
            identity=int.from_bytes(hashlib.sha256(digest+i.to_bytes(4,'big')).digest()[:4],'big')
            trips.append([identity,p[1],p[2],2,compact,s['unserved'],s['history'],p[0]])
    bus_export=[[v['id'],v['rid'],v['cap'],v['legs']] for v in vehicles if any(l[0]<=END and l[1]>=START for l in v['legs'])]
    highlights=sorted([e for e in events if START<=e[0]<END and e[8]>1],key=lambda e:e[8],reverse=True)[:10]
    mass=sum(p[3] for p in prepared['plans'][day]);served=[s for s in finished if not s['unserved']]
    sw=sum(s['w'] for s in served)
    report={'scenario':scenario,'weekday':day,'input_weight':mass,'final_weight':sum(s['w'] for s in finished),
        'finished_weight':sw,'unserved_trip_weight':sum(s['w'] for s in finished if s['unserved']),
        'full_particles':len(prepared['plans'][day]),'render_dots':len(trips),'capacity_checks':checks,
        'capacity_violations':0,'queue_min':float(values.min()),'max_queue':float(values[0].max()),
        'vehicles':len(vehicles),'boarding_events':sum(w[7]=='boarded' for w in waits),
        'switch_event_weight':sum(x[2] for x in decisions),'switched_trip_weight':sum(s['w'] for s in finished if s['history']),
        'gate_boarding_weight':sum(x[2] for x in gate_boardings),'forecast_calls':forecast_calls,
        'mean_finished_trip_minutes':sum((s['legs'][-1][2]-s['plan'][4])*s['w'] for s in served)/sw/60 if sw else None}
    data={'schema_version':4,'scenario':scenario,'day':day,'trips':trips,'queue_step_seconds':frame_step,
        'queues':np.round(values[0],3).tolist(),'denied_queues':np.round(values[1],3).tolist(),
        'queue_timeline':timelines,'vehicles':bus_export,'events':events,'hourly':hour_stats,'daily':day_stats,
        'highlights':highlights,'report':report,'switches':decisions,'gate_boardings':gate_boardings}
    if export:
        base.public(f'{scenario}-{base.DAYS[day]}.json',data)
        base.packed(WORK/f'audit-{scenario}-{base.DAYS[day]}.json.gz',{'waits':waits,'events':events,'report':report,
            'switches':decisions,'gate_boardings':gate_boardings,
            'legs':[{'id':s['plan'][0],'weight':s['w'],'unserved':s['unserved'],'history':s['history'],
                     'start':s['plan'][4],'legs':s['legs']} for s in finished]})
    print('ADAPTIVE',scenario,day,json.dumps(report,ensure_ascii=False),flush=True)
    return data

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--day',choices=list(base.DAYS));ap.add_argument('--scenario',choices=list(base.SCENARIOS));args=ap.parse_args()
    began=time.perf_counter();bundle=prepare();OUT.mkdir(parents=True,exist_ok=True);base.OUT=OUT
    base.public('common.json',bundle['prepared']['common']);charts={}
    for scenario in ([args.scenario] if args.scenario else base.SCENARIOS):
        charts[scenario]={}
        for day in ([args.day] if args.day else base.DAYS):
            d=simulate(bundle,day,scenario);charts[scenario][base.DAYS[day]]={k:d[k] for k in ('hourly','daily','report')}
    if not args.day and not args.scenario:
        legacy=base.read(base.BASE/'waiting_time_estimates_2026-11-07/outputs_v2/chart_configs.json')
        base.public('charts.json',{'scenarios':charts,'legacy_wait_charts':legacy,'adaptive':True})
    base.save(WORK/'run_verification.json',{'status':'PASS','settings':SETTINGS,'route_choice':'original starting plans; queue-observing reroute',
        'elapsed_seconds':time.perf_counter()-began,'runs':[v['report'] for s in charts.values() for v in s.values()],
        'original_v3_preserved':True})

if __name__=='__main__':main()
