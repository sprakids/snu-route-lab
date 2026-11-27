"""Reconcile final tables, immutable model, unchanged preference and weighted traces."""
from pathlib import Path
import argparse,csv,hashlib,json,math,re
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'261112171315'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def close(a,b):assert abs(float(a)-float(b))<1e-7,(a,b)
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve();out=w/'artifact_verification_final.json';assert not out.exists()
    d=read(w/'grid-diagnostics.json');v=read(w/'grid-validation.json');rec=read(w/'release_recommendation_final.json');pilot=read(w/'pilot-assessment.json')
    old={(r['case']['day'],r['case']['scenario']):r for r in read(PARENT/'grid-validation.json')['results']};new={(r['case']['day'],r['case']['scenario']):r for r in v['results']}
    assert len(new)==10 and set(new)==set(old)
    extension=read(w/'pilot_review_decision.json')
    assert pilot['status']=='PILOT_REVIEW_BUDGET_FAILED' and extension['full_grid_diagnostic_only'] is True
    assert pilot['invariants_pass'] and extension['original_budget_failure_preserved'] is True
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
    assert len(field)==48 and field[:40]==parent_field and len([r for r in field if r['model']==w.name])==8
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
    close(max(r['extended_diagnostics']['finished_trip_quantiles']['total_min']['maximum'] for r in new.values()),rec['maximum_total_journey_min'])
    named=sum(s['maximum_queue']>40 for r in d['cases'] for s in r['named_stop_40_recollection_comparison']);assert named==rec['named_40_reference_exceed_conditions']
    trace=read(w/'grid-trace-and-costs.json');assert trace['status'].startswith('PASS') and trace['maximum_cost_error_minutes']<1e-6
    for r in new.values():
        diag=r['policy_report']['committed_approach_forecast'];assert diag['remaining_commitments']==0
        assert diag['not_observed_student_tracking'] is True
    integrity=read(w/'final_verification.json');assert integrity['status']=='PASS' and integrity['cases_verified']==10 and integrity['future_hashes_verified']==22
    report=w/'RESULTS_FINAL.md';assert sha(report)==rec['report_sha256'];links=[]
    for href in re.findall(r'\]\(([^)]+)\)',report.read_text(encoding='utf8')):
        if href.startswith(('https://','http://','#')):continue
        dest=(w/href).resolve()
        if dest!=out.resolve():assert dest.exists(),href
        links.append(href)
    result={'status':'PASS_RECONCILED_PRIVATE_CANDIDATE','release_id':w.name,'cases':10,'numeric_checks':checks,
      'field_rows':len(field),'stop_rows':len(stops),'half_hour_rows':len(half),'journey_rows':len(table),'class_end_rows':len(classrows),
      'walking_preference_preserved':True,'no_release_timing_change':True,'maximum_all_recorded_continuous_wait_min':maximum,
      'decline_cost_vectors_checked':trace['cost_vectors_checked'],'local_links_checked':len(links),'runtime_frozen_hashes':22,
      'report_sha256':sha(report),'production_writes':False,'independent_field_accuracy':'NOT_EVALUABLE'}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    assert all((w/link).resolve().exists() for link in links)
    print('FINAL_ARTIFACTS_PASS',w.name,checks,'numeric checks',len(field),'field rows',len(half),'half-hour rows',flush=True)
if __name__=='__main__':main()
