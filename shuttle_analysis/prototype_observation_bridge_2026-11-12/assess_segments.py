"""Freeze peer evidence and evaluate a predeclared day-split private correction."""
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone
import copy, csv, gzip, hashlib, json
from segment_calibration import TRAIN_DATES, CHECK_DATES, collect_training, estimate, profile_at, error_summary

ROOT = Path(__file__).resolve().parent
ANALYSIS = ROOT.parent
PARENT = ANALYSIS / 'prototype_followup_261110193823'
PEER = ANALYSIS / 'collected_data_review_2026-11-12'

def sha_bytes(value): return hashlib.sha256(value).hexdigest()
def sha(path): return sha_bytes(path.read_bytes())
def read(path):
    b=path.read_bytes()
    return json.loads(gzip.decompress(b) if path.suffix=='.gz' else b)
def save(path, value):
    assert not path.exists(), f'Preserve an existing result: {path}'
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')
def csvout(path, rows):
    assert not path.exists()
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    assert not (ROOT/'assessment-started.json').exists(), 'One owned assessment; preserve prior attempts.'
    source=PEER/'observed_intervals.json'
    inputs={str(p):sha(p) for p in (source,PEER/'analyze_saved.py',PEER/'analysis_summary.json',ROOT/'PLAN.md',ROOT/'segment_calibration.py')}
    save(ROOT/'assessment-started.json',{'status':'STARTED','inputs':inputs,'training_dates':TRAIN_DATES,'check_dates':CHECK_DATES,
         'production_writes':False,'model_reruns':0,'minimum_train_intervals':5})
    snapshot=ROOT/'source_snapshot';snapshot.mkdir()
    raw=source.read_bytes();assert sha_bytes(raw)==inputs[str(source)]
    (snapshot/'observed_intervals.json.gz').write_bytes(gzip.compress(raw,mtime=0))
    for name in ('analyze_saved.py','analysis_summary.json'):
        b=(PEER/name).read_bytes();assert sha_bytes(b)==inputs[str(PEER/name)];(snapshot/name).write_bytes(b)
    data=json.loads(raw);training=collect_training(data['travel'])
    bundle=read(PARENT/'frozen/prepared_capacity44_pair.json.gz');common=bundle['prepared']['common']
    old=read(PARENT/'frozen/operations_distribution_v8.json');new=copy.deepcopy(old)
    cells=[];mapping={}
    for rid,route in new['routes'].items():
        info=common['route_info'][rid]
        for k,(left,right) in enumerate(zip(route['stops'],route['stops'][1:])):
            key=(rid,int(left['seq']),int(right['seq']))
            assert key not in mapping;mapping[key]=k
        for day,profiles in route['segment_profiles'].items():
            for low,high,durations in profiles:
                if low<40800 or low>=83400:continue
                hour=int(low//3600)
                for k,(left,right) in enumerate(zip(route['stops'],route['stops'][1:])):
                    key=(rid,int(left['seq']),int(right['seq']),hour)
                    values=training.get(key,[])
                    minimum=common['motion_profiles'][str(info['segments'][k])]['duration']
                    prior=durations[k];value,why=estimate(values,prior,minimum);durations[k]=value
                    if day=='2':cells.append({'route':rid,'name':route['name'],'from_seq':key[1],'to_seq':key[2],
                        'start_second':low,'end_second':high,'training_interval_n':len(values),
                        'old_seconds':prior,'candidate_seconds':value,'kinematic_minimum_seconds':minimum,'source':why})
    new.update(revision='private_tuesday_segment_medians_20261112_v1',
       source_dates=sorted(set(old['source_dates'])|set(TRAIN_DATES)),
       segment_training_dates=list(TRAIN_DATES),segment_model_built_at=datetime.now(timezone.utc).isoformat(),
       retained_headway_source_dates=old['source_dates'],heldout_diagnostic_dates=list(CHECK_DATES),
       segment_measurement='Elapsed between adjacent detected stop passages, includes detection/dwell uncertainty; not isolated running or boarding time',
       clock_policy='Existing departure grids and physical capacities unchanged; only supported hourly segment durations replaced',
       independent_queue_accuracy='NOT_EVALUABLE')
    new['limitations']=[x for x in old['limitations'] if not x.startswith('Monday-only transfer')]+[
       'Segment medians trained on one Tuesday and transferred to modeled weekdays; no weekday-effect identification',
       'Departure/headway distributions retained from earlier Monday transfer scenario, not newly measured shuttle dispatch',
       'One held-out Wednesday of detected-stop intervals is not independent passenger-wait or queue validation',
       'Observed intervals are correlated within vehicle/day; no nominal sample-based confidence interval is supplied']
    baseline=defaultdict(list);candidate=defaultdict(list);supported=defaultdict(int);unknown=0
    for row in data['travel']:
        if row['day'] not in CHECK_DATES or int(row['to_seq'])!=int(row['from_seq'])+1:continue
        rid=row['route'];key=(rid,int(row['from_seq']),int(row['to_seq']))
        if key not in mapping:unknown+=len(row['seconds']);continue
        at=max(40800,min(83399,int(row['hour'])*3600+1800));k=mapping[key]
        before=profile_at(old['routes'][rid],at)[k];after=profile_at(new['routes'][rid],at)[k]
        for seconds in row['seconds']:
            for group in (rid,'ALL'):
                baseline[group].append(before-seconds);candidate[group].append(after-seconds)
                supported[group]+=int(len(training.get((*key,int(row['hour'])),[]))>=5)
    comparison=[{'route':rid,'name':old['routes'].get(rid,{}).get('name','ALL'),
        'n':len(baseline[rid]),'supported_training_intervals':supported[rid],
        **{'old_'+k:v for k,v in error_summary(baseline[rid]).items() if k!='n'},
        **{'candidate_'+k:v for k,v in error_summary(candidate[rid]).items() if k!='n'}} for rid in sorted(baseline)]
    allrow=next(x for x in comparison if x['route']=='ALL');assert allrow['n']>0
    accepted=allrow['candidate_mae_seconds']<allrow['old_mae_seconds']
    changed=sum(abs(r['candidate_seconds']-r['old_seconds'])>1e-9 for r in cells)
    # Fair isolation: do not silently change supply, routes or stop directions.
    for rid in old['routes']:
        assert old['routes'][rid]['departures']==new['routes'][rid]['departures']
        assert old['routes'][rid]['stops']==new['routes'][rid]['stops']
    save(ROOT/'operations_observed_train_v1.json',new)
    csvout(ROOT/'segment_corrections.csv',cells);csvout(ROOT/'day_split_time_comparison.csv',comparison)
    result={'status':'PASS_DETECTED_INTERVAL_MAE' if accepted else 'NOT_SELECTED_DETECTED_INTERVAL_MAE',
        'training_dates':TRAIN_DATES,'heldout_diagnostic_dates':CHECK_DATES,'selection_rule':'predeclared global detected-interval MAE decreases; not final model validation',
        'model_input_connection_eligible':accepted,'production_replacement_allowed':False,'queue_accuracy':'NOT_EVALUABLE',
        'profile_cells':len(cells),'changed_profile_cells':changed,'mapped_check_intervals':allrow['n'],
        'unmapped_check_intervals':unknown,'comparison':comparison,'inputs':inputs,
        'outputs':{name:sha(ROOT/name) for name in ('operations_observed_train_v1.json','segment_corrections.csv','day_split_time_comparison.csv')},
        'shuttle_clocks_changed':False,'vehicle_capacity_changed':False,'headways_reestimated':False,
        'known_limit':'Point detection times include GPS/stop flag and provider timing error; rows are not independent vehicles, riders, or days.'}
    save(ROOT/'assessment.json',result)
    print(result['status'],'cells',changed,'check_intervals',allrow['n'],'MAE',allrow['old_mae_seconds'],allrow['candidate_mae_seconds'],flush=True)

if __name__=='__main__':main()
