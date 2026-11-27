"""Reuse the preserved SNU engine under isolated paths with common random numbers.

Owned files: this runner and simulation_outputs/. The research task owns specs and
comparison reports. Historical proportions are hypothetical allocation weights.
The engine emits stop-arrival demand weights, not observed queues or occupants.
"""
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta
import importlib.util, sys, shutil, hashlib, json, csv, time, math, platform, os
import numpy as np

ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'course_demand_2026-11-06'
OUT=ROOT/'simulation_outputs'
GROUPS=('dorm','snu','nak','daehak')
DAYS='월화수목금'
CANONICAL={'snu-901':'302동','snu-1001':'301동','snu-300':'문화관입구','snu-410':'행정관'}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def dump(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def clock(m):return f'{int(m)//60:02d}:{int(m)%60:02d}'
def csv_write(name,fields,rows):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def original_inventory():
    # Every existing original file, including earlier experiment outputs, is pinned.
    return {str(p.relative_to(OLD)):sha(p) for p in sorted(OLD.rglob('*')) if p.is_file()}
def weights(s):
    rho=float(s['dorm_share']);q=float(s['immediate_trip_share'])
    w={'dorm':rho*q,**{g:(1-rho)*float(x)*q for g,x in zip(GROUPS[1:],s['external_mix'])}}
    assert abs(sum(w.values())-q)<1e-12
    return w

def isolate():
    snap=OUT/'input_snapshot';app=snap/'app';engine_dir=snap/'engine'
    for p in (app/'data',engine_dir,OUT/'engine_runtime/sources',OUT/'engine_runtime/outputs'):
        p.mkdir(parents=True,exist_ok=False)
    pairs=[(OLD/'simulate_stop_inflow.py',engine_dir/'simulate_stop_inflow.py'),
           (OLD/'sources/routing_source_used.py',app/'routing.py'),
           (OLD/'sources/walking_osm_used.json',app/'data/walking_osm.json'),
           (OLD/'sources/city_network_used.json',app/'data/network.json'),
           (OLD/'sources/shuttle_catalog_legacy_used.json',app/'data/shuttle_network.json'),
           (OLD/'outputs/course_endings_current.json',snap/'course_endings_current.json'),
           (OLD/'outputs/course_quality.json',snap/'course_quality.json'),
           (ROOT/'scenario_specs.json',snap/'scenario_specs.json')]
    for name in ('campus_buildings.json','campus_bus_stops.json'):
        pairs.append((OLD/'sources'/name,OUT/'engine_runtime/sources'/name))
    manifest=[]
    for source,target in pairs:
        shutil.copy2(source,target)
        assert sha(source)==sha(target)
        manifest.append({'source':str(source),'snapshot':str(target.relative_to(OUT)),'sha256':sha(target)})
    spec=importlib.util.spec_from_file_location('snu_preserved_engine',engine_dir/'simulate_stop_inflow.py')
    engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)
    engine.ROOT=OUT/'engine_runtime'
    assert engine.APP.resolve()==app.resolve()
    return engine,manifest,snap

def mean_rows(combined,meta):
    for (day,group,stop,direction,rid,b,stage),v in sorted(combined.items()):
        m=meta[(stop,direction,rid)]
        yield {'weekday':day,'destination_group':group,'stop_id':stop,
            'stop_name':CANONICAL.get(stop,m['stop_name']),'direction':direction,'route_id':rid,
            'route_name':m['route_name'],'time_bin':clock(b),'bin_minute':b,'boarding_stage':stage+1,
            'conditional_trip_events':v,'in_collection_window':680<=b<1390,
            'lat':m['lat'],'lon':m['lon']}

def scenario_bins(conditional,s):
    result=defaultdict(float);w=weights(s)
    for (day,group,stop,direction,rid,b,stage),v in conditional.items():
        if 680<=b<1390:result[(day,stop,direction,rid,b,stage)]+=v*w[group]
    return result

def export_rep_peaks(bins,scenarios,rep,meta,writers):
    for s in scenarios:
        physical=defaultdict(lambda:defaultdict(lambda:[0.0,0.0,0.0]))
        directional=defaultdict(lambda:defaultdict(lambda:[0.0,0.0,0.0]))
        for (day,stop,direction,rid,b,stage),v in scenario_bins(bins,s).items():
            p=physical[(day,stop)][b];p[0]+=v;p[stage+1]+=v
            d=directional[(day,stop,direction)][b];d[0]+=v;d[stage+1]+=v
        for label,groups in [('physical',physical),('directional',directional)]:
            for key,times in groups.items():
                day,stop=key[:2]
                for window,start in [('all',680),('afternoon',900)]:
                    eligible={b:v for b,v in times.items() if b>=start}
                    if not eligible:continue
                    m=next(x for (sid,di,ri),x in meta.items() if sid==stop)
                    row={'scenario':s['name'],'replicate':rep,'window':window,'weekday':day,
                         'stop_id':stop,'stop_name':CANONICAL.get(stop,m['stop_name'])}
                    if label=='directional':row['direction']=key[2]
                    for i,metric in enumerate(('all_boarding','first_boarding','transfer_boarding')):
                        b=max(eligible,key=lambda x:(eligible[x][i],-x))
                        row[metric+'_peak_bin']=b if eligible[b][i]>0 else ''
                        row[metric+'_peak_events']=eligible[b][i]
                        row[metric+'_total_events']=sum(v[i] for v in eligible.values())
                    writers[label].writerow(row)

def main():
    began=time.perf_counter();started=datetime.now(timezone.utc)
    assert not OUT.exists(),'Do not overwrite an earlier run; preserve and select a new output directory explicitly.'
    specs=load(ROOT/'scenario_specs.json');scenarios=specs['scenarios']
    assert len(scenarios)==10 and len({s['name'] for s in scenarios})==10
    for s in scenarios:
        assert len(s['external_mix'])==3 and min(s['external_mix'])>=0
        assert abs(sum(s['external_mix'])-1)<1e-12
        assert 0<=s['dorm_share']<=1 and s['immediate_trip_share']==.5
    before=original_inventory()
    original_xls=Path(load(OLD/'outputs/course_quality.json')['source'])
    xls_hash=sha(original_xls)
    OUT.mkdir()
    dump(OUT/'original_inventory_before.json',before)
    provenance={'status':'running','started_at_utc':started.isoformat(),
        'started_at_kst':started.astimezone(timezone(timedelta(hours=9))).isoformat(),
        'specs_sha256':sha(ROOT/'scenario_specs.json'),'runner_sha256':sha(Path(__file__)),
        'python':sys.version,'numpy':np.__version__,'platform':platform.platform(),
        'writes_restricted_to':str(OUT),'live_api_calls':0,
        'scenario_status':'historical reference assumptions, not measured destination shares'}
    dump(OUT/'execution_provenance.json',provenance)
    # Refuse any write outside the owned output directory, including engine .pyc files.
    sys.dont_write_bytecode=True
    def audit(event,args):
        if event!='open' or not isinstance(args[0],(str,bytes)):return
        filename,mode,flags=args
        write_mode=isinstance(mode,str) and any(c in mode for c in 'wax+')
        write_flags=isinstance(flags,int) and bool(flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
        if write_mode or write_flags:
            p=Path(filename).resolve()
            assert p.is_relative_to(OUT.resolve()),f'Blocked unexpected write: {p}'
    sys.addaudithook(audit)
    engine,manifest,snap=isolate()
    dump(OUT/'input_manifest.json',manifest)
    events=[e for e in load(snap/'course_endings_current.json') if
            e['included_main'] and e['weekday'] in DAYS and e['end_minute']<=engine.END]
    input_day=Counter()
    for e in events:input_day[e['weekday']]+=e['enrollment']
    assert len(events)==6201 and sum(input_day.values())==156338
    choices,routes,destinations,coverage=engine.build_candidates(events)
    combined=defaultdict(float);modes_mean=defaultdict(float);metadata={}
    conditional_checks=[];scenario_checks=[]
    fields=['scenario','replicate','window','weekday','stop_id','stop_name']
    metrics=[m+'_'+suffix for m in ('all_boarding','first_boarding','transfer_boarding')
             for suffix in ('peak_bin','peak_events','total_events')]
    handles=[];writers={}
    for label,name in [('physical','replicate_stop_peaks.csv'),('directional','replicate_stop_direction_peaks.csv')]:
        f=(OUT/name).open('w',encoding='utf-8-sig',newline='');handles.append(f)
        w=csv.DictWriter(f,fieldnames=fields+(['direction'] if label=='directional' else [])+metrics)
        w.writeheader();writers[label]=w
    try:
        for rep in range(engine.REPS):
            bins,modes,meta,lags,missing=engine.run_rep(events,choices,routes,engine.SEED+rep)
            assert not missing,dict(missing)
            metadata.update(meta)
            first=defaultdict(float)
            for k,v in bins.items():
                assert math.isfinite(v) and v>=0
                combined[k]+=v/engine.REPS
                if k[-1]==0:first[k[:2]]+=v
            for k,v in modes.items():modes_mean[k]+=v/engine.REPS
            for day in DAYS:
                for group in GROUPS:
                    vals={mode:modes.get((day,group,mode),0.0) for mode in ('walk','city_first','shuttle_first','unassigned')}
                    assigned=sum(vals.values());boarding=vals['city_first']+vals['shuttle_first']
                    assert abs(assigned-input_day[day])<1e-6
                    assert abs(first[(day,group)]-boarding)<1e-6
                    conditional_checks.append({'replicate':rep+1,'weekday':day,'destination_group':group,
                        'input_enrollment_events':input_day[day],**vals,'sum_modes':assigned,
                        'first_boarding_events_all_times':first[(day,group)],
                        'mode_conservation_error':assigned-input_day[day],
                        'boarding_link_error':first[(day,group)]-boarding})
                for s in scenarios:
                    w=weights(s)
                    vals={mode:sum(modes.get((day,g,mode),0)*w[g] for g in GROUPS)
                          for mode in ('walk','city_first','shuttle_first','unassigned')}
                    generated=input_day[day]*s['immediate_trip_share']
                    assert abs(sum(vals.values())-generated)<1e-6
                    scenario_checks.append({'scenario':s['name'],'replicate':rep+1,'weekday':day,
                        'generated_trip_events':generated,**vals,'sum_modes':sum(vals.values()),
                        'conservation_error':sum(vals.values())-generated})
            export_rep_peaks(bins,scenarios,rep+1,metadata,writers)
            dump(OUT/'run_progress.json',{'completed_replications':rep+1,'total_replications':engine.REPS,
                'elapsed_seconds':round(time.perf_counter()-began,1)})
            print(f'replication {rep+1}/{engine.REPS}; elapsed {time.perf_counter()-began:.1f}s',flush=True)
    finally:
        for f in handles:f.close()
    cfields=['weekday','destination_group','stop_id','stop_name','direction','route_id','route_name',
             'time_bin','bin_minute','boarding_stage','conditional_trip_events','in_collection_window','lat','lon']
    csv_write('conditional_mean_bins.csv',cfields,mean_rows(combined,metadata))
    csv_write('conditional_mode_conservation_by_rep.csv',list(conditional_checks[0]),conditional_checks)
    csv_write('scenario_mode_conservation_by_rep.csv',list(scenario_checks[0]),scenario_checks)
    csv_write('conditional_mean_modes.csv',['weekday','destination_group','mode','conditional_trip_events'],
        ({'weekday':d,'destination_group':g,'mode':m,'conditional_trip_events':v}
         for (d,g,m),v in sorted(modes_mean.items())))
    sf=['scenario','weekday','stop_id','stop_name','direction','route_id','route_name',
        'time_bin','bin_minute','boarding_stage','expected_trip_events','lat','lon']
    equality={};count=0
    with (OUT/'stop_inflow_5min_scenarios.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=sf);writer.writeheader()
        for s in scenarios:
            sb=scenario_bins(combined,s)
            for (day,stop,direction,rid,b,stage),v in sorted(sb.items()):
                m=metadata[(stop,direction,rid)]
                writer.writerow({'scenario':s['name'],'weekday':day,'stop_id':stop,
                    'stop_name':CANONICAL.get(stop,m['stop_name']),'direction':direction,'route_id':rid,
                    'route_name':m['route_name'],'time_bin':clock(b),'bin_minute':b,'boarding_stage':stage+1,
                    'expected_trip_events':v,'lat':m['lat'],'lon':m['lon']})
                count+=1
            if s['name']=='equal_reference':equality=sb
    # Reproduce the previous equal-destination baseline, independently read from its CSV.
    old_values={}
    with (OLD/'outputs/stop_inflow_5min_scenarios.csv').open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            if r['scenario']=='reference_dorm19p49_depart50':
                key=(r['weekday'],r['stop_id'],r['direction'],r['route_id'],int(r['bin_minute']),int(r['boarding_stage'])-1)
                old_values[key]=float(r['expected_trip_events'])
    assert set(old_values)==set(equality), 'Old equal baseline keys changed'
    reproduction_error=max(abs(old_values[k]-equality[k]) for k in equality)
    assert reproduction_error<=1e-6, reproduction_error
    after=original_inventory();assert before==after,'Original engine or data changed'
    assert sha(original_xls)==xls_hash
    assert sha(ROOT/'scenario_specs.json')==provenance['specs_sha256'],'Scenario specs changed during execution'
    finished=datetime.now(timezone.utc)
    provenance.update(status='complete',finished_at_utc=finished.isoformat(),
        finished_at_kst=finished.astimezone(timezone(timedelta(hours=9))).isoformat(),
        elapsed_seconds=round(time.perf_counter()-began,2),seed=engine.SEED,replications=engine.REPS,
        particles_per_cohort_destination=engine.PARTICLES,scenario_count=len(scenarios),
        weekday_ending_events=len(events),buildings=len({e['building'] for e in events}),
        enrollment_event_sum=sum(input_day.values()),scenario_bin_rows=count,
        original_files_verified_unchanged=len(before),original_xls_verified_unchanged=True,
        equal_baseline_reproduced=True,equal_baseline_max_absolute_error=reproduction_error,
        conditional_mode_checks=len(conditional_checks),scenario_mode_checks=len(scenario_checks),
        input_day=dict(input_day),destination_coordinates=destinations,
        schema_notes={'expected_trip_events':'Mean expected stop-arrival boarding-demand weights, not actual boardings or congestion.',
          'conditional_trip_events':'All enrollment events select this destination and move immediately; no scenario probabilities applied.',
          'boarding_stage':'1 = initial boarding stop arrival; 2 = transfer stop arrival.',
          'direction':'Preserved provider route-direction label; not a standardized compass direction.',
          'time_window':'680 <= bin_minute < 1390; conditional bins additionally retain outside-window events.',
          'replicate_peaks':'Maximum within each independent replication; differs from peak of mean bins.',
          'mode_checks':'Whole modeled day including arrivals before collection window; first-boarding link checks include all times.'},
        assumptions={'source':'Unmodified preserved 2026-11-06 engine and archived route/walking data.',
          'historical_vector':'55.7/99.9, 27.2/99.9, 17.0/99.9. Historical Sillim represented by Daehak point.',
          'dorm_residence':'User-selected scenario; current Gwanak actual residence rate remains unknown.',
          'crowding_feedback':False,'capacity_model':False,'background_passengers':False})
    dump(OUT/'execution_provenance.json',provenance)
    dump(OUT/'original_preservation_check.json',{'status':'PASS','files_verified_unchanged':len(before),
        'original_xls_sha256':xls_hash,'old_outputs_overwritten':False,'specification_unchanged':True})
    print(json.dumps({'status':'complete','elapsed_seconds':provenance['elapsed_seconds'],
        'scenario_bin_rows':count,'equal_baseline_max_error':reproduction_error,
        'original_files_verified_unchanged':len(before)},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
