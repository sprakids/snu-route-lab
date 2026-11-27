"""Capacity-constrained weighted FIFO replay, isolated from the route recommendation app.

All course-demand particles, not the display sample, enter the queues. Route choices
are preserved; boarding delays propagate to downstream walking and transfers.
Headway scenarios are planned service assumptions, never observed vehicle traces.
"""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
from collections import defaultdict,Counter,deque
from datetime import datetime,timezone
import ast,csv,gzip,hashlib,heapq,importlib.util,json,math,shutil,time
import numpy as np

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent
WORK=ROOT/'capacity_model'
OUT=ROOT/'public/data/capacity_v2'
OLD=ROOT/'model_snapshot'
PRE=BASE/'scenario_comparison_2026-11-07/simulation_outputs'
START,END=680*60,1390*60
DAYS={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}
EPS=1e-7
SCENARIOS={'regular':{'label':'기준 배차','snu_peak':240,'circle_peak':360},
           'peak':{'label':'피크 최소 간격','snu_peak':180,'circle_peak':300}}
HOT=[('shuttle-41841','snu-410','admin_snu'),('shuttle-daehak','snu-410','admin_daehak'),
     ('shuttle-41946','snu-901','circle_302'),('shuttle-41946','snu-1001','circle_301'),
     ('shuttle-41914','snu-901','reverse_302'),('shuttle-41914','snu-1001','reverse_301')]
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,obj):Path(p).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def packed(p,obj):
    raw=json.dumps(obj,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    Path(p).write_bytes(gzip.compress(raw,compresslevel=6,mtime=0))
def public(name,obj):
    p=OUT/name;raw=json.dumps(obj,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    p.write_bytes(raw);Path(str(p)+'.gz').write_bytes(gzip.compress(raw,compresslevel=9,mtime=0))
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def distance(a,b):
    r=math.pi/180;return 6371000*math.hypot((b[0]-a[0])*r,(b[1]-a[1])*r*math.cos((a[0]+b[0])/2*r))
def point(s):return [s['lat'],s['lon']]
def segment_seconds(a,b):
    straight=distance(point(a),point(b));reported=b.get('segment_m',0)
    metres=reported if straight*.7<=reported<=max(200,straight*3) else straight*1.2
    return metres/5+15

class Geometry:
    def __init__(self,walker,routes):
        self.walker=walker;self.routes=routes;self.keys={};self.requests=[]
    def pid(self,kind,a=None,b=None,rid=None,i=None,j=None):
        k=(kind,tuple(a) if a is not None else None,tuple(b) if b is not None else None,rid,i,j)
        if k not in self.keys:self.keys[k]=len(self.requests);self.requests.append(k)
        return self.keys[k]
    def resolve(self):
        road=read(OLD/'road_geometry.json')['routes'];drive=None
        source=(BASE/'app/prepare_geometry.py').read_text(encoding='utf-8')
        definition=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='DriveGraph')
        ns={'math':math,'heapq':heapq,'meters':distance}
        exec(compile(ast.Module(body=[definition],type_ignores=[]),'local_saved_drive_graph','exec'),ns)
        answer=[None]*len(self.requests);sources=Counter();last_origin=None;parents=None
        for number,index in enumerate(sorted(range(len(self.requests)),key=lambda k:str(self.requests[k][:2]))):
            kind,a,b,rid,i,j=self.requests[index]
            if kind=='point':pts=[a];sources['stop_point']+=1
            elif kind=='walk':
                na,_=self.walker.snaps[a];nb,_=self.walker.snaps[b]
                if na!=last_origin:costs,parents=self.walker.graph.tree(na);last_origin=na
                assert nb==na or nb in parents
                chain=[nb]
                while chain[-1]!=na:chain.append(parents[chain[-1]][0])
                pts=[a]+[self.walker.graph.nodes[n] for n in reversed(chain)]+[b]
                sources['preserved_walking_graph']+=1
            else:
                segments=road.get(rid,{}).get('segments',[]);st=self.routes[rid]['stops'];pts=[]
                for k in range(i,j):
                    if k<len(segments) and segments[k] and segments[k].get('geometry'):
                        part=segments[k]['geometry'];sources['saved_road_segment']+=1
                    else:
                        if drive is None:drive=ns['DriveGraph'](read(BASE/'app/data/roads_osm.json'))
                        part=drive.path(point(st[k]),point(st[k+1]));assert part,(rid,k)
                        sources['saved_osm_drive_graph']+=1
                    pts.extend(part if not pts else part[1:])
            compact=[]
            for p in pts:
                v=[round(float(p[0]),6),round(float(p[1]),6)]
                if not compact or compact[-1]!=v:compact.append(v)
            assert compact;answer[index]=compact
            if number and number%500==0:print('saved geometry',number,'/',len(answer),flush=True)
        return answer,dict(sources)

def prepare():
    inputs=[OLD/'engine/simulate_stop_inflow.py',OLD/'instrumented_run.py',OLD/'app/routing.py',
            OLD/'app/data/network.json',OLD/'app/data/shuttle_network.json',OLD/'app/data/walking_osm.json',
            PRE/'input_snapshot/course_endings_current.json',PRE.parent/'scenario_specs.json',
            OLD/'road_geometry.json',BASE/'app/data/roads_osm.json',BASE/'app/prepare_geometry.py']
    hashes={str(p):sha(p) for p in inputs};cache=WORK/'prepared.json.gz'
    if cache.exists():
        assert read(WORK/'input_manifest.json')==hashes,'Preserved replay inputs changed; do not reuse stale cache.'
        cached=json.loads(gzip.decompress(cache.read_bytes()))
        cached['common']['queue_phases']=1
        return cached,hashes
    WORK.mkdir(exist_ok=True)
    runtime=WORK/'runtime';(runtime/'sources').mkdir(parents=True,exist_ok=True);(runtime/'outputs').mkdir(exist_ok=True)
    for n in ('campus_buildings.json','campus_bus_stops.json'):shutil.copy2(OLD/'runtime/sources'/n,runtime/'sources'/n)
    engine=module('capacity_preserved_engine',OLD/'engine/simulate_stop_inflow.py');engine.ROOT=runtime
    captured={};original=engine.MatrixWalker
    class Walker(original):
        def __init__(self,*a,**k):super().__init__(*a,**k);captured['walker']=self
    engine.MatrixWalker=Walker
    events=[e for e in read(inputs[6]) if e['included_main'] and e['weekday'] in DAYS and e['end_minute']<=engine.END]
    assert len(events)==6201
    print('Building preserved candidates for all weighted particles.',flush=True)
    choices,routes,destinations,_=engine.build_candidates(events)
    geo=Geometry(captured['walker'],routes)
    spec=read(inputs[7])['scenarios'][0];rho=spec['dorm_share'];q=spec['immediate_trip_share']
    shares={'dorm':rho*q,**{g:(1-rho)*x*q for g,x in zip(('snu','nak','daehak'),spec['external_mix'])}}
    plans=defaultdict(list);mass=Counter();uid=0
    def collect(e,group,c,mask,arrivals,ride_departures,departure,scale,weight,dest):
        nonlocal uid
        w=weight*shares[group];mass[e['weekday']]+=int(mask.sum())*w
        origin=[e['lat'],e['lon']];target=destinations[dest]
        for particle in np.flatnonzero(mask):
            uid+=1;factor=float(scale[particle]);start=float(departure[particle]);rides=c['rides']
            if not rides:
                p=geo.pid('walk',origin,target)
                plans[e['weekday']].append([uid,str(e['building']),group,w,start,[p,c['first_walk']['seconds']*factor],[]])
                continue
            first=routes[rides[0]['route_id']]['stops'][rides[0]['board']]
            walk=[geo.pid('walk',origin,point(first)),c['first_walk']['seconds']*factor]
            stages=[]
            for stage,r in enumerate(rides):
                route=routes[r['route_id']];a=route['stops'][r['board']];b=route['stops'][r['alight']]
                if stage+1<len(rides):
                    nr=rides[stage+1];next_stop=routes[nr['route_id']]['stops'][nr['board']]
                    nextwalk=[geo.pid('walk',point(b),point(next_stop)),c['transfer_walk']['seconds']*factor]
                else:nextwalk=[geo.pid('walk',point(b),target),c['last_walk']['seconds']*factor]
                stages.append({'rid':r['route_id'],'board':r['board'],'alight':r['alight'],
                    'ride_path':geo.pid('bus',rid=r['route_id'],i=r['board'],j=r['alight']),
                    'wait_path':geo.pid('point',point(a)),
                    'city_wait':float(ride_departures[stage][particle]-arrivals[stage][particle]),
                    'ride_seconds':r['ride_seconds'],'next_walk':nextwalk})
            plans[e['weekday']].append([uid,str(e['building']),group,w,start,walk,stages])
    engine._collect_viewer=collect
    exec(compile((OLD/'instrumented_run.py').read_text(encoding='utf-8'),str(OLD/'instrumented_run.py'),'exec'),engine.__dict__)
    replay=engine.run_viewer(events,choices,routes,engine.SEED)
    reference=engine.run_rep(events,choices,routes,engine.SEED)
    assert all(replay[i]==reference[i] for i in (0,1,4))
    expected=Counter()
    for e in events:expected[e['weekday']]+=e['enrollment']*.5
    assert all(abs(mass[d]-expected[d])<1e-6 for d in DAYS)
    nodes=[];node_lookup={};route_info={};hot={}
    for rid,r in routes.items():
        if not rid.startswith('shuttle'):continue
        n=r.get('cycle_length') or len(r['stops']);segments=[];offsets=[0.]
        # Full unrolled geometry supports passengers alighting after a loop boundary.
        for i in range(len(r['stops'])-1):
            segments.append(geo.pid('bus',rid=rid,i=i,j=i+1))
            offsets.append(offsets[-1]+segment_seconds(r['stops'][i],r['stops'][i+1]))
        for i,s in enumerate(r['stops'][:n]):
            if not s.get('board_allowed',True):continue
            k=len(nodes);node_lookup[f'{rid}|{i}']=k
            label=f"{s['name']} · {r['name']}"
            for rr,sid,hid in HOT:
                if rr==rid and s['id']==sid:hot[hid]=k
            nodes.append({'id':f'{rid}|{i}','route':rid,'board':i,'stop_id':s['id'],'name':s['name'],
                          'label':label,'lat':s['lat'],'lon':s['lon']})
        route_info[rid]={'n':n,'offsets':offsets,'segments':segments,
                         'anchor':next(i for i,s in enumerate(r['stops'][:n]) if s['id']==('snu-410' if rid in ('shuttle-41841','shuttle-daehak') else 'snu-901'))}
    paths,sources=geo.resolve()
    common=read(ROOT/'public/data/common.json')
    common.update(schema_version=2,paths=paths,nodes=nodes,hot_nodes=hot,route_info=route_info,
        movement_capacity_applied=True,scenarios=SCENARIOS,movement_seed=engine.SEED,queue_phases=1,
        source_note='전체 가중 흐름을 정원 제한 FIFO에 입력한 모형. 실제 GPS가 아닙니다.',
        peak_window_seconds=[900*60,1140*60],capacity_large=60,capacity_reverse=25,
        clock_note='공유된 예시 출발시각 1개. 실제 배차표·차량회전 검증은 미확보.',
        queue_note='같은 이동 입자의 정원 제한 대기열. 환승 지연도 전파됩니다.')
    result={'common':common,'routes':routes,'plans':plans,'expected':dict(expected),'geometry_sources':sources,
            'replay_bins_identical':True,'replay_modes_identical':True,'cache_version':1}
    assert hashes=={str(p):sha(p) for p in inputs}
    packed(cache,result);save(WORK/'input_manifest.json',hashes)
    print('Preserved full replay cached; plans',sum(map(len,plans.values())),flush=True)
    return result,hashes

def series(a,b,h,include_end=False):
    return list(np.arange(a,b+(EPS if include_end else -EPS),h))
def dispatches(rid,scenario):
    c=SCENARIOS[scenario]
    if rid=='shuttle-41841':
        ts=series(420*60,480*60,900)+series(480*60,660*60,240)+series(660*60,900*60,600)+series(900*60,1140*60,c['snu_peak'])+series(1140*60,1200*60,900)+series(1200*60,1260*60,1800)
    elif rid=='shuttle-daehak':
        ts=series(420*60,480*60,900)+series(480*60,660*60,390)+series(660*60,1140*60,600)+[1140*60]
    elif rid=='shuttle-41946':
        ts=series(480*60,900*60,360)+series(900*60,1140*60,c['circle_peak'])+series(1140*60,1260*60,1200)+[1260*60]
    else:ts=series(590*60,1030*60,1200,True)
    if rid in ('shuttle-41841','shuttle-daehak'):
        # Two separate 60-capacity vehicles, not a fictitious 120-capacity bus.
        ts += [t*60 for t in (1270,1300,1330,1360,1390) for _ in range(2)]
    return sorted(map(float,ts))

def percentile(values,q):
    if not values:return None
    rows=sorted(values);threshold=sum(w for v,w in rows)*q;acc=0
    for v,w in rows:
        acc+=w
        if acc>=threshold-EPS:return v
    return rows[-1][0]

def simulate(prepared,day,scenario,export=True,audit_sink=None):
    common=prepared['common'];routes=prepared['routes'];nodes=common['nodes'];ri=common['route_info']
    node_lookup={n['id']:i for i,n in enumerate(nodes)}
    heap=[];serial=0;queues=[deque() for _ in nodes];finished=[];waits=[];events=[];vehicles=[]
    qmass=[0.]*len(nodes);mass_in=sum(p[3] for p in prepared['plans'][day]);capacity_checks=0
    def push(t,priority,kind,payload):
        nonlocal serial
        serial+=1;heapq.heappush(heap,(float(t),priority,serial,kind,payload))
    def finish(state,unserved=False):
        state['unserved']=unserved;finished.append(state)
    def walk_next(state,t,path,duration):
        if duration>EPS:state['legs']=state['legs']+[[0,t,t+duration,path,-1,-1,-1]]
        t+=duration
        if state['stage']>=len(state['plan'][6]):finish(state);return
        stage=state['plan'][6][state['stage']];state['arrival']=t;state['first_denied']=-1
        if stage['rid'].startswith('shuttle'):
            node=node_lookup[f"{stage['rid']}|{stage['board']}"];state['node']=node
            if t+20<=END+EPS:push(t+20,0,'ready',state)
            else:
                state['legs']=state['legs']+[[1,t,max(t,END)+1,stage['wait_path'],node,-1,-1]]
                if t<=END:waits.append([node,t,END+1,state['w'],-1,True,state['plan'][0]])
                finish(state,True)
        else:
            dep=t+stage['city_wait']
            if dep>END:
                state['legs']=state['legs']+[[1,t,max(t,END)+1,stage['wait_path'],-1,-1,-1]];finish(state,True);return
            state['legs']=state['legs']+[[1,t,dep,stage['wait_path'],-1,-1,-1],[2,dep,dep+stage['ride_seconds'],stage['ride_path'],-1,-1,-1]]
            push(dep+stage['ride_seconds'],0,'city_alight',state)
    for plan in prepared['plans'][day]:
        state={'plan':plan,'w':plan[3],'stage':0,'legs':[]}
        walk_next(state,plan[4],*plan[5])
    for rid,info in ri.items():
        for clock in dispatches(rid,scenario):
            t0=clock-info['offsets'][info['anchor']];vid=len(vehicles);cap=25 if rid=='shuttle-41914' else 60
            v={'id':vid,'rid':rid,'cap':cap,'t0':t0,'onboard':[],'load':0.,'legs':[]}
            vehicles.append(v)
            for k,offset in enumerate(info['offsets']):
                # The second unrolled loop is alighting-only, never a second dispatch.
                push(t0+offset,1,'vehicle',(vid,k))
    while heap:
        t,priority,_,kind,payload=heapq.heappop(heap)
        if kind=='ready':
            node=payload['node'];queues[node].append(payload);qmass[node]+=payload['w'];continue
        if kind=='city_alight':
            st=payload['plan'][6][payload['stage']];payload['stage']+=1
            walk_next(payload,t,*st['next_walk']);continue
        vid,k=payload;v=vehicles[vid];info=ri[v['rid']];before=v['load'];remaining=[];off=0.
        for target,state in v['onboard']:
            if target==k:
                off+=state['w'];stage=state['plan'][6][state['stage']];state['stage']+=1
                walk_next(state,t,*stage['next_walk'])
            else:remaining.append((target,state))
        v['onboard']=remaining;v['load']-=off
        if abs(v['load'])<EPS:v['load']=0.
        node=node_lookup.get(f"{v['rid']}|{k}") if k<info['n'] else None
        boarded=0.;new_denied=0.;left=0.
        if node is not None and t<=END+EPS:
            queue=queues[node];available=v['cap']-v['load']
            while queue and available>EPS:
                state=queue[0];w=min(available,state['w']);take={**state,'w':w}
                stage=state['plan'][6][state['stage']];end_index=k+stage['alight']-stage['board']
                assert end_index<len(info['offsets']),(v['rid'],k,end_index)
                end=v['t0']+info['offsets'][end_index]
                take['legs']=state['legs']+[[1,state['arrival'],t,stage['wait_path'],node,state['first_denied'],-1],
                                           [3,t,end,stage['ride_path'],node,-1,vid]]
                waits.append([node,state['arrival'],t,w,state['first_denied'],False,state['plan'][0]])
                v['onboard'].append((end_index,take));boarded+=w;available-=w;v['load']+=w;qmass[node]-=w
                if state['w']-w<=EPS:queue.popleft()
                else:state['w']-=w
            left=max(0.,qmass[node])
            if left>EPS:
                assert available<EPS
                for state in queue:
                    if state['first_denied']<0:state['first_denied']=t;new_denied+=state['w']
            events.append([t,node,vid,v['cap'],before,off,boarded,v['load'],left,new_denied])
        assert -EPS<=v['load']<=v['cap']+EPS,(v['rid'],k,v['load'])
        capacity_checks+=1
        if k<len(info['segments']) and (k<info['n'] or v['load']>EPS):
            v['legs'].append([t,v['t0']+info['offsets'][k+1],info['segments'][k],round(v['load'],6)])
    for node,queue in enumerate(queues):
        for state in queue:
            st=state['plan'][6][state['stage']]
            state['legs']=state['legs']+[[1,state['arrival'],END+1,st['wait_path'],node,state['first_denied'],-1]]
            waits.append([node,state['arrival'],END+1,state['w'],state['first_denied'],True,state['plan'][0]])
            finish(state,True)
    assert all(v['load']<EPS for v in vehicles),'All modeled boarded particles must alight.'
    mass_out=sum(s['w'] for s in finished)
    assert abs(mass_out-mass_in)<1e-5,(mass_out,mass_in)
    frame_step=5;frames=(END-START)//frame_step+1
    diff=np.zeros((2,len(nodes),frames+1))
    hourly=defaultdict(list);daily=defaultdict(list);queue_changes=[defaultdict(lambda:[0.,0.]) for _ in nodes]
    def add(which,node,a,b,w):
        i=max(0,int(math.ceil((a-START)/frame_step-1e-8)));j=min(frames,int(math.ceil((b-START)/frame_step-1e-8)))
        if i<j:diff[which,node,i]+=w;diff[which,node,j]-=w
    for row in waits:
        node,a,b,w,denied,unserved,identity=row;add(0,node,a,b,w)
        queue_changes[node][a][0]+=w;queue_changes[node][b][0]-=w
        if denied>=0:
            add(1,node,denied,b,w);queue_changes[node][denied][1]+=w;queue_changes[node][b][1]-=w
        if START<=a<END:
            hourly[(node,int(a//3600))].append(row);daily[node].append(row)
    def stats(rows):
        served=[r for r in rows if not r[5]];total=sum(r[3] for r in rows);sw=sum(r[3] for r in served)
        return {'arrival_weight':round(total,6),'served_weight':round(sw,6),'unserved_weight':round(total-sw,6),
            'mean_wait_min':sum((r[2]-r[1])*r[3] for r in served)/sw/60 if sw>EPS else None,
            'p90_wait_min':percentile([((r[2]-r[1])/60,r[3]) for r in served],.9),
            'denied_weight':sum(r[3] for r in rows if r[4]>=0),
            'denied_share':sum(r[3] for r in rows if r[4]>=0)/total if total>EPS else None}
    hour_stats={str(n):{str(h):stats(hourly[(n,h)]) for h in range(11,24)} for n in range(len(nodes))}
    day_stats={str(n):stats(daily[n]) for n in range(len(nodes))}
    values=np.cumsum(diff,axis=2)[:,:,:frames].transpose(0,2,1)
    assert float(values.min())>-1e-5
    values=np.maximum(values,0)
    timelines=[]
    for changes in queue_changes:
        total=0.;denied=0.;rows=[]
        for t,(dq,dd) in sorted(changes.items()):
            total+=dq;denied+=dd
            assert total>-1e-5 and denied>-1e-5 and denied<=total+1e-5
            if t<=END:rows.append([round(t,3),round(max(0.,total),6),round(max(0.,denied),6)])
        timelines.append(rows)
    trips=[]
    for s in finished:
        p=s['plan'];legs=s['legs']
        if not legs or legs[0][1]>END or legs[-1][2]<START:continue
        for a,b in zip(legs,legs[1:]):assert abs(a[2]-b[1])<1e-5,(a,b)
        # Render weighted sample only after the exact full-flow capacity calculation.
        signature=f"{p[0]}|{s['w']:.7f}|"+';'.join(f'{l[0]}:{l[1]:.3f}:{l[2]:.3f}' for l in legs if l[0] in (1,3))
        digest=hashlib.sha256(signature.encode()).digest();full=int(s['w']//2);tail=s['w']-full*2
        count=full+(int.from_bytes(digest[:8],'big')/2**64<tail/2)
        compact=[[l[0],round(l[1],3),round(l[2],3),*l[3:5],round(l[5],3),l[6]] for l in legs if l[2]-l[1]>EPS]
        for i in range(count):
            identity=int.from_bytes(hashlib.sha256(digest+i.to_bytes(4,'big')).digest()[:4],'big')
            trips.append([identity,p[1],p[2],2,compact,s['unserved']])
    bus_export=[[v['id'],v['rid'],v['cap'],v['legs']] for v in vehicles if any(l[0]<=END and l[1]>=START for l in v['legs'])]
    highlights=sorted([e for e in events if START<=e[0]<END and e[8]>1],key=lambda e:e[8],reverse=True)
    hotset=set(common['hot_nodes'].values());upper={common['hot_nodes'][k] for k in ('circle_302','circle_301','reverse_302','reverse_301')}
    highlights=(sorted([e for e in highlights if e[1] in upper],key=lambda e:e[8],reverse=True)[:4]
                +[e for e in highlights if e[1] in hotset][:6])
    report={'scenario':scenario,'weekday':day,'input_weight':mass_in,'final_weight':mass_out,
            'finished_weight':sum(s['w'] for s in finished if not s['unserved']),
            'unserved_trip_weight':sum(s['w'] for s in finished if s['unserved']),
            'full_particles':len(prepared['plans'][day]),'render_dots':len(trips),
            'capacity_checks':capacity_checks,'capacity_violations':0,'queue_min':float(values.min()),
            'max_queue':float(values[0].max()),'vehicles':len(vehicles),'boarding_events':len(waits)}
    if audit_sink is not None:audit_sink(waits,events,finished)
    if export:
        public(f'{scenario}-{DAYS[day]}.json',{'schema_version':2,'scenario':scenario,'day':day,'trips':trips,
            'queue_step_seconds':frame_step,'queues':np.round(values[0],3).tolist(),
            'denied_queues':np.round(values[1],3).tolist(),'queue_timeline':timelines,'vehicles':bus_export,'events':events,
            'hourly':hour_stats,'daily':day_stats,'highlights':highlights,'report':report})
        packed(WORK/f'audit-{scenario}-{DAYS[day]}.json.gz',{'waits':waits,'events':events,'report':report,
            'legs':[{'id':s['plan'][0],'weight':s['w'],'unserved':s['unserved'],'legs':s['legs']} for s in finished]})
    print('Capacity replay',scenario,day,json.dumps(report,ensure_ascii=False),flush=True)
    return report,hour_stats,day_stats

def main():
    began=time.perf_counter();OUT.mkdir(parents=True,exist_ok=True)
    prepared,hashes=prepare();public('common.json',prepared['common']);reports=[];charts={}
    for scenario in SCENARIOS:
        charts[scenario]={}
        for day,did in DAYS.items():
            report,hourly,daily=simulate(prepared,day,scenario)
            reports.append(report);charts[scenario][did]={'hourly':hourly,'daily':daily,'report':report}
    legacy=read(BASE/'waiting_time_estimates_2026-11-07/outputs_v2/chart_configs.json')
    public('charts.json',{'scenarios':charts,'legacy_wait_charts':legacy,
        'legacy_note':'이전 평균 유입·20개 출발위상 평균. 현재 대표 반복·연계 재생과 계산 방식이 다릅니다.'})
    assert all(sha(p)==h for p,h in hashes.items())
    save(WORK/'verification.json',{'status':'PASS','model':'All weighted particles, shared route vehicles, FIFO capacity, alight-before-board, transfer delay propagation',
        'representative_seed':20261106,'route_choice_reselected':False,'dispatch_clock_scenarios':1,
        'replay_bins_identical':prepared['replay_bins_identical'],'replay_modes_identical':prepared['replay_modes_identical'],
        'source_hashes_unchanged':True,'capacity_large':60,'capacity_reverse':25,'peak_window':['15:00','19:00'],
        'peak_headways_min':{'snu':3,'circle':5,'daehak':10,'reverse':20},'runs':reports,
        'builder_sha256':sha(Path(__file__)),'created_at_utc':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':time.perf_counter()-began})
    print('DONE',round(time.perf_counter()-began,2),flush=True)
if __name__=='__main__':main()
