"""Preserved-engine conditional segment features, with exact reference replay.

Writes only under this task-owned segment_model directory. No network or key use.
Two explicit observation assumptions: segment entry and actual boarding departure.
"""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone
import ast, copy, importlib.util, hashlib, json, csv, gzip, shutil, time, os, argparse
from types import SimpleNamespace
import numpy as np

ROOT=Path(__file__).resolve().parent
SHUTTLE=ROOT.parents[2]
OLD=SHUTTLE/'course_demand_2026-11-06'
PREVIOUS=SHUTTLE/'scenario_comparison_2026-11-07/simulation_outputs'
OBS=SHUTTLE/'tdata_calibration_2026-11-07/collected/20261026/target_routes.json'
TARGETS={'100100250','100100251','100100253','120900011','120900012'}
GROUPS=('dorm','snu','nak','daehak')
BASE_WEIGHTS={'dorm':(5772/29613)*.5,**{g:(1-5772/29613)/3*.5 for g in GROUPS[1:]}}
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def write_rows(p,rows,fields=None):
    rows=iter(rows)
    first=next(rows,None)
    if first is None:return
    with Path(p).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(first));w.writeheader();w.writerow(first);w.writerows(rows)

class Inject(ast.NodeTransformer):
    def __init__(self,features):self.features=features;self.counts=Counter()
    def visit_Assign(self,node):
        node=self.generic_visit(node)
        name=node.targets[0].id if len(node.targets)==1 and isinstance(node.targets[0],ast.Name) else None
        extra=[]
        if name=='valid':
            extra=ast.parse('_cohort_trace(e, group, chosen, valid, rng)').body;self.counts['trace']+=1
        if self.features:
            if name=='arrivals':
                extra+=ast.parse('departures_by_choice = []').body;self.counts['departures_init']+=1
            elif name=='stops':
                extra+=ast.parse('ride_departures = []').body;self.counts['option_departures_init']+=1
            elif name=='t' and any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='wait_seconds' for n in ast.walk(node.value)):
                extra+=ast.parse('ride_departures.append(t.copy())').body;self.counts['departure_capture']+=1
        return [node]+extra if extra else node
    def visit_Expr(self,node):
        node=self.generic_visit(node)
        if self.features and ast.unparse(node)=='arrivals.append(stops)':
            self.counts['option_capture']+=1
            return [node]+ast.parse('departures_by_choice.append(ride_departures)').body
        return node
    def visit_AugAssign(self,node):
        node=self.generic_visit(node)
        if self.features and ast.unparse(node.target)=='modes[day, group, mode]':
            self.counts['collector']+=1
            return [node]+ast.parse('_collect_segments(e, group, c, selected, departures_by_choice[ci], weight)').body
        return node

def build_function(engine,source,name,features,out):
    original=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='run_rep')
    injector=Inject(features);node=injector.visit(copy.deepcopy(original));node.name=name
    expected={'trace':1}
    if features:expected.update(departures_init=1,option_departures_init=1,departure_capture=1,option_capture=1,collector=1)
    assert dict(injector.counts)==expected,(injector.counts,expected)
    module=ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[]))
    rendered=ast.unparse(module)+'\n'
    path=out/(name+'.py');path.write_text(rendered,encoding='utf-8')
    exec(compile(module,str(path),'exec'),engine.__dict__)
    return getattr(engine,name),{'insertions':dict(injector.counts),'emitted_source_sha256':sha(path)}

class Trace:
    def __init__(self):self.chosen=hashlib.sha256();self.rng=hashlib.sha256();self.cohorts=0
    def __call__(self,e,g,chosen,valid,rng):
        identity=json.dumps([e['weekday'],e['building'],e['end_minute'],e['enrollment'],g],ensure_ascii=False).encode()
        self.chosen.update(identity);self.chosen.update(chosen.tobytes());self.chosen.update(valid.tobytes())
        self.rng.update(json.dumps(rng.bit_generator.state,sort_keys=True).encode());self.cohorts+=1
    def result(self):return {'cohorts':self.cohorts,'chosen_sha256':self.chosen.hexdigest(),'rng_state_stream_sha256':self.rng.hexdigest()}

def max_difference(a,b):
    assert set(a)==set(b),'Replay keys changed'
    return max((abs(a[k]-b[k]) for k in a),default=0.)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='outputs');args=parser.parse_args()
    out=(ROOT/args.out).resolve();assert out.is_relative_to(ROOT.resolve()) and not out.exists()
    started=time.perf_counter();out.mkdir(parents=True)
    provenance={'status':'running','started_at_utc':datetime.now(timezone.utc).isoformat(),
                'runner_sha256':sha(__file__),'authenticated_api_calls':0,'credentials_read':False,
                'writes_restricted_to':str(out),'time_conventions_provider_confirmed':False}
    dump(out/'provenance.json',provenance)
    before={str(p.relative_to(OLD)):sha(p) for p in sorted(OLD.rglob('*')) if p.is_file()}
    dump(out/'original_inventory_before.json',before)
    protected={str(p):sha(p) for p in (PREVIOUS/'execution_provenance.json',PREVIOUS/'conditional_mean_bins.csv',
        PREVIOUS/'stop_inflow_5min_scenarios.csv',OBS)}
    def audit(event,args):
        if event!='open' or not isinstance(args[0],(str,bytes)):return
        filename,mode,flags=args
        if (isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):
            assert Path(filename).resolve().is_relative_to(out),f'Unexpected write outside run: {filename}'
    sys.addaudithook(audit)
    snap=out/'input_snapshot';app=snap/'app';engine_dir=snap/'engine';runtime=out/'engine_runtime'
    for p in (app/'data',engine_dir,runtime/'sources',runtime/'outputs'):p.mkdir(parents=True)
    pairs=[(PREVIOUS/'input_snapshot/engine/simulate_stop_inflow.py',engine_dir/'simulate_stop_inflow.py'),
        *[(PREVIOUS/'input_snapshot/app'/p,app/p) for p in ('routing.py','data/network.json','data/walking_osm.json','data/shuttle_network.json')],
        (PREVIOUS/'input_snapshot/course_endings_current.json',snap/'course_endings_current.json'),
        (OBS,snap/'target_routes_20261026.json'),
        *[(PREVIOUS/'engine_runtime/sources'/p,runtime/'sources'/p) for p in ('campus_buildings.json','campus_bus_stops.json')]]
    manifest=[]
    previous_pins={str((PREVIOUS/x['snapshot']).resolve()):x['sha256'] for x in load(PREVIOUS/'input_manifest.json')}
    for source,target in pairs:
        source_hash=sha(source)
        if str(source.resolve()) in previous_pins:assert source_hash==previous_pins[str(source.resolve())]
        shutil.copy2(source,target);assert sha(target)==source_hash
        manifest.append({'source':str(source),'snapshot':str(target.relative_to(out)),'sha256':source_hash})
    dump(out/'input_manifest.json',manifest)
    module_spec=importlib.util.spec_from_file_location('snu_segment_preserved_engine',engine_dir/'simulate_stop_inflow.py')
    engine=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(engine);engine.ROOT=runtime
    reference,ref_transform=build_function(engine,(engine_dir/'simulate_stop_inflow.py').read_text(encoding='utf-8'),'reference_run_rep',False,out)
    feature,feat_transform=build_function(engine,(engine_dir/'simulate_stop_inflow.py').read_text(encoding='utf-8'),'feature_run_rep',True,out)
    dump(out/'instrumentation.json',{'reference':ref_transform,'feature':feat_transform,
        'reference_change':'read-only chosen and RNG-state audit after original valid calculation',
        'feature_change':'copy vehicle departure arrays and observe selected city ride legs; no additional RNG calls'})
    events=[e for e in load(snap/'course_endings_current.json') if e['included_main'] and e['weekday'] in engine.DAYS[:5] and e['end_minute']<=engine.END]
    assert len(events)==6201 and sum(e['enrollment'] for e in events)==156338
    choices,routes,destinations,coverage=engine.build_candidates(events)
    observed=load(snap/'target_routes_20261026.json')
    obskeys=Counter((str(x['routeId']),str(x['staSn']),str(x['fromStaId']),str(x['toStaId'])) for x in observed)
    assert all(v==1 for v in obskeys.values())
    segment_meta={};index=[]
    for rid in sorted(TARGETS):
        route=routes[rid]
        for k,(a,b) in enumerate(zip(route['stops'],route['stops'][1:])):
            key=(rid,str(a['seq']),a['id'],b['id'])
            row={'route_id':rid,'route_name':route['name'],'current_link_index0':k,
                'current_from_seq':a['seq'],'current_to_seq':b['seq'],'from_stop_id':a['id'],'to_stop_id':b['id'],
                'from_stop_name':a['name'],'to_stop_name':b['name'],'from_lat':a['lat'],'from_lon':a['lon'],
                'direction':a.get('direction',''),'observed_sta_sn':str(a['seq']) if obskeys[key]==1 else '',
                'mapping_date':'20261026','exact_pair_and_from_seq_match':obskeys[key]==1}
            segment_meta[(rid,k)]=row;index.append(row)
    assert len(index)==259 and all(x['exact_pair_and_from_seq_match'] for x in index)
    write_rows(out/'segment_index.csv',index)
    dump(out/'mapping_validation.json',{'status':'PASS_FOR_20261026_SNAPSHOT','segments':len(index),
        'endpoint_pairs_without_sequence':len({(x['route_id'],x['from_stop_id'],x['to_stop_id']) for x in index}),
        'all_259_current_from_seq_keys_match':True,'general_provider_sequence_definition_confirmed':False})
    offsets={};rounding=[]
    planner_adapter=SimpleNamespace(point=lambda s:(s['lat'],s['lon']))
    for options in choices.values():
        for candidate in options:
            for ride in candidate['rides']:
                rid=ride['route_id'];i=ride['board'];j=ride['alight'];legkey=(rid,i,j)
                if rid not in TARGETS or legkey in offsets:continue
                route=routes[rid];unrounded=0.;partials=[];rounded_single_sum=0.
                for k in range(i,j):
                    prefix=0 if k==i else engine.Planner.ride_seconds(planner_adapter,route,i,k)
                    partials.append((k,prefix,unrounded))
                    a,b=route['stops'][k:k+2]
                    straight=engine.distance((a['lat'],a['lon']),(b['lat'],b['lon']))
                    reported=b.get('segment_m',0)
                    meters=reported if straight*.7<=reported<=max(200,straight*3) else straight*1.2
                    seconds=meters/5+15;unrounded+=seconds;rounded_single_sum+=round(seconds)
                assert abs(ride['ride_seconds']-round(unrounded))<1e-9
                for k,prefix,rawprefix in partials:
                    rounding.append({'route_id':rid,'board_index0':i,'alight_index0':j,'link_index0':k,
                        'partial_seconds_used':prefix,'partial_seconds_unrounded':rawprefix,
                        'prefix_rounding_error_seconds':prefix-rawprefix,
                        'rounded_single_links_minus_full_ride_seconds':rounded_single_sum-ride['ride_seconds']})
                offsets[legkey]=partials
    write_rows(out/'rounding_diagnostics.csv',rounding)
    combined=defaultdict(float);stop_mean=defaultdict(float);checks=[]
    columns=['clock','weekday','destination_group','route_id','route_name','current_link_index0','current_from_seq','current_to_seq',
        'from_stop_id','to_stop_id','observed_sta_sn','direction','day_offset','hour','conditional_trip_events']
    def export_row(key,value):
        clock,day,group,rid,k,offset,hour=key;m=segment_meta[(rid,k)]
        return {'clock':clock,'weekday':day,'destination_group':group,
            **{n:m[n] for n in ('route_id','route_name','current_link_index0','current_from_seq','current_to_seq','from_stop_id','to_stop_id','observed_sta_sn','direction')},
            'day_offset':offset,'hour':hour,'conditional_trip_events':value}
    with gzip.open(out/'conditional_segment_hour_by_rep.csv.gz','wt',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['replicate']+columns);writer.writeheader()
        for rep in range(engine.REPS):
            trace_ref=Trace();engine._cohort_trace=trace_ref
            original=reference(events,choices,routes,engine.SEED+rep)
            bins=defaultdict(float);expected_segments=0.;city_legs=0.;rounding_crossings=0
            def collect(e,group,c,selected,departures,weight):
                nonlocal expected_segments,city_legs,rounding_crossings
                for stage,ride in enumerate(c['rides']):
                    rid=ride['route_id']
                    if rid not in TARGETS:continue
                    values=departures[stage][selected];n=len(values)
                    assert np.isfinite(values).all()
                    city_legs+=weight*n
                    boardhours=np.floor(values/3600).astype(np.int64)
                    for k,offset,unrounded_offset in offsets[(rid,ride['board'],ride['alight'])]:
                        expected_segments+=weight*n
                        entryhours=np.floor((values+offset)/3600).astype(np.int64)
                        rawhours=np.floor((values+unrounded_offset)/3600).astype(np.int64)
                        rounding_crossings+=weight*int(np.count_nonzero(entryhours!=rawhours))
                        for clock,hours in [('segment_entry',entryhours),('boarding_hour',boardhours)]:
                            unique,counts=np.unique(hours,return_counts=True)
                            for hour,count in zip(unique,counts):
                                bins[(clock,e['weekday'],group,rid,k,int(hour)//24,int(hour)%24)]+=weight*int(count)
            engine._collect_segments=collect;trace_feature=Trace();engine._cohort_trace=trace_feature
            extended=feature(events,choices,routes,engine.SEED+rep)
            assert trace_ref.result()==trace_feature.result(),'RNG or chosen paths changed'
            bin_error=max_difference(original[0],extended[0]);mode_error=max_difference(original[1],extended[1])
            assert bin_error==0 and mode_error==0 and original[3]==extended[3] and original[4]==extended[4]
            totals={clock:sum(v for k,v in bins.items() if k[0]==clock) for clock in ('segment_entry','boarding_hour')}
            assert all(abs(v-expected_segments)<1e-6 for v in totals.values())
            for key,value in sorted(bins.items()):
                combined[key]+=value/engine.REPS;writer.writerow({'replicate':rep+1,**export_row(key,value)})
            for key,value in extended[0].items():stop_mean[key]+=value/engine.REPS
            checks.append({'replicate':rep+1,'seed':engine.SEED+rep,**trace_ref.result(),
                'stop_bin_max_difference':bin_error,'mode_max_difference':mode_error,
                'conditional_passenger_segment_weight':expected_segments,'segment_entry_total':totals['segment_entry'],
                'boarding_hour_total':totals['boarding_hour'],'city_ride_leg_weight':city_legs,
                'conditional_segment_weight_changing_hour_due_to_prefix_rounding':rounding_crossings})
            dump(out/'run_progress.json',{'replications_complete':rep+1,'replications_total':engine.REPS,'elapsed_seconds':round(time.perf_counter()-started,1)})
            print(f'Paired replay {rep+1}/{engine.REPS}; {time.perf_counter()-started:.1f}s',flush=True)
    write_rows(out/'conditional_segment_hour.csv',(export_row(k,v) for k,v in sorted(combined.items())),columns)
    baseline=defaultdict(float)
    for key,value in combined.items():
        clock,day,g,rid,k,offset,hour=key;baseline[(clock,day,rid,k,offset,hour)]+=value*BASE_WEIGHTS[g]
    def baseline_rows():
        for (clock,day,rid,k,offset,hour),value in sorted(baseline.items()):
            r=export_row((clock,day,'baseline',rid,k,offset,hour),value);r.pop('destination_group')
            r['expected_trip_events']=r.pop('conditional_trip_events');yield r
    write_rows(out/'baseline_segment_hour.csv',baseline_rows())
    write_rows(out/'replication_replay_checks.csv',checks)
    archived={}
    with (PREVIOUS/'conditional_mean_bins.csv').open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            key=(r['weekday'],r['destination_group'],r['stop_id'],r['direction'],r['route_id'],int(r['bin_minute']),int(r['boarding_stage'])-1)
            archived[key]=float(r['conditional_trip_events'])
    archive_error=max_difference(archived,stop_mean);assert archive_error<1e-9
    assert before=={str(p.relative_to(OLD)):sha(p) for p in sorted(OLD.rglob('*')) if p.is_file()}
    assert all(sha(Path(p))==h for p,h in protected.items())
    maxround=max(abs(r['prefix_rounding_error_seconds']) for r in rounding)
    assert maxround<=.500000001
    validation={'status':'PASS_CONDITIONAL_SEGMENT_FEATURES','paired_replications':engine.REPS,
        'chosen_and_rng_streams_equal_each_rep':True,'all_stop_bins_and_modes_exactly_reproduced':True,
        'archived_conditional_stop_mean_max_difference':archive_error,
        'passenger_segment_conservation_each_clock_each_rep':True,
        'current_segments_matched_20261026':len(index),'largest_prefix_rounding_error_seconds':maxround,
        'original_files_verified_unchanged':len(before),'protected_previous_outputs_and_observation_unchanged':True,
        'empirical_calibration_performed':False,'capacity_or_queues_modelled':False}
    dump(out/'validation.json',validation)
    provenance.update(status='complete',finished_at_utc=datetime.now(timezone.utc).isoformat(),
        elapsed_seconds=round(time.perf_counter()-started,2),seed=engine.SEED,replications=engine.REPS,
        weighted_particles_per_cohort_destination=engine.PARTICLES,
        source_ending_events=len(events),source_enrollment_event_sum=sum(e['enrollment'] for e in events),
        conditional_feature_rows=len(combined),baseline_feature_rows=len(baseline),baseline_weights=BASE_WEIGHTS,
        origin_weekday_definition='Weekday of the original class-ending event; bind calendar date before applying day_offset.',
        day_offset_definition='Floor of simulated timestamp seconds divided by 86400 relative to origin date; hour modulo 24.',
        segment_entry_definition='Wait-after-20s boarding allowance + Planner.ride_seconds(route,board,link_start) partial cumulative.',
        boarding_hour_definition='Hour of the same leg actual simulated departure after waiting, applied to every ridden segment.',
        original_files_verified_unchanged=len(before),schema_status='Conditional reference features; time attribution not provider-confirmed.')
    dump(out/'provenance.json',provenance)
    files={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    dump(out/'output_manifest.json',files)
    dump(out/'READY.json',{'status':'READY_CONDITIONAL_FEATURES','validation':'validation.json',
        'conditional_features':'conditional_segment_hour.csv','baseline':'baseline_segment_hour.csv',
        'empirical_calibration_complete':False,'provider_time_semantics_confirmed':False})
    print(json.dumps(validation,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
