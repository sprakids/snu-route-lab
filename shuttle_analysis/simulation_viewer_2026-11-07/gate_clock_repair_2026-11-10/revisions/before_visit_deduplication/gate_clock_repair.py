"""One predeclared, data-only gate-clock repair trial; otherwise revert to v7.

Observed queue counts never select a docking radius, phase offset or demand.
"""
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta
import argparse, gzip, hashlib, importlib.util, json, math, statistics, sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
WORK=ROOT/'gate_clock_repair_2026-11-10'
OUT=WORK/'public_data'
SOURCE=ROOT/'weekday_operations_2026-11-10/prepared.json.gz'
REVIEW=ROOT.parent/'monday_model_review_2026-11-09'
REVISION='observed_gate_phase_operations_20261110_v1'
KST=timezone(timedelta(hours=9))
import capacity_model as base
import weekday_operations as old
import gate_access_calibration as gate

TARGETS={'100100250':21,'100100251':9,'100100252':7,'100100263':30,'100100521':70}
RULE={'max_minimum_stop_distance_m':40,'within_best_distance_m':10,'max_track_gap_seconds':300,
      'minimum_detection_coverage_fraction':.85,'maximum_clock_inversion_error_seconds':30,
      'gate_error_at_most_v7':True,'other_old_case_error_tolerance_people':.5,
      'source_window_seconds':[54000,68400],'one_candidate_only':True,
      'demand_capacity_speed_profiles_shuttles_unchanged':True,
      'not_independent_predictive_validation':True}


def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def save(p,x):base.save(p,x)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def second(t):
    v=datetime.fromtimestamp(t,KST);return v.hour*3600+v.minute*60+v.second
def distance(r,s):return math.hypot((r['lat']-s['lat'])*111195,(r['lon']-s['lon'])*111195*math.cos(math.radians(s['lat'])))


def detections():
    stops=read(REVIEW/'sources/route_stops.json');lookup={rid:{int(s['seq']):s for s in rs} for rid,rs in stops.items()}
    unique={}
    for line in gzip.decompress((REVIEW/'sources/collector-2026-11-09.json.gz').read_bytes()).splitlines():
        for r in json.loads(line)['vehicles']:
            if r['route_id'] not in TARGETS:continue
            key=r['route_id'],r['id'],r['provided_at']
            if key not in unique or r['captured_at']<unique[key]['captured_at']:unique[key]=r
    tracks=defaultdict(list)
    for (rid,vid,_),r in unique.items():
        if 0<=r['captured_at']-r['provided_at']<=300:tracks[rid,vid].append(r)
    results=defaultdict(list);quality=defaultdict(Counter)
    for (rid,vid),rows in tracks.items():
        rows.sort(key=lambda r:r['provided_at']);visit=[];prev=None
        def close():
            if not visit:return
            stop=lookup[rid][TARGETS[rid]]
            # Count source visits independently of whether docking is detected.
            reference=second(visit[0]['provided_at'])
            candidates=[(distance(r,stop),r) for r in visit if r['at_stop']]
            if not candidates:
                if 54000<=reference<68400:quality[rid]['visits_without_docking']+=1;quality[rid]['peak_visits']+=1
                return
            best=min(d for d,r in candidates)
            if best>RULE['max_minimum_stop_distance_m']:
                if 54000<=reference<68400:quality[rid]['distant_docking']+=1;quality[rid]['peak_visits']+=1
                return
            first=next(r for d,r in candidates if d<=best+RULE['within_best_distance_m'])
            at=second(first['provided_at'])
            if not 54000<=at<68400:return
            quality[rid]['peak_visits']+=1;quality[rid]['docking_visits']+=1
            results[rid].append({'second':at,'minimum_distance_m':best,
                'chosen_distance_m':distance(first,stop),'source':'first_stopped_sample_within_10m_of_closest_stopped_position',
                'provided_at_kst':datetime.fromtimestamp(first['provided_at'],KST).isoformat(),
                'arrival_is_approximate':True,'observed_boarding_time':False})
        for r in rows:
            seq=int(r['section_order'])
            reset=prev is not None and (seq<int(prev['section_order']) or r['provided_at']-prev['provided_at']>300 or
                lookup[rid][seq]['direction']!=lookup[rid][int(prev['section_order'])]['direction'])
            if reset or seq!=TARGETS[rid]:close();visit=[]
            if seq==TARGETS[rid]:visit.append(r)
            prev=r
        close()
    for rid in results:results[rid].sort(key=lambda r:r['second'])
    return results,{rid:dict(q) for rid,q in quality.items()}


def at_reference(route,start,index):
    t=start
    for k in range(index):t+=old.segment_seconds(route,t)[k]
    return t


def inverse_clock(route,target,index,old_seconds):
    if index==0:return float(target),0.
    guess=target-old_seconds;best=(float('inf'),guess)
    # Profiles are piecewise constant in segment-entry time; solve within each
    # sampled region, then verify the result rather than assume global monotonicity.
    grid=[guess]+list(range(max(0,int(target-max(3600,old_seconds*3))),int(target)+1,30))
    for sample in grid:
        value=target-(at_reference(route,sample,index)-sample)
        for _ in range(3):
            actual=at_reference(route,value,index);error=abs(actual-target)
            if error<best[0]:best=(error,value)
            if error<1e-7:return value,error
            value+=target-actual
    return best[1],best[0]


def prepare():
    WORK.mkdir(exist_ok=True);OUT.mkdir(exist_ok=True)
    if (WORK/'prepared.json.gz').exists():return read(WORK/'prepared.json.gz')
    if (WORK/'experiment_plan.json').exists():raise RuntimeError('Inspect preserved preparation before retry')
    save(WORK/'experiment_plan.json',{'status':'predeclared','rules':RULE,'source_v8_sha256':sha(SOURCE),
        'raw_monday_sha256':sha(REVIEW/'sources/collector-2026-11-09.json.gz'),'builder_sha256':sha(Path(__file__))})
    observed,quality=detections();save(WORK/'docking_observations.json',observed);save(WORK/'docking_quality.json',quality)
    for rid in TARGETS:
        q=quality[rid];fraction=q.get('docking_visits',0)/max(1,q['peak_visits'])
        if fraction<RULE['minimum_detection_coverage_fraction']:raise RuntimeError(f'Insufficient docking coverage {rid}: {fraction:.3f}; do not impute missing buses')
    bundle=read(SOURCE);common=bundle['prepared']['common'];ops=common['city_operations'];changes=[]
    for rid,seq in TARGETS.items():
        route=ops['routes'][rid];index=next(i for i,s in enumerate(route['stops']) if s['seq']==seq)
        baseline=common['route_info'][rid]['offsets'][index]
        aligned=[]
        for observation in observed[rid]:
            start,error=inverse_clock(route,observation['second'],index,baseline)
            if error>RULE['maximum_clock_inversion_error_seconds']:raise RuntimeError(f'Cannot align {rid} within detection precision')
            aligned.append(start);changes.append({'route_id':rid,'reference_seq':seq,'observed_reference_second':observation['second'],
                'modeled_first_departure_second':start,'alignment_error_seconds':error})
        assert len(set(aligned))==len(aligned)
        for day in range(5):
            keep=[t for t in route['departures'][str(day)] if not 54000<=at_reference(route,t,index)<68400]
            route['departures'][str(day)]=sorted(keep+aligned)
        route['phase_reference']={'source':'Monday_GPS_docking_template_transferred_to_all_weekdays',
            'reference_seq':seq,'reference_stop_id':route['stops'][index]['id'],'observed_docking_events':len(aligned),
            'actual_boarding_time_verified':False}
    ops['revision']=REVISION;ops['phase_repair']={'rules':RULE,'source_dates':['2026-11-09'],
        'source_vehicle_ids_published':False,'Monday_reconstruction_other_weekdays_transfer':True}
    common['city_speed_revision']=REVISION;common['data_version']=9
    common['weekday_operations']['revision']=REVISION
    common['city_clock_note']='월요일 실제 정문 근방 도킹 시각을 참조한 시계 보정 후보. 다른 평일은 전이 추정이며 승차 시각 실측은 아님.'
    assert bundle['prepared']['plans']==read(SOURCE)['prepared']['plans']
    base.packed(WORK/'prepared.json.gz',bundle);save(WORK/'city_operations.json',ops);save(WORK/'clock_alignment.json',changes)
    save(WORK/'preparation_verification.json',{'status':'PASS','rules':RULE,'quality':quality,'alignments':len(changes),
        'maximum_alignment_error_seconds':max(r['alignment_error_seconds'] for r in changes),'demand_unchanged':True,
        'capacity_unchanged':True,'shuttle_unchanged':True,'segment_profiles_unchanged':True})
    return bundle


def pilot():
    bundle=prepare();log=WORK/'pilot-started.json'
    if log.exists():raise RuntimeError('One candidate pilot already consumed; inspect existing evidence')
    save(log,{'status':'started','day':'월','scenario':'peak','rules':RULE})
    engine_path=ROOT/'weekday_operations_2026-11-10/operations_engine.py'
    spec=importlib.util.spec_from_file_location('gate_clock_repair_engine',engine_path)
    engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine);engine.WORK=WORK;engine.OUT=OUT;base.OUT=OUT
    data=engine.simulate(bundle,'월','peak')
    import finish_weekday_operations as f
    f.WORK=WORK;f.OUT=OUT;independent=f.checker();checked=independent.check(bundle,'peak','월','mon')
    save(WORK/'pilot-independent-verification.json',checked)
    common=bundle['prepared']['common'];oldfits=gate.minute_summary(read(ROOT/'public/data/capacity_v7/peak-mon.json'),common)
    before=gate.minute_summary(read(ROOT/'public/data/capacity_v8/peak-mon.json'),common);after=gate.minute_summary(data,common)
    gate_ok=after[-1]['expected_absolute_distance_to_report_interval']<=oldfits[-1]['expected_absolute_distance_to_report_interval']+1e-6
    other_ok=all(a['expected_absolute_distance_to_report_interval']<=b['expected_absolute_distance_to_report_interval']+.5 for a,b in zip(after[:-1],oldfits[:-1]))
    result={'status':'PASS' if gate_ok and other_ok else 'REJECTED_REVERT_TO_V7','gate_at_most_v7':gate_ok,'other_two_not_materially_worse':other_ok,
        'v7':oldfits,'v8':before,'candidate':after,'independent_validation':False,'rules':RULE}
    save(WORK/'pilot-decision.json',result);print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pilot',action='store_true');args=p.parse_args()
    if args.pilot:pilot()
    else:prepare();print('PREPARED',REVISION)
