"""Same-parent population comparison; includes people who left a queue."""
from pathlib import Path
import argparse,csv,gzip,hashlib,json,math
from validation_metrics import diagnostics
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(validation):
    root=Path(validation);v=read(root/'validation.json');lock=read(root/'experiment_lock.json')
    target=ROOT/'journey_tail_comparison.json';assert not target.exists()
    names={c['case'] for c in lock['all_weekday_main_cases']};rows=[];proof=[]
    for result in v['results']:
        if result['case']['case'] not in names:continue
        case=result['case'];day={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}[case['day']];scenario=case['scenario']
        path=ANALYSIS/f'simulation_viewer_2026-11-07/peak_pair_correction_2026-11-10/audit-{scenario}-{day}.json.gz'
        audit=read(path);mass=math.fsum(t['weight'] for t in audit['legs'])
        assert abs(mass-result['scope']['all']['weight'])<1e-6
        before=diagnostics(audit,40800,83400);del audit
        after=result['extended_diagnostics'];assert before['unserved_trip_weight']<1e-7 and after['unserved_trip_weight']<1e-7
        for name,key in [('walk_min','walk_min'),('cumulative_wait_min','wait_min'),('total_min','total_min'),('changes','changes')]:
            b=before['finished_trip_quantiles'][name];a=after['finished_trip_quantiles'][name]
            if name!='changes':assert abs(b['mean']-result['scope']['all']['metrics'][key]['baseline'])<1e-6
            rows.append({'weekday':case['day'],'scenario':scenario,'metric':name,'same_parent_weight':mass,
                         **{'baseline_'+q:b[q] for q in ('mean','p50','p90','p95','p99','maximum')},
                         **{'candidate_'+q:a[q] for q in ('mean','p50','p90','p95','p99','maximum')},
                         'unserved_before':before['unserved_trip_weight'],'unserved_after':after['unserved_trip_weight']})
        proof.append({'case':case['case'],'reference_audit':str(path),'reference_audit_sha256':sha(path),
                      'candidate_audit_sha256':result['audit_sha256'],'before':before,'after':after})
        print('TAIL_CELL',case['case'],flush=True)
    assert len(rows)==40 and len(proof)==10
    with (ROOT/'journey_tail_comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
    target.write_text(json.dumps({'status':'SCENARIO_COMPARISON_NOT_EMPIRICAL_VALIDATION','population':'all original parent-trip weight, including walk-away journeys',
        'main_cells':10,'metrics':'minutes except changes/count; quantiles weighted by completed trip mass',
        'unserved_not_hidden':True,'rows':rows,'audit_proof':proof},ensure_ascii=False,indent=2),encoding='utf8')
    print('ALL_TAIL_CELLS_DONE',len(rows),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--validation',required=True);a=p.parse_args();main(a.validation)
