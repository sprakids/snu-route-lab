"""Reconcile probabilities, immutable runs, journey tables and private release report."""
from pathlib import Path
import argparse,csv,hashlib,json,math,re
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'261112210916'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def close(a,b):assert abs(float(a)-float(b))<1e-7,(a,b)
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve();out=w/'artifact_verification_final.json';assert not out.exists()
    d=read(w/'grid-diagnostics.json');v=read(w/'grid-validation.json');rec=read(w/'release_recommendation_final.json');pilot=read(w/'pilot-assessment.json')
    old={(r['case']['day'],r['case']['scenario']):r for r in read(PARENT/'grid-validation.json')['results']};new={(r['case']['day'],r['case']['scenario']):r for r in v['results']}
    assert len(new)==10 and set(new)==set(old) and pilot['status']=='VIABLE_FOR_FULL_GRID'
    assert all(r['status']=='PASS_INTERNAL_INVARIANTS' and r['case']['seed']==0 for r in new.values())
    assert d['source_group_sha256']==sha(w/'grid-validation.json')
    maximum=max(r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min'] for r in new.values())
    close(maximum,rec['maximum_all_recorded_continuous_wait_min'])
    assert all(r['extended_diagnostics']['all_recorded_time_over20_episode_weight']==0 and r['unserved_trip_weight']==0 for r in new.values())
    table=rows(w/'grid-journey-comparison.csv');assert len(table)==40;checks=0
    for row in table:
        key=(row['day'],row['scenario']);metric=row['metric']
        for stat in ('mean','p50','p90','p95','p99','maximum'):
            close(row['parent_'+stat],old[key]['extended_diagnostics']['finished_trip_quantiles'][metric][stat])
            close(row['repair_'+stat],new[key]['extended_diagnostics']['finished_trip_quantiles'][metric][stat]);checks+=2
    field=rows(w/'grid-field-comparison.csv');parent_field=rows(PARENT/'grid-field-comparison.csv')
    assert len(field)==len(parent_field)+8==56 and field[:len(parent_field)]==parent_field
    assert len([r for r in field if r['model']==w.name])==8
    stops=rows(w/'grid-all-stops.csv');half=rows(w/'grid-half-hour-waits.csv')
    assert len(stops)==d['stop_rows']==990 and len(half)==d['half_hour_rows']
    for r in half:
        assert int(r['queue_entry_half_hour'])%1800==0
        assert float(r['mean_wait_min'])<=float(r['max_wait_min'])+1e-7<=maximum+2e-7
    classrows=rows(w/'class-end-journey-comparison.csv');assert len(classrows)==40
    for key in new:
        values={}
        for model in (PARENT.name,w.name):
            for metric in ('class_end_to_departure_min','class_end_to_destination_min'):
                values[model,metric]=next(r for r in classrows if r['model']==model and (r['weekday'],r['scenario'])==key and r['metric']==metric)
            depart=(old if model==PARENT.name else new)[key]['extended_diagnostics']['finished_trip_quantiles']['total_min']['mean']
            close(float(values[model,'class_end_to_departure_min']['mean'])+depart,values[model,'class_end_to_destination_min']['mean'])
        close(values[PARENT.name,'class_end_to_departure_min']['mean'],values[w.name,'class_end_to_departure_min']['mean']);checks+=3
    components=rows(w/'mean-physical-components.csv');assert len(components)==20
    for row in components:
        source=(old if row['model']==PARENT.name else new)[row['weekday'],row['scenario']]
        close(row['total_min'],source['extended_diagnostics']['finished_trip_quantiles']['total_min']['mean'])
        close(row['total_min'],math.fsum(float(row[k]) for k in ('walk_min','wait_min','ride_min')));checks+=2
    usage=read(w/'observation_usage_ledger.json');assert usage['status']=='PASS_INHERITED_ROLES_AND_FINAL_CORRECTIONS_AUDITED'
    assert usage['ancestor_inventory_item_count']==53 and len(usage['snapshot_integrity_checks'])==39
    assert usage['runtime_modified'] is False and usage['new_outcomes_opened'] is False
    for source in usage['snapshot_integrity_checks']+list(usage['frozen_inputs'].values()):assert sha(Path(source.get('snapshot',source.get('path'))))==source['sha256']
    close(max(r['extended_diagnostics']['finished_trip_quantiles']['total_min']['maximum'] for r in new.values()),rec['maximum_total_journey_min'])
    named=sum(s['maximum_queue']>40 for r in d['cases'] for s in r['named_stop_40_recollection_comparison']);assert named==rec['named_40_reference_exceed_conditions']
    trace=read(w/'grid-trace-and-costs.json');assert trace['status'].startswith('PASS') and trace['maximum_cost_error_minutes']<1e-6
    assert len(trace['traces'])==2;close(trace['traces'][0]['mass'],trace['traces'][1]['mass'])
    for r in new.values():
        diag=r['policy_report']['committed_approach_forecast'];assert diag['remaining_commitments']==0 and diag['not_observed_student_tracking'] is True
    prob=read(w/'grid-probability-validation.json');assert prob['status']=='PASS_CONTROLLED_LAW_AND_RECORDED_TARGETS'
    assert prob['recorded_probability_checks']==rec['recorded_probability_checks'] and prob['maximum_probability_formula_error']<1e-7
    law=rows(w/'probability-law.csv');assert len(law)==45
    cfg=read(w/'config.json');assert cfg['repeat_walk_growth_factor']==2. and cfg['maximum_route_changes'] is None and not cfg['persistent_strategy_utility']
    for r in law:
        base=float(r['fixed_reference_probability']);n=int(r['completed_changes']);expected=min(1-cfg['repeat_walk_numeric_epsilon'],1-(1-base)**(2**n))
        close(r['target_probability'],expected);checks+=1
    opportunities=rows(w/'grid-walking-by-change-count.csv');assert len(opportunities)==prob['actual_opportunity_rows']
    for r in opportunities:
        raw=float(r['mean_unboosted_probability']);target=float(r['mean_target_probability']);actual=float(r['realized_terminal_walk_fraction'])
        assert 0<=raw<=target+1e-10<=1+2e-10 and 0<=actual<=1+1e-10
        if int(r['completed_changes'])==0:close(raw,target)
    tests=(w/'boundary-tests.log').read_text(encoding='utf8');assert 'Ran 89 tests' in tests and tests.rstrip().endswith('OK')
    integrity=read(w/'final_verification.json');assert integrity['status']=='PASS' and integrity['cases_verified']==10 and integrity['future_hashes_verified']==22
    review_path=ROOT.parent/'collaboration'/f'v12_repeat_walk_review_{w.name}'/'evidence.json';review=read(review_path)
    assert review['review_outcome']=='STATIC_CHECKS_MATCH' and not review['failures']
    assert sha(ROOT.parent.parent/review['report']['path'])==review['report']['sha256']
    assert len(review['started_receipts_as_observed'])==7 and review['scope']['performance_or_adoption_approved'] is False
    assert rec['production_writes'] is False and rec['recommendation']=='KEEP_PRIVATE_DO_NOT_PROMOTE'
    report=w/'RESULTS_FINAL.md';assert sha(report)==rec['report_sha256'];links=[]
    for href in re.findall(r'\]\(([^)]+)\)',report.read_text(encoding='utf8')):
        if href.startswith(('https://','http://','#')):continue
        dest=(w/href).resolve()
        if dest!=out.resolve():assert dest.exists(),href
        links.append(href)
    result={'status':'PASS_RECONCILED_PRIVATE_CANDIDATE','release_id':w.name,'cases':10,'numeric_checks':checks,
      'field_rows':len(field),'stop_rows':len(stops),'half_hour_rows':len(half),'journey_rows':len(table),'class_end_rows':len(classrows),'physical_component_rows':len(components),
      'probability_law_rows':len(law),'probability_opportunity_rows':len(opportunities),'recorded_probability_checks':prob['recorded_probability_checks'],
      'no_release_timing_change':True,'maximum_all_recorded_continuous_wait_min':maximum,'unit_tests_passed':89,
      'decline_cost_vectors_checked':trace['cost_vectors_checked'],'local_links_checked':len(links),'runtime_frozen_hashes':22,
      'report_sha256':sha(report),'peer_static_evidence_sha256':sha(review_path),'production_writes':False,'independent_field_accuracy':'NOT_EVALUABLE'}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');assert all((w/link).resolve().exists() for link in links)
    print('FINAL_ARTIFACTS_PASS',w.name,checks,'numeric checks',len(field),'field rows',len(half),'half-hour rows',flush=True)
if __name__=='__main__':main()
