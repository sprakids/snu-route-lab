"""Trace a rare long journey using the engine's recorded leg types0,1,3."""
from pathlib import Path
import gzip,hashlib,json,math
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent;WORK=ANALYSIS/'261112171315'
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def detail(trip,nodes):
    kinds={'walk':0,'queue_wait':1,'ride':3}
    by={name:math.fsum(l[2]-l[1] for l in trip['legs'] if l[0]==k)/60 for name,k in kinds.items()}
    assert all(l[0] in kinds.values() for l in trip['legs'])
    total=(trip['finish_time']-trip['start'])/60;assert abs(math.fsum(by.values())-total)<1e-6
    return {'id':trip['id'],'parent_id':trip['parent_id'],'weight':trip['weight'],'duration_min':total,
      'leg_time_minutes':by,'route_change_count':len(trip['history']),'history':trip['history'],
      'wait_stop_names':[nodes[l[4]]['name'] for l in trip['legs'] if l[0]==1]}
def main():
    target=WORK/'tail_regression_diagnosis_final.json';assert not target.exists()
    d=read(WORK/'observations-diagnostics.json');c=next(r for r in d['cases'] if r['case']['day']=='화')
    path=Path(c['source_directory'])/'audit-regular-tue.json.gz';a=read(path)
    t=next(t for t in a['legs'] if t['id']==c['worst_trip']['id'])
    nodes=read(WORK/'frozen/prepared_capacity44_pair.json.gz')['prepared']['common']['nodes']
    baseline=read(ANALYSIS/'261112132736/grid-validation.json');b=next(r for r in baseline['results'] if r['case']['day']=='화' and r['case']['scenario']=='regular')
    oldpath=Path(b['source_directory'])/'audit-regular-tue.json.gz';old=read(oldpath)
    parent=[x for x in old['legs'] if x['parent_id']==t['parent_id']]
    mass=math.fsum(x['weight'] for x in a['legs']);finished=[x for x in a['legs'] if not x['unserved']]
    out={'status':'RARE_TAIL_REGRESSION_EXPOSED_NOT_CAUSAL_ISOLATION','new_case':c['case'],
      'new_worst':detail(t,nodes),'same_source_parent_before':[detail(x,nodes) for x in parent],
      'case_scenario_weight':mass,'new_worst_weight_share':t['weight']/mass,
      'over90_trip_weight':math.fsum(x['weight'] for x in finished if x['finish_time']-x['start']>5400),
      'source_audit_sha256':sha(path),'parent_audit_sha256':sha(oldpath),
      'correction_note':'Earlier tail_regression_diagnosis.json omitted ride type3. A preserved label snapshot later called unused type2 preparation. The engine records0 walk/1 queue/3 ride; boarding preparation is inside queue time, not separately measured. This file asserts the full duration sum. Earlier diagnostics are retained, not model failures.',
      'interpretation':'Same source parent, different individual timing, walking factor and endogenous random decision path. This is not alpha-only causal attribution. Unlimited changes allow rare long histories; first-boardable continuation remains approximate. Do not clip the trip or count its weight as a measured person.'}
    target.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
    print('TAIL_TRACE',out['new_worst']['leg_time_minutes'],'total',out['new_worst']['duration_min'],
      'weight_share',out['new_worst_weight_share'],'before',[x['duration_min'] for x in out['same_source_parent_before']],flush=True)
if __name__=='__main__':main()
