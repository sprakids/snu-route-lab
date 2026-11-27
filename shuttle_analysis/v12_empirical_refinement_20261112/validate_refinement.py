"""Reconcile delivered metrics, exact references, frozen receipts and local links."""
from pathlib import Path
import argparse,csv,hashlib,json,math,re
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent;PARENT='261112132736'
def read(p):return json.loads(p.read_bytes())
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def close(a,b):assert abs(float(a)-float(b))<1e-7,(a,b)
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');args=p.parse_args();work=Path(args.candidate).resolve()
    target=work/'artifact_verification_final.json';assert not target.exists()
    d=read(work/'grid-diagnostics.json');v=read(work/'grid-validation.json');decision=read(work/'release_recommendation_final.json')
    base=read(ANALYSIS/PARENT/'grid-validation.json');old={(r['case']['day'],r['case']['scenario']):r for r in base['results']}
    new={(r['case']['day'],r['case']['scenario']):r for r in v['results']};assert len(new)==10 and set(new)==set(old)
    assert all(r['case']['seed']==0 and r['case']['operations']=='v12_empirical' for r in v['results'])
    assert all(r['status']=='PASS_INTERNAL_INVARIANTS' for r in v['results'])
    assert sha(work/'grid-validation.json')==d['source_group_sha256']
    maximum=max(r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min'] for r in v['results'])
    over=math.fsum(r['extended_diagnostics']['all_recorded_time_over20_episode_weight'] for r in v['results'])
    close(maximum,decision['maximum_all_recorded_continuous_wait_min']);close(over,decision['over20_episode_weight'])
    assert d['all_continuous_waits_under20']==(over<1e-7)
    unserved=math.fsum(r['unserved_trip_weight'] for r in v['results']);close(unserved,decision['unserved_trip_weight'])
    trips=rows(work/'grid-journey-comparison.csv');assert len(trips)==40
    checks=0
    for r in trips:
        c=(r['day'],r['scenario']);metric=r['metric'];a=old[c]['extended_diagnostics']['finished_trip_quantiles'][metric];b=new[c]['extended_diagnostics']['finished_trip_quantiles'][metric]
        for stat in ('mean','p50','p90','p95','p99','maximum'):
            close(r['parent_'+stat],a[stat]);close(r['repair_'+stat],b[stat]);checks+=2
    field=rows(work/'grid-field-comparison.csv');parent_field=rows(ANALYSIS/PARENT/'grid-field-comparison.csv')
    assert len(field)==40 and field[:32]==parent_field
    own=[r for r in field if r['model']==work.name];assert len(own)==8
    regular=[r for r in own if r['scenario']=='regular'];assert len(regular)==4
    improved=0
    for r in regular:
        b=next(x for x in parent_field if x['model']==PARENT and x['scenario']=='regular' and x['observation_id']==r['observation_id'])
        if float(r['expected_absolute_distance_to_count_or_interval'])<float(b['expected_absolute_distance_to_count_or_interval']):improved+=1
    assert improved==decision['old_queue_reports_improved_vs_immediate_parent']
    stops=rows(work/'grid-all-stops.csv');half=rows(work/'grid-half-hour-waits.csv')
    assert len(stops)==d['stop_rows']==990 and len(half)==d['half_hour_rows']
    assert len({(r['case'],r['node']) for r in stops})==990
    for r in half:
        assert int(r['queue_entry_half_hour'])%1800==0
        assert float(r['max_wait_min'])+1e-7>=float(r['mean_wait_min'])>=0
        assert float(r['max_wait_min'])<=maximum+1e-7
        assert float(r['over20_episode_weight'])<=float(r['episode_weight'])+1e-7
    classrows=rows(work/'class-end-journey-comparison.csv');assert len(classrows)==40
    assert read(work/'class-end-metrics-manifest.json')['lineage_sha256']==sha(work/'frozen/class_release_map.json.gz')
    for model in (PARENT,work.name):
        for c in new:
            lag=next(r for r in classrows if r['model']==model and (r['weekday'],r['scenario'])==c and r['metric']=='class_end_to_departure_min')
            total=next(r for r in classrows if r['model']==model and (r['weekday'],r['scenario'])==c and r['metric']=='class_end_to_destination_min')
            src=(old if model==PARENT else new)[c]['extended_diagnostics']['finished_trip_quantiles']['total_min']
            assert float(total['unserved_trip_weight'])==0
            close(float(lag['mean'])+src['mean'],total['mean']);checks+=1
    n40=sum(s['maximum_queue']>40 for r in d['cases'] for s in r['named_stop_40_recollection_comparison'])
    assert n40==decision['named_40_reference_exceed_conditions']
    assert len([s for r in d['cases'] for s in r['named_stop_40_recollection_comparison']])==40
    regress=[];walk=[];improvements={k:0 for k in ('mean','p99','maximum')}
    for c,r in new.items():
        a=r['extended_diagnostics']['finished_trip_quantiles'];b=old[c]['extended_diagnostics']['finished_trip_quantiles']
        for k in improvements:improvements[k]+=a['total_min'][k]<b['total_min'][k]
        if a['total_min']['mean']>b['total_min']['mean']:regress.append((c[0],c[1]))
        walk.append(a['walk_min']['mean']-b['walk_min']['mean'])
    assert set(regress)=={(x['day'],x['scenario']) for x in decision['mean_total_regressions']}
    assert improvements['mean']==decision['mean_total_improved_conditions']
    assert improvements['p99']==decision['p99_total_improved_conditions']
    assert improvements['maximum']==decision['max_total_improved_conditions']
    close(min(walk),decision['mean_walk_change_range_min'][0]);close(max(walk),decision['mean_walk_change_range_min'][1])
    report=work/'RESULTS_FINAL.md';assert sha(report)==decision['report_sha256']
    links=[]
    for href in re.findall(r'\]\(([^)]+)\)',report.read_text(encoding='utf8')):
        if href.startswith(('https://','http://','#')):continue
        dest=(work/href.split('#')[0]).resolve()
        if dest!=target.resolve():assert dest.exists(),href
        links.append(href)
    final=read(work/'final_verification.json');assert final['status']=='PASS' and len(final['public_readback'])==8
    assert final['production_model_id']=='261110162302' and final['production_writes'] is False
    assert decision['recommendation']=='KEEP_PRIVATE_DO_NOT_PROMOTE' and decision['new_day_outcomes_opened'] is False
    tests=re.search(r'Ran (\d+) tests', (work/'boundary-tests.log').read_text(encoding='utf8'));assert tests
    out={'status':'PASS_REPORT_TABLES_REFERENCES_AND_LIMITATIONS','release_id':work.name,
      'cases':10,'exact_numeric_checks':checks,'field_rows':len(field),'new_field_rows':len(own),
      'stop_rows':len(stops),'half_hour_rows':len(half),'journey_rows':len(trips),'class_end_rows':len(classrows),
      'tests_passed':int(tests.group(1)),'local_links_checked':len(links),'regressions_explicit':regress,
      'report_sha256':sha(report),'recommendation_sha256':sha(work/'release_recommendation_final.json'),
      'integrity_verification_sha256':sha(work/'final_verification.json'),'production_writes':False,
      'not_independent_field_accuracy_validation':True}
    target.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
    assert all((work/href.split('#')[0]).resolve().exists() for href in links)
    print('ARTIFACTS_VERIFIED',work.name,'field',len(field),'stops',len(stops),'half',len(half),'links',len(links),flush=True)
if __name__=='__main__':main()
