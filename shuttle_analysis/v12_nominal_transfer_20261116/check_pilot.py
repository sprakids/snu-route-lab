"""Apply the frozen mechanism gate against the completed parent-F pilot."""
from pathlib import Path
import csv,json,math,sys
def read(p):return json.loads(p.read_bytes())
def csvrows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def main():
    w=Path(sys.argv[1]).resolve();parent=w.parent/'261116153200';out=w/'pilot-decision.json';assert not out.exists()
    v=read(w/'pilot-validation.json');behavior=read(w/'pilot-behavior-validation.json')
    new=[r for r in v['results'] if not r['case']['case'].startswith('ablation')];assert len(new)==2
    old=[r for r in read(parent/'pilot-validation.json')['results'] if not r['case']['case'].startswith('ablation')]
    pairs=[(next(a for a in old if a['case']['day']==b['case']['day']),b) for b in new]
    over=lambda r:r['extended_diagnostics']['all_recorded_time_over20_episode_weight']
    maximum=lambda r:r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min']
    mean=lambda r:r['extended_diagnostics']['finished_trip_quantiles']['total_min']['mean']
    fields=[r for r in csvrows(w/'pilot-field-comparison.csv') if r['model']==w.name and not r['case'].startswith('ablation')]
    prior=[r for r in csvrows(parent/'pilot-field-comparison.csv') if r['model']==parent.name and not r['case'].startswith('ablation')]
    assert len(fields)==len(prior)==4
    key='expected_absolute_distance_to_count_or_interval';comparisons=[]
    for b in fields:
        a=next(x for x in prior if x['observation_id']==b['observation_id'] and x['scenario']==b['scenario'])
        comparisons.append({'observation':b['observation_id'],'minute':b['reported_minute'],
            'old_mean':float(a['uniform_minute_mean']),'new_mean':float(b['uniform_minute_mean']),
            'old_error':float(a[key]),'new_error':float(b[key])})
    e0=math.fsum(x['old_error'] for x in comparisons);e1=math.fsum(x['new_error'] for x in comparisons)
    gate=next(x for x in comparisons if x['minute']=='17:03')
    o0=math.fsum(over(a) for a,b in pairs);o1=math.fsum(over(b) for a,b in pairs)
    m0=max(maximum(a) for a,b in pairs);m1=max(maximum(b) for a,b in pairs)
    means=[mean(b)-mean(a) for a,b in pairs];unserved=math.fsum(r['unserved_trip_weight'] for r in new)
    oldlaw=read(w/'parent-law-reference.json')['cases']
    newlaw=[r for r in read(w/'pilot-law-transfer-metrics.json')['cases'] if not r['case']['case'].startswith('ablation')]
    law0=max(z['maximum_queue'] for r in oldlaw for z in r['law_profiles']);law1=max(z['maximum_queue'] for r in newlaw for z in r['law_profiles'])
    t0=math.fsum(r['snu_law_arrival_after_prior_bus_weight'] for r in oldlaw)
    t1=math.fsum(r['snu_law_arrival_after_prior_bus_weight'] for r in newlaw)
    restored=all(r['catalog_repair_report'] and r['catalog_repair_report']['restored_count']==5 for r in newlaw)
    diag=next(r for r in v['results'] if r['case']['case'].startswith('ablation'))
    par=next(r for r in old if r['case']['day']=='화')
    numbers=lambda r:[over(r),maximum(r),*r['extended_diagnostics']['finished_trip_quantiles']['total_min'].values()]
    differences=[abs(a-b) for a,b in zip(numbers(diag),numbers(par))];reproduced=max(differences)<1e-6
    physical=all(r['status']=='PASS_INTERNAL_INVARIANTS' for r in v['results']);bgate=behavior['status']=='PASS_STUDENT_BEHAVIOR_GATES'
    checks={'physical':physical,'behavior':bgate,'no_unserved':unserved<1e-7,'disabled_parent_reproduced':reproduced,
        'known_direct_five_preserved':restored,'over20_nonworse':o1<=o0+1e-7,'max_wait_nonworse':m1<=m0+1e-7,
        'each_mean_journey_nonworse':all(x<=1e-7 for x in means),'field_sum_nonworse':e1<=e0+1e-7,
        'gate_error_nonworse':gate['new_error']<=gate['old_error']+1e-7,'afternoon_law_max_nonworse':law1<=law0+1e-7,
        'afternoon_snu_transfer_arrivals_decreased':t1<t0-1e-7,'over20_strict_improvement':o1<o0-1e-7}
    passed=all(checks.values())
    result={'status':'PILOT_QUALIFIED' if passed else 'PILOT_NOT_ACCEPTED','comparison_parent':parent.name,
        'broader_reference':'261116010854','main_cases':2,'diagnostic_cases':1,'checks':checks,'physical':physical,'behavior':bgate,
        'over20_before':o0,'over20_after':o1,'field_error_sum_before':e0,'field_error_sum_after':e1,'observations':comparisons,
        'mean_journey_delta_minutes':means,'max_wait_before':m0,'max_wait_after':m1,'unserved_weight':unserved,
        'afternoon_law_max_before':law0,'afternoon_law_max_after':law1,
        'afternoon_snu_transfer_arrivals_before':t0,'afternoon_snu_transfer_arrivals_after':t1,
        'disabled_reproduction_absolute_errors':differences,'new_date_accuracy':'NOT_EVALUATED','production_writes':False}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(result,ensure_ascii=False),flush=True)
    return passed
if __name__=='__main__':raise SystemExit(0 if main() else 2)
