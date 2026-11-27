"""Recompute exported-table identities; keep model behavior and field evidence distinct."""
from pathlib import Path
import argparse,csv,hashlib,json,math
def read(p):return json.loads(p.read_bytes())
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def close(a,b):assert abs(float(a)-float(b))<1e-6,(a,b)
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve();out=w/'export-reconciliation.json';assert not out.exists()
    v=read(w/'grid-validation.json');bycase={r['case']['case']:r for r in v['results']};assert len(bycase)==10
    d=read(w/'grid-diagnostics.json');assert d['parent']=='261112220847'
    s=rows(w/'grid-all-stops.csv');assert len(s)==d['stop_rows']
    for x in s:
        r=bycase[x['case']];z=next(z for z in r['stop_waits'] if z['node']==int(x['node']))
        for k in ('episode_weight','max_wait_min','over20_weight'):close(x[k],z[k])
    j=rows(w/'grid-journey-comparison.csv');assert len(j)==40
    for x in j:
        r=bycase[x['case']];q=r['extended_diagnostics']['finished_trip_quantiles'][x['metric']]
        for k in q:close(x['repair_'+k],q[k])
    h=rows(w/'grid-half-hour-waits.csv');assert len(h)==d['half_hour_rows']
    assert all(int(x['queue_entry_half_hour'])%1800==0 and float(x['max_wait_min'])+1e-7>=float(x['mean_wait_min'])>=0 for x in h)
    alls=rows(w/'grid-all-recorded-stops.csv');allh=rows(w/'grid-all-recorded-half-hour-waits.csv')
    assert len(alls)==d['all_recorded_stop_rows']==len(s) and len(allh)==d['all_recorded_half_hour_rows']
    for cid,r in bycase.items():
        subset=[x for x in alls if x['case']==cid];z=r['extended_diagnostics']
        close(max(float(x['max_wait_min']) for x in subset),z['all_recorded_time_max_continuous_wait_min'])
        close(math.fsum(float(x['over20_episode_weight']) for x in subset),z['all_recorded_time_over20_episode_weight'])
    assert all(int(x['queue_entry_half_hour'])%1800==0 for x in allh)
    f=rows(w/'grid-field-comparison.csv');owned=[x for x in f if x['model']==w.name];assert len(owned)==8
    for x in owned:
        assert x['scenario'] in ('regular','peak') and x['case'] in bycase
        # Comparing means is not the same statistic as expected absolute error.
        assert float(x['expected_absolute_distance_to_count_or_interval'])>=0
    for name,n in [('mean-physical-components.csv',20),('class-end-journey-comparison.csv',40)]:assert len(rows(w/name))==n
    b=read(w/'grid-behavior-validation.json');assert b['status']=='PASS_STUDENT_BEHAVIOR_GATES' and len(b['cases'])==10
    counts={'display_overlapping_stops':len(s),'display_overlapping_half_hour_waits':len(h),'all_recorded_stops':len(alls),'all_recorded_half_hour_waits':len(allh),'journey':len(j),'reused_field_comparisons':len(f),'candidate_field_comparisons':len(owned),'mean_components':20,'class_end_journey':40}
    names=['grid-all-stops.csv','grid-half-hour-waits.csv','grid-all-recorded-stops.csv','grid-all-recorded-half-hour-waits.csv','grid-journey-comparison.csv','grid-field-comparison.csv','mean-physical-components.csv','class-end-journey-comparison.csv']
    out.write_text(json.dumps({'status':'PASS','release_id':w.name,'row_counts':counts,'artifact_sha256':{n:sha(w/n) for n in names},'new_field_accuracy':'NOT_EVALUATED','production_writes':False},ensure_ascii=False,indent=2),encoding='utf8')
    print('EXPORT_IDENTITIES_PASS',counts,flush=True)
if __name__=='__main__':main()
