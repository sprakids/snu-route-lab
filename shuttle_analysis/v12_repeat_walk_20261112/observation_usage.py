"""Audit inherited observation roles without refitting or opening new-date labels."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent/'261112111627';PARENT=ROOT.parent/'261112210916'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve();out=w/'observation_usage_ledger.json';assert not out.exists()
    inventory=read(BASE/'evidence_inventory_final.json');checks=[]
    for r in inventory['items']:
        if not r.get('snapshot'):continue
        path=BASE/r['snapshot'];assert path.exists(),path;digest=sha(path)
        if r.get('sha256'):assert digest==r['sha256'],path
        checks.append({'id':r['id'],'snapshot':str(path),'sha256':digest,'inherited_role':r['role']})
    frozen={}
    for name in ('empirical_evidence.json','operations_observed_train_v1.json','operations_v12_empirical.json','peer_calibration_contract.json','peer_calibration_candidates.json','historical_evidence_context.json','new_observation_at_amendment.json'):
        path=w/'frozen'/name;frozen[name]={'path':str(path),'sha256':sha(path)}
        assert sha(path)==sha(PARENT/'frozen'/name),name
    e=read(w/'frozen/empirical_evidence.json');o=read(w/'frozen/operations_v12_empirical.json');t=read(w/'frozen/new_observation_at_amendment.json');plan=read(w/'future_evaluation_plan.json')
    assert e['training_dates']==o['headway_training_dates']==o['segment_training_dates']==['2026-11-10']
    assert len(e['route_sequences'])==8 and set(e['missing_crowd_routes'])=={'120900011','120900012'}
    assert o['dwell_added_separately'] is False and o['grade_people_conversion'] is False and o['physical_external_occupancy_identified'] is False
    assert t['reported_time_event']=='joined_the_queue' and t['people']['preferred_reported_outside_queue_count_including_observer']==67
    assert t['durations']['reported_pure_queue_wait_seconds']==189 and t['durations']['reported_seconds_from_end_of_queue_wait_to_departure']==30
    assert t['vehicle']['preferred_user_reported_max_passengers']==44 and t['vehicle']['observed_vehicle_arrival_time'] is None
    assert plan['new_outcome_raw_opened'] is False and plan['production_replacement_allowed'] is False
    roles=[
      {'id':'city-headways','use':'inherited_runtime_input','dates':['2026-11-10'],'consumer':'frozen operations_v12_empirical.json route departures; operations.journeys; empirical_v12.Evidence.headways',
       'source':'stable detector observed_intervals and empirical headway samples','limit':'Direction/stop sequence/hour retained; sample gaps15..3600s; inferred reference-stop crossings, not official dispatch or personal waits; reused overlapping passages are dependent.'},
      {'id':'city-segment-times','use':'inherited_runtime_input','dates':['2026-11-10'],'consumer':'frozen operations_v12_empirical.json segment_profiles; time_profiles.values_at',
       'source':'adjacent_segment_samples_stable_dates + reconciled operations bridge','limit':'Elapsed detected passages include signal/dwell/detection uncertainty; no second blanket dwell. FIFO interpolation and physical caps retained. Cannot identify pure moving speed independently.'},
      {'id':'city-categorical-grades-and-transitions','use':'inherited_runtime_choice_risk','dates':['2026-11-10'],'consumer':'empirical_v12.Evidence.context; preferences crowd exposure',
       'source':'deduplicated_grade_passages; grade transitions reconstructed in empirical_evidence','limit':'API0 is missing. Known API3..6 mapped to ordinal0..3; does not mean0..3 people. Same-vehicle transitions retain route/sequence/hour; risk coefficients remain a scenario.'},
      {'id':'city-full-flags','use':'inherited_runtime_context','dates':['2026-11-10'],'consumer':'empirical_v12.Evidence.context full_flag_probability',
       'source':'full_flags_by_day_route_section_slot.csv','limit':'Known flags only, not available seats. Does not physically inject a measured external passenger count.'},
      {'id':'old-nov09-bus-detector','use':'provenance_and_legacy_context_only','dates':['2026-11-09'],'consumer':'inherited evidence snapshots and limitations',
       'source':'download_manifest/calibration_contract/raw archive','limit':'Midday detector logic changed; not current V12 headway/segment training. Operations JSON retains older source/retained_headway metadata in addition to explicit current training_dates; route departures use V12 Nov10 anchoring, not a newly observed Nov09 shuttle timetable.'},
      {'id':'nov11-date-split','use':'already_explored_retrospective_diagnostic','dates':['2026-11-11'],'consumer':'ancestor evidence validation and bridge reconciliation',
       'source':'calibration_candidates, stable samples, heldout_diagnostic_dates','limit':'Not used for current training; already inspected, cannot be called pristine validation. Aggregate multi-date candidate summaries are not silently fitted.'},
      {'id':'three-monday-queue-snapshots','use':'reused_comparison_and_historical_selection','dates':['2026-11-09'],'consumer':'grid-field-comparison.csv and inherited queue calibration lineage',
       'source':'field_observations_2026-11-09 and observation_timing_correction; ancestor frozen snapshots','values':'16:53 administration53;16:55 culture5;17:03 gate33..39, ARS21128',
       'limit':'Date inferred; culture direction uncertain; minute-uniform seconds are a comparison assumption, no best second. No new fitting of growth2.'},
      {'id':'tuesday-queue-and-capacity','use':'inherited_supply_amendment_and_reused_comparison','dates':['2026-11-10'],'consumer':'capacity.py batch_size_at_clock; prepared_capacity44_pair; grid-field-comparison.csv',
       'source':'frozen/new_observation_at_amendment.json','values':'15:23 queue join,67 outside including observer,66 ahead,44 per shuttle,second of two same-destination buses',
       'limit':'Earlier83/69 counts,46 capacity and15:23 bus arrival superseded. Arrival after15:24 is approximate, exact unknown.2x44 pair scenario daytime15..19 retained, not evidence every batch is exactly3min. Two photos are one episode.'},
      {'id':'tuesday-individual-wait','use':'diagnostic_constraint_global_comparison_not_identifiable','dates':['2026-11-10'],'consumer':'ancestor individual_wait ledger + dwell.py micro model, not network global dwell fit',
       'source':'same final amended observation','values':{'pure_queue_wait_seconds':189,'boarding_to_departure_seconds':30,'joined_to_departure_seconds':219,'individual_samples':1},
       'limit':'Network has coalesced arrival/boarding/departure, no observed exact arrival or matching unique synthetic passenger. Cannot report a measured personal-wait before/after error or fit global boarding service from this single episode.'},
      {'id':'shuttle-traffic-time-and-dispatch','use':'partially_available_official_and_scenario','dates':[],'consumer':'existing supply/offsets; capacity pair amendment',
       'source':'official plan and prior scenario + direct Tuesday report','limit':'BUSIN overwritten cache/schematic coordinates are not continuous GPS. No observed shuttle traffic-dependent speed/dispatch distribution to fit; city segments cannot be relabeled shuttle observations.'},
      {'id':'external-numeric-occupancy-and-village-grades','use':'unavailable_not_fitted','dates':[],'consumer':'existing background occupancy scenarios and missing-grade fallback',
       'source':'calibration_contract; empirical missing_crowd_routes','limit':'No observed numeric external load, seat-count mapping or village grades. Ordinal grades inform risk only; unknown grade is not free capacity.'},
      {'id':'saved-individual-trips','use':'unavailable_not_fitted','dates':[],'consumer':None,'source':'collected_data_review_2026-11-12/saved_trip_observations.json','limit':'Saved records list is empty; no empirical individual route/travel-time sample.'},
      {'id':'historical-and-class-demand','use':'inherited_weighted_demand_or_context','dates':[],'consumer':'prepared_capacity44_pair and historical_evidence_context',
       'source':'inherited53-item inventory incl course enrollment, destinations/dorm,library,Seoul boarding context','limit':'Not actual unique-student destinations; library delay/dorm/destination shares remain declared scenarios; aggregate boarding events are not unique students or offered stop arrivals.'},
      {'id':'new-date-validation','use':'reserved_unopened','dates':[],'consumer':'future_evaluation_plan.json','source':'first qualifying completed day after11/11','limit':'Earliest11/13 00:00KST for11/12; first check date/schema/coverage before outcomes; no new raw outcomes opened or automated job created.'}]
    saved=ROOT.parent/'collected_data_review_2026-11-12/saved_trip_observations.json';assert read(saved)['records']==[]
    provenance={str(BASE/'evidence_inventory_final.json'):sha(BASE/'evidence_inventory_final.json'),str(saved):sha(saved)}
    for name in ('recording_index.json','download_manifest.json'):
        path=ROOT.parent/'collected_data_review_2026-11-12'/name
        if path.exists():provenance[str(path)]=sha(path)
    result={'status':'PASS_INHERITED_ROLES_AND_FINAL_CORRECTIONS_AUDITED','release_id':w.name,'checked_at':datetime.now(timezone.utc).isoformat(),
      'ancestor_inventory_item_count':len(inventory['items']),'snapshot_integrity_checks':checks,'frozen_inputs':frozen,'additional_provenance_hashes':provenance,
      'usage_roles':roles,'training_dates':['2026-11-10'],'already_explored_diagnostic_dates':['2026-11-11'],'growth2_not_fitted':True,
      'new_outcomes_opened':False,'runtime_modified':False,'production_writes':False,'unavailable_quantities_not_fabricated':True}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    lines=[f'# 실측 자료 사용 장부 — {w.name}','','원본 사용을 추적하는 읽기 전용 대조입니다. 새 수치 보정이나 동결 입력 수정은 하지 않았습니다. 식별 가능한 기존 관측 입력은 계승하고, 자료가 없는 항목은 미확보로 남겼습니다.','',
      f'기존 목록53항목, 보존 스냅샷{len(checks)}개, 현재 동결 실측 관련 입력7개를 대조했습니다. [해시·소비 위치·제약 원장](observation_usage_ledger.json).','',
      '|자료|사용|반영 위치 / 한계|','|---|---|---|']
    for r in roles:lines.append(f"|{r['id']}|{r['use']}|{r.get('consumer') or '없음'}; {r['limit']}|")
    lines+=['','화요일 최종값은15:23 줄 합류,밖의 줄 본인 포함67명,정원44명,동행 두 대 중 두 번째 승차,순수대기189초+탑승 후30초입니다. 정확한 버스 도착시각은 없습니다. 개인 대기1건을 전체 정차시간 분포나 모든67명의 대기시간으로 복제하지 않았습니다.','',
      '새 규칙 전후 대기열과 가중 여정/차내시간은 모의 비교로 산출합니다. 실제 개인의189초 대기에 대한 전후 오차는 도착·승차·출발을 분리하지 못하는 현재 전역 모델에서 식별 불가이므로 숫자를 만들지 않았습니다. 이번 장부의 미확보 항목을 모두 보정했다고 표현하지 않습니다.','']
    (w/'OBSERVATION_USAGE.md').write_text('\n'.join(lines),encoding='utf8');print('OBSERVATION_USAGE_PASS',len(inventory['items']),len(checks),'snapshots',len(roles),'roles',flush=True)
if __name__=='__main__':main()
