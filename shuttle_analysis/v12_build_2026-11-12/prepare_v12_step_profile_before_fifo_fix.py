"""Build a private numeric-ID V12 release, with every source assigned an explicit role."""
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime,timezone,timedelta
import copy,csv,gzip,hashlib,json,shutil
from empirical_v12 import Evidence,ordinal_grade,period
from v12_supply import anchored_departures

ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent
PARENT=ANALYSIS/'prototype_observed_261112104829'
PEER=ANALYSIS/'collected_data_review_2026-11-12'
BRIDGE=ANALYSIS/'prototype_observation_bridge_2026-11-12'
KST=timezone(timedelta(hours=9))
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists(),str(p)
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
def csvout(p,rows):
    assert not p.exists()
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)

def evidence_data(ops):
    raw=read(PEER/'observed_intervals.json');hw={};hp=defaultdict(list);segments={}
    for r in raw['headways']:
        if r['day']!='2026-11-10':continue
        values=r['seconds'];key=f'{r["route"]}|{r["seq"]}|{r["hour"]}'
        hw[key]={'seconds':values,'source_day':r['day']}
        hp[f'{r["route"]}|{r["seq"]}|{period(r["hour"]*3600)}'].extend(values)
    for r in raw['travel']:
        if r['day']=='2026-11-10' and r['to_seq']==r['from_seq']+1:
            segments[f'{r["route"]}|{r["from_seq"]}|{r["to_seq"]}|{r["hour"]}']={'seconds':r['seconds']}
    grades=defaultdict(lambda:[0]*4);tracks=defaultdict(list)
    with (PEER/'deduplicated_grade_passages.csv').open(encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            if r['day']!='2026-11-10':continue
            at=float(r['at']);hour=datetime.fromtimestamp(at,KST).hour;level=ordinal_grade(r['grade'])
            assert level is not None
            grades[f'{r["route"]}|{r["seq"]}|{hour}'][level]+=1
            tracks[r['route'],r['vehicle'],r['trip']].append((at,int(r['seq']),level))
    transitions=defaultdict(lambda:[[0]*4 for _ in range(4)])
    for (rid,vid,trip),rows in tracks.items():
        rows.sort()
        for a,b in zip(rows,rows[1:]):
            if b[1]==a[1]+1 and 0<b[0]-a[0]<=180:
                hour=datetime.fromtimestamp(a[0],KST).hour
                transitions[f'{rid}|{a[1]}|{b[1]}|{hour}'][a[2]][b[2]]+=1
    full=defaultdict(lambda:{'known_n':0,'full_n':0})
    with (PEER/'v12_support/full_flags_by_day_route_section_slot.csv').open(encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            if r['day']!='2026-11-10':continue
            hour=int(r['slot_15min'])//4;cell=full[f'{r["route"]}|{r["section"]}|{hour}']
            cell['known_n']+=int(r['known_full_flag_passages']);cell['full_n']+=int(r['full_true_passages'])
    assert sum(r['known_n'] for r in full.values())==28935
    assert sum(r['full_n'] for r in full.values())==14
    return {'schema':'v12_empirical_context_v1','training_dates':['2026-11-10'],
      'headways':hw,'headway_periods':{k:{'seconds':v} for k,v in hp.items()},'segment_samples':segments,
      'grades':{k:{'counts':v} for k,v in grades.items()},'transitions':{k:{'counts':v} for k,v in transitions.items()},
      'full_flags':dict(full),'full_flag_passage_n':28935,'full_flag_true_n':14,
      'route_sequences':{rid:[int(s['seq']) for s in r['stops']] for rid,r in ops['routes'].items()},
      'missing_crowd_routes':['120900011','120900012'],
      'scope':'Training historical proxies, not observed numeric occupancy or independent passengers',
      'headway_censoring':'observed gaps15..3600sec; missed passages and under15sec bunches not identified',
      'source_sha256':{str(p.relative_to(ANALYSIS)):sha(p) for p in (PEER/'observed_intervals.json',PEER/'deduplicated_grade_passages.csv',PEER/'v12_support/full_flags_by_day_route_section_slot.csv')}}

def main():
    pointer=ROOT/'candidate.json';assert not pointer.exists()
    stamp=datetime.now(KST).strftime('%y%m%d%H%M%S');work=ANALYSIS/stamp;work.mkdir()
    names=['artifacts.py','config.json','preferences.py','hazard.py','capacity.py','physics.py','fares.py','prepare.py','policy.py',
      'metrics.py','engine.py','operations.py','run_case.py','fixtures.py','test_prototype.py','test_prediction_integration.py','dwell.py',
      'input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md','analyze_followup.py','validation_metrics.py']
    for name in names:shutil.copy2(PARENT/name,work/name)
    shutil.copytree(PARENT/'frozen',work/'frozen')
    for p in PARENT.glob('physical_paths_*.json.gz'):shutil.copy2(p,work/p.name)
    shutil.copy2(ROOT/'empirical_v12.py',work/'empirical_v12.py')
    shutil.copy2(ROOT/'run_v12.py',work/'run_v12.py')
    shutil.copy2(ROOT/'test_empirical_v12.py',work/'test_empirical_v12.py')
    shutil.copy2(ROOT/'v12_supply.py',work/'v12_supply.py')
    inventory=[];extra=[]
    def source(identifier,category,path,use,consumer,limit):
        target=work/'evidence'/path.relative_to(ANALYSIS)
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
        inventory.append({'id':identifier,'category':category,'source':str(path),'sha256':sha(path),
          'snapshot':str(target.relative_to(work)),'role':use,'consumer':consumer,'limitations':limit})
        extra.append({'path':str(target.relative_to(work)).replace('\\','/'),'sha256':sha(target)})
    for filename in ('calibration_contract.json','calibration_candidates.json','headway_samples_stable_dates.json',
        'adjacent_segment_samples_stable_dates.json','download_manifest.json','observed_intervals.json',
        'analysis_summary.json','deduplicated_grade_passages.csv','provider_section_speeds.csv','grade_transitions.csv'):
        role='runtime_input_and_validation' if filename in ('headway_samples_stable_dates.json','adjacent_segment_samples_stable_dates.json','observed_intervals.json','deduplicated_grade_passages.csv') else 'validation_and_provenance'
        source(filename,'city_bus_observations',PEER/filename,role,'empirical_v12.py / frozen empirical context / validation_v12.py','Train11/10;11/11retrospective; ordinal grades not passenger counts; detection intervals not exact arrival times')
    for p in sorted((PEER/'raw').glob('*.gz')):
        source('raw-'+p.name[:10],'raw_archive',p,'runtime_source' if p.name.startswith('2026-11-10') else 'validation_preserved',
          'prepare_v12.evidence_data / evidence inventory','Older detector dates/weekends not fitted as weekday demand; vehicle/time rows are correlated')
    fields=[ANALYSIS/'field_observations_2026-11-09'/f for f in ('queue_admin_snu_1653.json','queue_culture_1655.json','queue_snu_gate_1703.json','observation_timing_correction.json')]
    fields.append(ANALYSIS/'field_observations_2026-11-10/queue_admin_snu_1523.json')
    for p in fields:source(p.stem,'field_reports',p,'validation_constraint','validation_v12.py / dwell.py micro validation',
      'Latest corrected report; uniform unknown second in minute; dates/direction uncertainties retained; already used in earlier selection; one189s observer only')
    for filename in ('operations_observed_train_v1.json','segment_corrections.csv','assessment.json','peer_contract_reconciliation.json','stop_identity_reconciliation.json'):
        source('bridge-'+filename,'segment_calibration',BRIDGE/filename,'runtime_input' if filename.startswith('operations_') else 'validation_provenance',
         'prepare.py / operations.py / empirical_v12 time_spread','678 supported cells retained; other cells fallback; unmapped5052 check intervals retained separately')
    historical=read(PEER/'v12_support/inventory.json')
    for filename in ('inventory.json','full_flag_availability.json','full_flags_by_day_route_section_slot.csv','future_holdout_rule.json','verification.json'):
        source('support-'+filename,'historical_and_full_flag_context',PEER/'v12_support'/filename,
          'runtime_input' if filename.startswith('full_flags_by') else 'validation_and_provenance',
          'empirical_v12.py / validation_v12.py historical-unit checks','Preserve source dates, units, archive coverage and missingness; no boarding-to-arrival substitution')
    for dataset in historical['datasets']:
        inventory.append({'id':dataset['id'],'category':'historical_boardings_and_card_data','role':'validation_context_or_unavailable',
          'consumer':'validation_v12.py historical_context','source_inventory':'evidence/collected_data_review_2026-11-12/v12_support/inventory.json',
          'source_records':dataset,'limitations':'Preserved source grain; served boardings are not queue arrivals; monthly-hour and daily totals are not joined into observed date-hour cells'})
        for file in dataset.get('usable_files',[]):
            path=ANALYSIS/file['path']
            if path.is_file() and path.stat().st_size<=32*1024*1024:
                source(dataset['id']+'-'+path.name,'historical_derived_validation',path,'validation_context',
                  'validation_v12.py historical_context','Source aggregation preserved; not individual queue/wait truth and not extra modeled trip arrivals')
    save(work/'frozen/historical_evidence_context.json',historical)
    extra.append({'path':'frozen/historical_evidence_context.json','sha256':sha(work/'frozen/historical_evidence_context.json')})
    data=evidence_data(read(BRIDGE/'operations_observed_train_v1.json'));save(work/'frozen/empirical_evidence.json',data)
    extra.append({'path':'frozen/empirical_evidence.json','sha256':sha(work/'frozen/empirical_evidence.json')})
    ops=read(BRIDGE/'operations_observed_train_v1.json');evidence=Evidence(data);anchors=[]
    for rid,route in ops['routes'].items():
        assert all(v==route['segment_profiles']['0'] for v in route['segment_profiles'].values())
        for day in range(5):route['departures'][str(day)],rows=anchored_departures(route,rid,day,evidence);anchors.extend(rows)
    ops.update(revision='v12_directional_stop_anchored_supply_and_empirical_context',version_family='V12',
      release_id=stamp,headway_training_dates=['2026-11-10'],headway_anchor_rule='Observed reference stop passage process inverted through segment-entry profiles; not depot dispatch',
      physical_external_occupancy_identified=False,grade_people_conversion=False,
      inverse_phase_diagnostic_max_abs_seconds=max(abs(r['inverse_error_seconds']) for r in anchors),
      limitations=ops['limitations']+['Reference stop anchored supply is a conditional scenario; missed buses and sub15sec bunches unidentifiable',
        'Inversion at discontinuous hourly profiles can have residual phase error; per-journey diagnostics are retained',
        'Ordinal crowd probabilities only enter an uncalibrated discomfort proxy, never numeric seats'])
    save(work/'frozen/operations_v12_empirical.json',ops);extra.append({'path':'frozen/operations_v12_empirical.json','sha256':sha(work/'frozen/operations_v12_empirical.json')})
    csvout(work/'anchor_supply_diagnostics.csv',anchors)
    cfg=read(work/'config.json');cfg.update(version_family='V12',release_id=stamp,empirical_context=True)
    (work/'config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf8')
    p=work/'prepare.py';s=p.read_text(encoding='utf8');marker="    bundle['prototype_config']=config";assert marker in s
    s=s.replace(marker,"    if config.get('empirical_context'):\n        from empirical_v12 import Evidence\n        bundle['empirical_evidence']=Evidence(read(ROOT/'frozen/empirical_evidence.json'))\n"+marker,1);p.write_text(s,encoding='utf8')
    p=work/'preferences.py';s=p.read_text(encoding='utf8');marker='    wait_cubed:float=0.';assert marker in s
    s=s.replace(marker,marker+'\n    empirical_context:tuple=()',1);p.write_text(s,encoding='utf8')
    p=work/'policy.py';s=p.read_text(encoding='utf8')
    s=s.replace("    paths=bundle['physical_paths'];", "    evidence=bundle.get('empirical_evidence')\n    paths=bundle['physical_paths'];",1)
    s=s.replace("            ledger=state['fare_ledger']", "            contexts=[]\n            ledger=state['fare_ledger']",1)
    marker="                fraction=min(1.,(occupied+state['w'])/vehicle['cap']);crowd+=duration*fraction*fraction";assert marker in s
    s=s.replace(marker,"""                fraction=min(1.,(occupied+state['w'])/vehicle['cap'])
                exposure,context=evidence.context(vehicle['rid'],k,target,when,vehicle['times']) if evidence else (None,None)
                crowd+=duration*fraction*fraction if exposure is None else exposure
                if context is not None:contexts.append(context)""",1)
    marker='return Prediction(cursor,walk,wait,ride,prep,transfers,fee,crowd,fatigue,first_wait,wait_squared,wait_cubed)';assert marker in s
    s=s.replace(marker,marker[:-1]+',tuple(contexts))',1)
    marker="                    'fare_scenario':config['fare_scenario'],'fare_used_in_choice':config['fare_in_choice']}";assert marker in s
    s=s.replace(marker,"                    'fare_scenario':config['fare_scenario'],'fare_used_in_choice':config['fare_in_choice'],\n                    'empirical_evidence':evidence.report() if evidence else None}",1);p.write_text(s,encoding='utf8')
    p=work/'run_case.py';s=p.read_text(encoding='utf8');s=s.replace("'operations.py','run_case.py')","'operations.py','empirical_v12.py','run_case.py')",1);p.write_text(s,encoding='utf8')
    manifest=read(work/'input_manifest.json');manifest['frozen'].extend(extra)
    (work/'input_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    cases=[{'case':f'v12_empirical-combined-{scenario}-{did}','mode':'combined','day':day,'scenario':scenario,'seed':0,'operations':'v12_empirical'}
      for scenario in ('regular','peak') for day,did in (('월','mon'),('화','tue'),('수','wed'),('목','thu'),('금','fri'))]
    save(work/'experiment_lock.json',{'status':'PREREGISTERED_BEFORE_EXECUTION','version_family':'V12','release_id':stamp,
      'parent':str(PARENT),'pilot_cases':cases,'training_dates':['2026-11-10'],'retrospective_check_dates':['2026-11-11'],
      'pristine_holdout_dates':[],'requires_user_approval_before_production':True,
      'headway_supply_is_stop_anchored_not_depot_dispatch':True,'choice_discomfort_mapping_is_scenario':True})
    save(work/'evidence_inventory_initial.json',{'release_id':stamp,'version_family':'V12','items':inventory,
      'pending_historical_source_inventory':False,'missing_items':['shuttle continuous GPS/actual dispatch history','village ordinal crowd grades','numeric occupancy and boarding/alighting counts'],
      'operating_reference':'capacity_v11 model261110162302','code_parent':str(PARENT),
      'lineage':'V11 demand/supply contracts -> R10 behavior/physics ->261112104829 segment-only input ->V12 empirical supply/context candidate'})
    latest=ANALYSIS/'simulation_viewer_2026-11-07/public/routing-model/latest.json'
    save(work/'creation_manifest.json',{'release_id':stamp,'version_family':'V12','parent':str(PARENT),
      'parent_source_sha256':{n:sha(PARENT/n) for n in names},'production_latest_sha256':sha(latest),
      'candidate_builder_sha256':sha(Path(__file__)),'source_plan_sha256':sha(ROOT/'PLAN.md'),
      'new_evidence_payload_sha256':sha(work/'frozen/empirical_evidence.json'),'operations_sha256':sha(work/'frozen/operations_v12_empirical.json'),
      'operational_promotion_allowed':False})
    shutil.copy2(ROOT/'PLAN.md',work/'PLAN.md')
    save(pointer,{'directory':str(work),'release_id':stamp,'version_family':'V12','production_replacement_allowed':False})
    print('V12_PRIVATE_CANDIDATE_CREATED',work,'inventory',len(inventory),'anchor_rows',len(anchors),flush=True)

if __name__=='__main__':main()
