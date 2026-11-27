"""Export a preserved representative movement run and the completed mean queue model.

The web display is an explicitly weighted sample, never observed GPS tracks.
Writes are restricted to this separate demo directory. No live traffic API calls.
"""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
from collections import defaultdict,Counter
from datetime import datetime,timezone
import ast,copy,csv,gzip,hashlib,heapq,importlib.util,json,math,shutil,time
import numpy as np

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent
PRE=BASE/'scenario_comparison_2026-11-07/simulation_outputs'
PUBLIC=ROOT/'public';DATA=PUBLIC/'data';WORK=ROOT/'model_snapshot'
DAYS='월화수목금'
DAYIDS=dict(zip(DAYS,('mon','tue','wed','thu','fri')))
START,END=680*60,1390*60
TARGET_DOT_WEIGHT=2.
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def public_json(name,obj):
    data=json.dumps(obj,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    (DATA/name).write_bytes(data)
    (DATA/(name+'.gz')).write_bytes(gzip.compress(data,compresslevel=9,mtime=0))
    return len(data)
def import_file(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def main():
    began=time.perf_counter()
    assert not DATA.exists(),'Preserve previous data exports rather than overwrite them.'
    DATA.mkdir(parents=True)
    WORK.mkdir()
    input_files=[PRE/'input_snapshot/engine/simulate_stop_inflow.py',PRE/'input_snapshot/app/routing.py',
        PRE/'input_snapshot/app/data/walking_osm.json',PRE/'input_snapshot/app/data/network.json',
        PRE/'input_snapshot/app/data/shuttle_network.json',PRE/'input_snapshot/course_endings_current.json',
        BASE/'app/data/road_geometry.json',BASE/'app/data/building_access.json',BASE/'app/data/roads_osm.json',
        BASE/'app/prepare_geometry.py',BASE/'waiting_time_estimates_2026-11-07/estimate_wait.py',
        BASE/'waiting_time_estimates_2026-11-07/outputs_v2/waiting_5min.csv']
    hashes={str(p):sha(p) for p in input_files}
    dump(ROOT/'source_manifest.json',hashes)
    for folder in ('app/data','engine','runtime/sources','runtime/outputs'):(WORK/folder).mkdir(parents=True)
    for part in ('routing.py','data/walking_osm.json','data/network.json','data/shuttle_network.json'):
        shutil.copy2(PRE/'input_snapshot/app'/part,WORK/'app'/part)
    shutil.copy2(input_files[0],WORK/'engine/simulate_stop_inflow.py')
    for name in ('campus_buildings.json','campus_bus_stops.json'):
        shutil.copy2(PRE/'engine_runtime/sources'/name,WORK/'runtime/sources'/name)
    # Readable snapshots of geometry inputs ensure the running implementation can evolve.
    for name in ('road_geometry.json','building_access.json'):
        shutil.copy2(BASE/'app/data'/name,WORK/name)
    engine=import_file('preserved_viewer_engine',WORK/'engine/simulate_stop_inflow.py')
    engine.ROOT=WORK/'runtime'
    capture={}
    original_walker=engine.MatrixWalker
    class ViewerWalker(original_walker):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs);capture['walker']=self
    engine.MatrixWalker=ViewerWalker
    all_events=load(PRE/'input_snapshot/course_endings_current.json')
    events=[e for e in all_events if e['included_main'] and e['weekday'] in DAYS and e['end_minute']<=engine.END]
    assert len(events)==6201
    choices,routes,destinations,_=engine.build_candidates(events)
    walker=capture['walker']
    print('Candidate graph built; replaying preserved seed.',flush=True)
    spec=load(PRE.parent/'scenario_specs.json')['scenarios'][0]
    rho=spec['dorm_share'];q=spec['immediate_trip_share']
    group_weights={'dorm':rho*q,**{g:(1-rho)*x*q for g,x in zip(('snu','nak','daehak'),spec['external_mix'])}}
    selected=defaultdict(list);all_mass=Counter();path_keys={};path_requests=[]
    route_colors={'100100250':'#4f78b3','100100251':'#5b84a2','100100253':'#5b8e8b','120900011':'#3a958d','120900012':'#4aa37c',
                  'shuttle-41841':'#8b6abd','shuttle-41946':'#8b6abd','shuttle-41914':'#8b6abd','shuttle-daehak':'#8b6abd'}
    def pid(kind,a,b=None,rid=None,i=None,j=None):
        key=(kind,tuple(a) if a is not None else None,tuple(b) if b is not None else None,rid,i,j)
        if key not in path_keys:
            path_keys[key]=len(path_requests);path_requests.append(key)
        return path_keys[key]
    def collect(e,group,c,mask,arrivals,ride_departures,departure,scale,weight,dest):
        probability=group_weights[group];w=weight*probability
        all_mass[e['weekday']]+=int(mask.sum())*w
        destination=destinations[dest];origin=[e['lat'],e['lon']]
        for particle in np.flatnonzero(mask):
            identity=f"{e['weekday']}|{e['section_id']}|{e['end_minute']}|{group}|{particle}"
            digest=hashlib.sha256(identity.encode()).digest()
            u=int.from_bytes(digest[:8],'big')/2**64
            inclusion=min(1.,w/TARGET_DOT_WEIGHT)
            if u>=inclusion:continue
            legs=[];t=float(departure[particle])
            if not c['rides']:
                final=t+c['first_walk']['seconds']*float(scale[particle])
                legs.append([0,round(t),round(final),pid('walk',origin,destination)])
            else:
                first=c['rides'][0];board=routes[first['route_id']]['stops'][first['board']]
                first_at=float(arrivals[0][particle])
                legs.append([0,round(t),round(first_at),pid('walk',origin,[board['lat'],board['lon']])])
                for stage,ride in enumerate(c['rides']):
                    route=routes[ride['route_id']];a=route['stops'][ride['board']];b=route['stops'][ride['alight']]
                    at=float(arrivals[stage][particle]);dep=float(ride_departures[stage][particle]);end=dep+ride['ride_seconds']
                    legs.append([1,round(at),round(dep),pid('point',[a['lat'],a['lon']])])
                    mode=3 if ride['route_id'].startswith('shuttle') else 2
                    legs.append([mode,round(dep),round(end),pid('bus',None,rid=ride['route_id'],i=ride['board'],j=ride['alight'])])
                    if stage+1<len(c['rides']):
                        nr=c['rides'][stage+1];next_stop=routes[nr['route_id']]['stops'][nr['board']]
                        end_walk=float(arrivals[stage+1][particle])
                        legs.append([0,round(end),round(end_walk),pid('walk',[b['lat'],b['lon']],[next_stop['lat'],next_stop['lon']])])
                    else:
                        final=end+c['last_walk']['seconds']*float(scale[particle])
                        legs.append([0,round(end),round(final),pid('walk',[b['lat'],b['lon']],destination)])
            legs=[leg for leg in legs if leg[2]>leg[1]]
            if not legs or legs[-1][2]<START or legs[0][1]>END:continue
            for a,b in zip(legs,legs[1:]):assert a[2]==b[1],(a,b)
            selected[e['weekday']].append([int.from_bytes(digest[8:12],'big'),str(e['building']),group,round(w/inclusion,4),legs])
    engine._collect_viewer=collect
    # Capture calculated arrays without introducing any random draw into route choice.
    class Inject(ast.NodeTransformer):
        def __init__(self):self.counts=Counter()
        def visit_Assign(self,node):
            node=self.generic_visit(node);name=node.targets[0].id if len(node.targets)==1 and isinstance(node.targets[0],ast.Name) else None;extra=[]
            if name=='arrivals':extra=ast.parse('departures_by_choice=[]').body;self.counts['init']+=1
            if name=='stops':extra=ast.parse('ride_departures=[]').body;self.counts['option']+=1
            if name=='t' and any(isinstance(v,ast.Call) and isinstance(v.func,ast.Name) and v.func.id=='wait_seconds' for v in ast.walk(node.value)):
                extra=ast.parse('ride_departures.append(t.copy())').body;self.counts['depart']+=1
            return [node]+extra if extra else node
        def visit_Expr(self,node):
            node=self.generic_visit(node)
            if ast.unparse(node)=='arrivals.append(stops)':self.counts['option_capture']+=1;return [node]+ast.parse('departures_by_choice.append(ride_departures)').body
            return node
        def visit_AugAssign(self,node):
            node=self.generic_visit(node)
            if ast.unparse(node.target)=='modes[day, group, mode]':
                self.counts['collect']+=1
                return [node]+ast.parse('_collect_viewer(e,group,c,selected,arrivals[ci],departures_by_choice[ci],departure,scale,weight,dest)').body
            return node
    source=(WORK/'engine/simulate_stop_inflow.py').read_text(encoding='utf-8')
    fn=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='run_rep')
    injection=Inject();fn=injection.visit(copy.deepcopy(fn));fn.name='run_viewer'
    assert dict(injection.counts)=={'init':1,'option':1,'depart':1,'option_capture':1,'collect':1}
    module=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]))
    (WORK/'instrumented_run.py').write_text(ast.unparse(module),encoding='utf-8')
    exec(compile(module,str(WORK/'instrumented_run.py'),'exec'),engine.__dict__)
    reference=engine.run_rep(events,choices,routes,engine.SEED)
    replay=engine.run_viewer(events,choices,routes,engine.SEED)
    assert reference[0]==replay[0] and reference[1]==replay[1] and reference[4]==replay[4]
    inputs=Counter()
    for e in events:inputs[e['weekday']]+=e['enrollment']*.5
    assert max(abs(all_mass[d]-inputs[d]) for d in DAYS)<1e-6
    print('Exact seed replay matched; resolving saved geometries.',flush=True)
    road=load(WORK/'road_geometry.json')['routes']
    # Reuse only the local DriveGraph definition, never the module's download routines.
    geo_source=(BASE/'app/prepare_geometry.py').read_text(encoding='utf-8')
    graph_class=next(n for n in ast.parse(geo_source).body if isinstance(n,ast.ClassDef) and n.name=='DriveGraph')
    namespace={'math':math,'heapq':heapq,'meters':engine.distance}
    exec(compile(ast.Module(body=[graph_class],type_ignores=[]),'saved_drive_graph','exec'),namespace)
    drive=None;geometries=[None]*len(path_requests);geom_sources=Counter();walk_failures=0
    order=sorted(range(len(path_requests)),key=lambda k:str(path_requests[k][:2]))
    for number,index in enumerate(order):
        kind,a,b,rid,i,j=path_requests[index]
        if kind=='point':points=[a];geom_sources['station_point']+=1
        elif kind=='walk':
            na,da=walker.snaps[a];nb,db=walker.snaps[b];costs,parents=walker.graph.tree(na)
            assert nb in costs,'Selected walking path must remain reachable'
            chain=[nb]
            while chain[-1]!=na:chain.append(parents[chain[-1]][0])
            points=[a]+[walker.graph.nodes[n] for n in reversed(chain)]+[b];geom_sources['preserved_walking_graph']+=1
        else:
            segments=road.get(rid,{}).get('segments',[]);points=[]
            if len(segments)==len(routes[rid]['stops'])-1 and all(segments[k] for k in range(i,j)):
                for k in range(i,j):points.extend(segments[k]['geometry'] if not points else segments[k]['geometry'][1:])
                geom_sources['saved_route_road_geometry']+=1
            else:
                if drive is None:drive=namespace['DriveGraph'](load(BASE/'app/data/roads_osm.json'))
                st=routes[rid]['stops']
                for k in range(i,j):
                    part=drive.path([st[k]['lat'],st[k]['lon']],[st[k+1]['lat'],st[k+1]['lon']])
                    assert part,'Do not fabricate a straight bus path when road geometry is missing.'
                    points.extend(part if not points else part[1:])
                geom_sources['saved_osm_drive_graph']+=1
        compact=[]
        for p in points:
            v=[round(float(p[0]),6),round(float(p[1]),6)]
            if not compact or v!=compact[-1]:compact.append(v)
        assert compact
        geometries[index]=compact
        if number and number%500==0:print('geometry',number,'/',len(order),flush=True)
    nodes=[]
    queue_model=import_file('viewer_queue_model',BASE/'waiting_time_estimates_2026-11-07/estimate_wait.py')
    node_names=list(queue_model.NODES)
    for name,(rid,sid,label) in queue_model.NODES.items():
        st=next(s for s in routes[rid]['stops'] if s['id']==sid)
        nodes.append({'id':name,'label':label,'lat':st['lat'],'lon':st['lon']})
    waiting=defaultdict(lambda:[[None]*6 for _ in range(142)])
    with (BASE/'waiting_time_estimates_2026-11-07/outputs_v2/waiting_5min.csv').open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            if row['config']=='base60':waiting[row['weekday']][(int(row['bin_minute'])-680)//5][node_names.index(row['node'])]=round(float(row['mean_wait_min']),2) if row['mean_wait_min'] else None
    raw=defaultdict(float)
    with (PRE/'conditional_mean_bins.csv').open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            node=queue_model.LOOKUP.get((r['route_id'],r['stop_id']))
            if node:raw[(r['weekday'],r['destination_group'],node,int(r['bin_minute']))]+=float(r['conditional_trip_events'])
    bins=queue_model.arrival_bins(queue_model.CONFIGS[0],raw)
    offsets=queue_model.offsets(routes);step=5;frame_n=(END-START)//step+1
    exports={}
    for day in DAYS:
        diff=np.zeros((6,frame_n+1),dtype=float)
        def add(node,arrival,departure,weight):
            a=max(0,int(math.ceil((arrival*60-START)/step-1e-8)));b=min(frame_n,int(math.ceil((departure*60-START)/step-1e-8)))
            if a<b:idx=node_names.index(node);diff[idx,a]+=weight/20;diff[idx,b]-=weight/20
        for phase in range(20):
            served,unserved,_,_=queue_model.simulate(bins,day,queue_model.CONFIGS[0],phase,offsets)
            for node,b,w,wait,extra,sched,departure,arrival in served:add(node,arrival,departure,w)
            for node,b,w,arrival in unserved:add(node,arrival,24*60,w)
        frames=np.cumsum(diff,axis=1)[:,:frame_n].T
        assert float(frames.min())>-1e-6
        frames=np.maximum(frames,0)
        payload={'day':day,'trips':selected[day],'queue_step_seconds':step,'queues':np.round(frames,1).tolist(),'waits':waiting[day]}
        exports[DAYIDS[day]]=public_json(DAYIDS[day]+'.json',payload)
        print('export',day,'dots',len(selected[day]),'bytes',exports[DAYIDS[day]],flush=True)
    buildings={}
    for e in events:buildings[str(e['building'])]={'id':str(e['building']),'name':e['building_name'],'lat':e['lat'],'lon':e['lon']}
    building_polys=load(WORK/'building_access.json')['buildings']
    road_lines=[]
    for rid,specification in road.items():
        if rid in routes:
            pts=[]
            for part in specification['segments']:
                if part:pts.extend(part['geometry'])
            road_lines.append({'id':rid,'name':routes[rid]['name'],'geometry':pts})
    common={'schema_version':1,'start_second':START,'end_second':END,'dot_weight_target':2,
        'movement_seed':engine.SEED,'movement_replications_shown':1,'original_replications':10,
        'movement_capacity_applied':False,'queue_capacity_large':60,'queue_capacity_reverse':25,'queue_phases':20,
        'paths':geometries,'buildings':list(buildings.values()),'nodes':nodes,
        'footprints':[{'name':b.get('name',''),'polygon':b['polygon']} for b in building_polys if b.get('polygon')],
        'route_lines':road_lines,'destinations':destinations,
        'source_note':'수강인원 기반 가중 모형의 대표 재생. 실제 GPS·고유 학생 수가 아닙니다.',
        'queue_note':'완료된 평균 유입 대기열 계산의20개 출발시각 경우 평균. 이동 재생과 구분합니다.'}
    common_bytes=public_json('common.json',common)
    vendor=PUBLIC/'vendor';vendor.mkdir(exist_ok=True)
    for name in ('leaflet.js','leaflet.css','LEAFLET-LICENSE'):shutil.copy2(BASE/'app/static/vendor'/name,vendor/name)
    shutil.copytree(BASE/'app/static/vendor/images',vendor/'images')
    assert all(sha(p)==h for p,h in hashes.items()),'A selected source changed during the export.'
    checks={'status':'PASS','representative_seed':engine.SEED,'reference_replay_bins_identical':True,'reference_replay_modes_identical':True,
        'full_weight_conservation':dict(all_mass),'expected_full_weight':dict(inputs),'sample_dots_per_day':{DAYIDS[d]:len(selected[d]) for d in DAYS},
        'shared_paths':len(geometries),'geometry_sources':dict(geom_sources),'source_hashes_unchanged':True,
        'live_api_calls':0,'credentials_read':False,'common_bytes':common_bytes,'day_export_bytes':exports,
        'elapsed_seconds':round(time.perf_counter()-began,2),'completed_at_utc':datetime.now(timezone.utc).isoformat()}
    dump(ROOT/'data_verification.json',checks)
    print(json.dumps(checks,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
