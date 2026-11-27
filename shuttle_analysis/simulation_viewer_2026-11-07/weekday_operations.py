"""Transfer saved Monday operations to all modeled weekdays, with explicit provenance.

Demand and shuttle clocks stay unchanged. No collection or network access.
"""
from pathlib import Path
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import argparse, bisect, csv, gzip, hashlib, importlib.util, json, math, statistics, subprocess, sys

ROOT = Path(__file__).resolve().parent
WORK = ROOT / 'weekday_operations_2026-11-10'
OUT = WORK / 'public_data'
REVIEW = ROOT.parent / 'monday_model_review_2026-11-09'
SOURCE = ROOT / 'gate_access_calibration_2026-11-09/candidates/alpha_075/prepared.json.gz'
REVISION = 'weekday_transfer_operations_20261110_v1'
KST = timezone(timedelta(hours=9))
sys.dont_write_bytecode = True
import capacity_model as base


def read(p): return json.loads(gzip.decompress(p.read_bytes()) if p.suffix == '.gz' else p.read_bytes())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p, x): base.save(p, x)
def csvout(p, values):
    if not values: return
    with p.open('w', encoding='utf-8-sig', newline='') as f:
        w=csv.DictWriter(f, list(values[0])); w.writeheader(); w.writerows(values)
def second(t):
    d=datetime.fromtimestamp(t,KST); return d.hour*3600+d.minute*60+d.second
def near(r,s):
    return math.hypot((r['lat']-s['lat'])*111195,(r['lon']-s['lon'])*111195*math.cos(math.radians(r['lat']))) <= 60
def band(t):
    if 40800 <= t < 54000: return '11:20-15:00'
    if 54000 <= t < 68400: return '15:00-19:00'
    if 68400 <= t <= 83400: return '19:00-23:10'
    return 'unobserved'
def protect():
    paths=[]
    for dataset in ('capacity_v3','capacity_v4','capacity_v5','capacity_v6','capacity_v7'):
        paths.extend((ROOT/'public/data'/dataset).glob('*'))
    paths.extend((ROOT/'public/routing-model/releases').glob('*.json'))
    paths.extend([SOURCE,ROOT/'city_capacity_model.py',ROOT/'verify_city.py',ROOT/'prepare_city.py'])
    return {p.relative_to(ROOT).as_posix():sha(p) for p in paths if p.is_file()}


def derive_observations():
    stoplist=read(REVIEW/'sources/route_stops.json'); stops={rid:{int(s['seq']):s for s in rows} for rid,rows in stoplist.items()}
    bad={tuple(x) for x in read(REVIEW/'analysis/ambiguous_provider_keys.private.json')}
    unique={}
    for line in gzip.decompress((REVIEW/'sources/collector-2026-11-09.json.gz').read_bytes()).splitlines():
        for r in json.loads(line)['vehicles']:
            k=r['route_id'],r['id'],r['provided_at']
            if k not in unique or r['captured_at']<unique[k]['captured_at']:unique[k]=r
    tracks=defaultdict(list)
    for k,r in unique.items():
        if k in bad or not 0 <= r['captured_at']-r['provided_at'] <= 300:continue
        tracks[r['route_id'],r['id']].append(r)
    # Away from a terminal/turn so the reference crossing is direction-specific.
    refs={'100100250':13,'100100251':2,'100100252':7,'100100253':14,
          '100100263':30,'100100521':70,'120900011':24,'120900012':20}
    crosses=defaultdict(list); totals=defaultdict(list); near_n=0
    for (rid,vid),rs in tracks.items():
        rs.sort(key=lambda x:x['provided_at']); prev=None; seen={}; last_event=None
        for r in rs:
            seq=int(r['section_order']); s=stops[rid][seq]
            reset=prev is None or seq<int(prev['section_order']) or r['provided_at']-prev['provided_at']>300 or s['direction']!=stops[rid][int(prev['section_order'])]['direction']
            if reset:seen={};last_event=None
            if not reset:
                old=int(prev['section_order']); width=r['provided_at']-prev['provided_at']
                if old < refs[rid] <= seq:
                    crosses[rid].append({'lower':prev['provided_at'],'upper':r['provided_at'],'width':width,'jump':seq-old})
            if r['at_stop'] and near(r,s) and seq not in seen:
                seen[seq]=True
                tight=not reset and 0<r['provided_at']-prev['provided_at']<=45
                event={'seq':seq,'lower':prev['provided_at'] if tight else None,'upper':r['provided_at'],'tight':tight}
                if last_event and last_event['tight'] and tight and seq-last_event['seq']==1:
                    low=event['lower']-last_event['upper']; high=event['upper']-last_event['lower']
                    if 0<low<=high<=600:
                        totals[rid,seq,int(second((last_event['lower']+last_event['upper'])/2)//3600)].append((low+high)/2)
                        near_n+=1
                last_event=event
            prev=r
    samples=defaultdict(list); hwquality=[]
    for rid,values in crosses.items():
        values.sort(key=lambda r:r['lower']+r['upper'])
        for a,b in zip(values,values[1:]):
            ta=(a['lower']+a['upper'])/2; tb=(b['lower']+b['upper'])/2; label=band(second(tb))
            if label=='unobserved' or band(second(ta))!=label: continue
            window=45 if label=='15:00-19:00' else 180
            if any(r['width']>window or r['jump']>3 for r in (a,b)):continue
            lower=b['lower']-a['upper']; upper=b['upper']-a['lower']
            if not 0<lower<=upper<=3600:continue
            samples[rid,label].append((tb-ta,(lower,upper)))
    return refs, samples, totals, near_n


def segment_seconds(route, at):
    # Half-open profiles, except the final unobserved sentinel.
    profiles=route['segment_profiles']['0']
    i=bisect.bisect_right([p[0] for p in profiles],at)-1
    return profiles[max(0,min(len(profiles)-1,i))][2]


def stop_times(route, start):
    result=[float(start)]
    for k in range(len(route['stops'])-1):
        result.append(result[-1]+segment_seconds(route,result[-1])[k])
    return result


def prepare():
    WORK.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)
    hashes={'source_v7':sha(SOURCE),'raw_monday':sha(REVIEW/'sources/collector-2026-11-09.json.gz'),
            'speeds':sha(REVIEW/'analysis/transport_observations/provider_section_speed_hourly.csv'),
            'builder':sha(Path(__file__))}
    cached=WORK/'prepared.json.gz'
    if cached.exists():
        bundle=read(cached); assert bundle['weekday_operations_inputs']==hashes, 'Changed builder/inputs; preserve previous work before rerun'
        return bundle
    save(WORK/'protected_hashes.json',protect())
    bundle=read(SOURCE); common=bundle['prepared']['common']; routes=bundle['prepared']['routes']
    # Restore descriptive UI fields not present in the original prepared cache.
    frozen=read(ROOT/'public/data/capacity_v7/common.json')
    common['city_route_stops']=frozen['city_route_stops']
    refs, samples, observed_totals, near_n=derive_observations()
    speeds={}
    with (REVIEW/'analysis/transport_observations/provider_section_speed_hourly.csv').open(encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            if int(r['n'])>=3:speeds[r['route_id'],int(r['to_seq']),int(r['hour'])]=r
    ops={'schema':'snu_city_operations_v1','revision':REVISION,
         'network_sha256':sha(ROOT.parent/'app/data/network.json'),'coverage_start_seconds':40800,'coverage_end_seconds':83400,
         'weekdays':[0,1,2,3,4],'source_dates':['2026-11-09'],'transfer_estimate':True,
         'source_capture_window_kst':['2026-11-09T11:20:00+09:00','2026-11-09T23:10:00+09:00'],
         'includes_destination_dwell':True,'dwell_added_separately':False,
         'time_rule':'choose total segment seconds at segment-entry time, half-open profiles',
         'dwell_identified_from_measurement':False,'campus_max_kmh':40,'external_max_kmh':65,
         'external_background_people_included':False,
         'limitations':['Monday-only transfer to all five modeled weekdays; no out-of-sample accuracy validation',
            'Headway windows are inferred section crossings, not an operator timetable; missed vehicles remain possible',
            'Near-stop elapsed times include stopping and detection uncertainty; provider speeds are section indicators',
            'Shuttle clocks unchanged; city grade codes are not mapped to persons'], 'routes':{}}
    changes=[]; headways=[]; clocks={}
    bounds=[0,40800,*range(43200,82801,3600),83400,172800]
    for rid,info in common['route_info'].items():
        if not info.get('city'): continue
        r=routes[rid]; original=[b-a for a,b in zip(info['offsets'],info['offsets'][1:])]
        profiles=[]
        for low,high in zip(bounds,bounds[1:]):
            hour=low//3600; durations=[]
            for k,pid in enumerate(info['segments']):
                seq=int(r['stops'][k+1]['seq']); motion=common['motion_profiles'][str(pid)]
                candidates=observed_totals.get((rid,seq,hour),[]); speed=speeds.get((rid,seq,hour))
                if low<40800 or low>=83400:
                    value=original[k]; source='preserved_v7_unobserved_time'; n=0
                elif len(candidates)>=5:
                    value=max(motion['duration'],statistics.median(candidates));source='Monday_near_stop_adjacent_total';n=len(candidates)
                elif speed:
                    value=max(motion['duration'],motion['d'][-1]/(float(speed['median_speed_kmh'])/3.6));source='Monday_provider_section_speed_reference';n=int(speed['n'])
                else:value=original[k];source='preserved_v7_insufficient_samples';n=len(candidates)
                assert value>=motion['duration']-1e-5
                durations.append(value)
                changes.append({'route_id':rid,'route':r['name'],'from_seq':r['stops'][k]['seq'],'to_seq':seq,
                    'start_second':low,'end_second':high,'old_seconds':original[k],'new_seconds':value,'source':source,'n':n,
                    'kinematic_minimum_seconds':motion['duration'],'dwell_separately_measured':False})
            profiles.append([low,high,durations])
        route={'name':r['name'],'stops':[{'id':s['id'],'seq':int(s['seq'])} for s in r['stops']],
               'departures':{},'segment_profiles':{str(d):profiles for d in range(5)},
               'reference_seq':refs[rid],'headway_bands':{},'official_plan':info['plan'],
               'origin_to_modeled_first_seconds':info.get('origin_to_modeled_first_stop_seconds',0),
               'partial_route':bool(r.get('partial_route')),'includes_destination_dwell':True}
        nominal=info['plan']['headway_seconds']
        for label in ['11:20-15:00','15:00-19:00','19:00-23:10']:
            all_values=samples.get((rid,label),[])
            # A missed bus can create long gaps: keep only bounded, plausible
            # intervals and still label the entire distribution a transfer estimate.
            values=[x for x,(lo,hi) in all_values if 60<=x<=min(1800,3*nominal)]
            # Two-minute off-peak polling can miss entire section crossings,
            # particularly on the village routes. Do not turn that into a
            # fictitious service cut outside the high-resolution peak window.
            use_observed=label=='15:00-19:00' and len(values)>=5
            applied=values if use_observed else [nominal]
            route['headway_bands'][label]={'seconds':applied,'sample_intervals':len(values),
                'discarded_outside_diagnostic_range':len(all_values)-len(values),
                'source':'Monday_section_crossing_distribution' if use_observed else 'official_representative_fallback'}
            headways.append({'route_id':rid,'route':r['name'],'reference_seq':refs[rid],'band':label,'n':len(values),
                'official_seconds':nominal,'applied_median_seconds':statistics.median(applied),
                'applied_min_seconds':min(applied),'applied_max_seconds':max(applied),'source':route['headway_bands'][label]['source']})
        ref_index=next(i for i,s in enumerate(r['stops']) if int(s['seq'])==refs[rid])
        first=info['plan']['first_seconds']+route['origin_to_modeled_first_seconds']
        last=info['plan']['last_seconds']+route['origin_to_modeled_first_seconds']
        for day in range(5):
            starts=[];at=float(first);index=0
            while at<=last+1e-6:
                starts.append(at); reference_time=stop_times(route,at)[ref_index]; label=band(reference_time)
                distribution=route['headway_bands'].get(label,{'seconds':[nominal]})['seconds']
                shift=int.from_bytes(hashlib.sha256(f'weekday-transfer-v1:{rid}:{day}:{label}'.encode()).digest()[:4],'big')
                gap=distribution[(index+shift)%len(distribution)]
                assert gap>=60;at+=gap;index+=1
            if starts[-1]<last-1e-6:starts.append(float(last))
            route['departures'][str(day)]=starts
            clocks[rid,str(day)]=[stop_times(route,at) for at in starts]
        ops['routes'][rid]=route
    common['city_operations']=ops;common['city_speed_revision']=REVISION;common['data_version']=8
    common['city_clock_note']='월요일 관측 통과간격 분포·시간대별 구간시간을 월~금에 전이한 운행 시나리오. 실시간/요일별 검증 전.'
    common['city_speed_note']='교내40·교외65 km/h 상한 유지. 시내 구간 진입시각별 총시간 적용, 정차 재가산 없음. 셔틀 시각은 v7 유지.'
    common['weekday_operations']={k:v for k,v in ops.items() if k!='routes'}
    common['weekday_operations']['source_counts']={'provider_observations':77931,'near_stop_adjacent_pairs':near_n}
    common['policies']={'city':{'label':'평일 운행 보정 모형'}}
    bundle['weekday_operations_inputs']=hashes
    base.packed(cached,bundle); save(WORK/'city_operations.json',ops)
    # Numeric schedule only; no source vehicle identifiers.
    save(WORK/'vehicle_stop_clocks.json',{'revision':REVISION,'routes':{rid:{str(d):clocks[rid,str(d)] for d in range(5)} for rid in ops['routes']}})
    csvout(WORK/'segment_profile_changes.csv',changes);csvout(WORK/'headway_transfer_summary.csv',headways)
    assert protect()==read(WORK/'protected_hashes.json')
    save(WORK/'preparation_verification.json',{'status':'PASS','revision':REVISION,'weekdays':[0,1,2,3,4],
        'same_v7_plans_sha256':hashlib.sha256(json.dumps(bundle['prepared']['plans'],sort_keys=True).encode()).hexdigest(),
        'transfer_estimate':True,'observed_source_days':1,'out_of_sample_validated':False,
        'segment_profiles':len(changes),'headway_bands':len(headways),'external_background_people_included':False,
        'demand_unchanged':True,'shuttle_clock_unchanged':True,'source_hashes':hashes})
    return bundle


def build_engine():
    """Isolated extension of the preserved FIFO engine; original file untouched."""
    src=(ROOT/'city_capacity_model.py').read_text(encoding='utf-8')
    old="""        clocks=planned_departures(info['plan']) if info.get('city') else base.dispatches(rid,scenario)
        prefix=info.get('origin_to_modeled_first_stop_seconds',0.)
        for clock in clocks:
            t0=clock+prefix-info['offsets'][info['anchor']]"""
    new="""        if info.get('city'):
            day_index=list(base.DAYS).index(day)
            route=common['city_operations']['routes'][rid]
            journeys=[operations.stop_times(route,t) for t in route['departures'][str(day_index)]]
        else:
            journeys=[[t-info['offsets'][info['anchor']]+x for x in info['offsets']] for t in base.dispatches(rid,scenario)]
        for times in journeys:
            t0=times[0]"""
    assert old in src;src=src.replace(old,new,1)
    replacements={
      "t0+info['offsets'][-1]<0":"times[-1]<0",
      "'t0':t0,'onboard':[]":"'t0':t0,'times':times,'onboard':[]",
      "for k,offset in enumerate(info['offsets']):\n                when=t0+offset;":"for k,when in enumerate(times):\n                ",
      "t=dep+info['offsets'][end]-info['offsets'][k]+chosen['next_walk'][1]*factor":"t=vehicles[vid]['times'][end]+chosen['next_walk'][1]*factor",
      "end=vehicle['t0']+info['offsets'][end_index]":"end=vehicle['times'][end_index]",
      "vehicle['t0']+info['offsets'][k+1]":"vehicle['times'][k+1]"}
    for old,new in replacements.items():
        assert old in src,old;src=src.replace(old,new)
    src='import weekday_operations as operations\n'+src
    target=WORK/'operations_engine.py'
    if target.exists():assert target.read_text(encoding='utf-8')==src, 'Preserve differing prior engine before replacement'
    else:target.write_text(src,encoding='utf-8')
    spec=importlib.util.spec_from_file_location('weekday_operations_engine',target);engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)
    engine.WORK=WORK;engine.OUT=OUT;return engine


def run(day,scenario):
    bundle=prepare();engine=build_engine();base.OUT=OUT
    data=engine.simulate(bundle,day,scenario)
    save(WORK/f'run-{scenario}-{base.DAYS[day]}.json',{'status':'PASS','revision':REVISION,'report':data['report']})


def run_all():
    prepare();build_engine()
    jobs=[(d,s) for s in base.SCENARIOS for d in base.DAYS]
    def worker(job):
        day,scenario=job;did=base.DAYS[day];receipt=WORK/f'run-{scenario}-{did}.json'
        if receipt.exists():assert read(receipt)['status']=='PASS';print('REUSED',scenario,did,flush=True);return
        log=WORK/f'run-{scenario}-{did}.log';assert not log.exists(),f'Inspect previous failure before retry: {log}'
        with log.open('w',encoding='utf-8') as f:
            r=subprocess.run([sys.executable,str(Path(__file__)),'--day',day,'--scenario',scenario],stdout=f,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert r.returncode==0,(scenario,did,str(log));print('COMPLETE',scenario,did,flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(worker,jobs))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepare-only',action='store_true');p.add_argument('--all',action='store_true')
    p.add_argument('--day',choices=list(base.DAYS));p.add_argument('--scenario',choices=base.SCENARIOS);args=p.parse_args()
    if args.all:run_all()
    elif args.day and args.scenario:run(args.day,args.scenario)
    else:prepare();build_engine();print('PREPARED',REVISION,flush=True)
