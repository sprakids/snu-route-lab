"""Same-parent population comparison; includes people who left a queue."""
from pathlib import Path
import argparse,csv,gzip,hashlib,json,math
from collections import defaultdict
from validation_metrics import diagnostics
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def engineering_bins(audit,plans):
    result=defaultdict(lambda:defaultdict(float))
    for trip in audit['legs']:
        p=plans[trip.get('parent_id',trip['id'])]
        if p[1] not in ('301','302') or p[2]!='snu':continue
        r=result[int(p[4]//1800)*1800];w=trip['weight'];r['weight']+=w
        r['unserved_weight']+=w if trip['unserved'] else 0.
        r['wait_min']+=w*math.fsum(l[2]-l[1] for l in trip['legs'] if l[0]==1)/60
        r['walk_min']+=w*math.fsum(l[2]-l[1] for l in trip['legs'] if l[0]==0)/60
        r['total_min']+=w*(trip['legs'][-1][2]-p[4])/60
        r['changes']+=w*len(trip['history'])
    return result
def main(validation):
    root=Path(validation);v=read(root/'validation.json');lock=read(root/'experiment_lock.json')
    target=ROOT/'journey_tail_comparison.json';assert not target.exists()
    names={c['case'] for c in lock['all_weekday_main_cases']};rows=[];proof=[];engineering=[]
    frozen=read(root/'frozen/prepared_capacity44_pair.json.gz')
    for result in v['results']:
        if result['case']['case'] not in names:continue
        case=result['case'];day={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}[case['day']];scenario=case['scenario']
        path=ANALYSIS/f'simulation_viewer_2026-11-07/peak_pair_correction_2026-11-10/audit-{scenario}-{day}.json.gz'
        audit=read(path);mass=math.fsum(t['weight'] for t in audit['legs'])
        assert abs(mass-result['scope']['all']['weight'])<1e-6
        plans={p[0]:p for p in frozen['prepared']['plans'][case['day']]}
        before=diagnostics(audit,40800,83400);before_eng=engineering_bins(audit,plans);del audit
        after=result['extended_diagnostics'];assert before['unserved_trip_weight']<1e-7 and after['unserved_trip_weight']<1e-7
        audit=read(Path(result['source_directory'])/f'audit-{scenario}-{day}.json.gz')
        after_eng=engineering_bins(audit,plans);del audit
        assert set(before_eng)==set(after_eng)
        assert abs(math.fsum(p['weight'] for p in after_eng.values())-result['scope']['engineering_snu']['weight'])<1e-6
        for stamp,b in sorted(before_eng.items()):
            a=after_eng[stamp];assert abs(a['weight']-b['weight'])<1e-6
            assert a['unserved_weight']<1e-7 and b['unserved_weight']<1e-7
            engineering.append({'weekday':case['day'],'scenario':scenario,'class_end_bin_start':stamp,'class_end_bin_end':stamp+1800,
                'trip_weight':a['weight'],**{'baseline_'+k:b[k]/b['weight'] for k in ('wait_min','walk_min','total_min','changes')},
                **{'candidate_'+k:a[k]/a['weight'] for k in ('wait_min','walk_min','total_min','changes')},
                'unserved_before':b['unserved_weight'],'unserved_after':a['unserved_weight']})
        for key in ('wait_min','walk_min','total_min','changes'):
            for side,bins in [('baseline',before_eng),('prototype',after_eng)]:
                total=math.fsum(p['weight'] for p in bins.values())
                if total:assert abs(math.fsum(p[key] for p in bins.values())/total-result['scope']['engineering_snu']['metrics'][key][side])<1e-6
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
    with (ROOT/'engineering_snu_half_hour_comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(engineering[0]));w.writeheader();w.writerows(engineering)
    (ROOT/'engineering_snu_half_hour_comparison.json').write_text(json.dumps({'population':'same original301/302-origin, SNU-station-destination parent trips including walk-aways',
        'grouping':'original class-end time half-hour, NOT queue-entry time or instant queue size','rows':engineering,
        'same_parent_mass_checked':True,'daily_scope_means_cross_checked':True},ensure_ascii=False,indent=2),encoding='utf8')
    with (ROOT/'journey_tail_comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
    target.write_text(json.dumps({'status':'SCENARIO_COMPARISON_NOT_EMPIRICAL_VALIDATION','population':'all original parent-trip weight, including walk-away journeys',
        'main_cells':10,'metrics':'minutes except changes/count; quantiles weighted by completed trip mass',
        'unserved_not_hidden':True,'rows':rows,'audit_proof':proof},ensure_ascii=False,indent=2),encoding='utf8')
    print('ALL_TAIL_CELLS_DONE',len(rows),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--validation',required=True);a=p.parse_args();main(a.validation)
