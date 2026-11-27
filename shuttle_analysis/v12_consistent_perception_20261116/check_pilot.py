"""Predeclared acceptance against the same predecessor, preserving all variants."""
from pathlib import Path
import argparse,csv,json,math
def read(p):return json.loads(p.read_bytes())
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve();out=w/'pilot-decision.json';assert not out.exists()
    v=read(w/'pilot-validation.json');b=read(w/'pilot-behavior-validation.json');base=read(w.parent/'261116105704/grid-validation.json')['results']
    main=[r for r in v['results'] if not r['case']['case'].startswith('ablation')];assert len(main)==2
    fields=list(csv.DictReader((w/'pilot-field-comparison.csv').open(encoding='utf-8-sig')))
    names={r['case']['case'] for r in main};owned=[r for r in fields if r['model']==w.name and r['case'] in names];assert len(owned)==4
    key='expected_absolute_distance_to_count_or_interval';comparisons=[]
    for r in owned:
        old=next(x for x in fields if x['model']=='261116105704' and x['scenario']==r['scenario'] and x['observation_id']==r['observation_id'])
        comparisons.append({'observation':r['observation_id'],'minute':r['reported_minute'],'old_mean':float(old['uniform_minute_mean']),'new_mean':float(r['uniform_minute_mean']),'old_error':float(old[key]),'new_error':float(r[key])})
    before=after=unserved=0.;means=[];old_max=[];new_max=[]
    for r in main:
        old=next(x for x in base if (x['case']['day'],x['case']['scenario'])==(r['case']['day'],r['case']['scenario']))
        before+=old['extended_diagnostics']['all_recorded_time_over20_episode_weight'];after+=r['extended_diagnostics']['all_recorded_time_over20_episode_weight']
        unserved+=r['unserved_trip_weight'];means.append(r['extended_diagnostics']['finished_trip_quantiles']['total_min']['mean']-old['extended_diagnostics']['finished_trip_quantiles']['total_min']['mean'])
        old_max.append(old['extended_diagnostics']['all_recorded_time_max_continuous_wait_min']);new_max.append(r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min'])
    e0=math.fsum(x['old_error'] for x in comparisons);e1=math.fsum(x['new_error'] for x in comparisons)
    physical=all(r['status']=='PASS_INTERNAL_INVARIANTS' for r in v['results']);behavior=b['status']=='PASS_STUDENT_BEHAVIOR_GATES'
    passed=physical and behavior and unserved<1e-7 and after<=before+1e-7 and e1<=e0+1e-7 and max(new_max)<=max(old_max)+1e-7 and (after<before-1e-7 or e1<e0-1e-7)
    result={'status':'PILOT_QUALIFIED' if passed else 'PILOT_NOT_ACCEPTED','comparison_parent':'261116105704','physical':physical,'behavior':behavior,
            'main_cases':2,'diagnostic_cases':len(v['results'])-2,'over20_before':before,'over20_after':after,'field_error_sum_before':e0,'field_error_sum_after':e1,
            'observations':comparisons,'mean_journey_delta_minutes':means,'max_wait_before':max(old_max),'max_wait_after':max(new_max),'unserved_weight':unserved,'new_date_accuracy':'NOT_EVALUATED','production_writes':False}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(result,ensure_ascii=False),flush=True)
    return passed
if __name__=='__main__':raise SystemExit(0 if main() else 2)
