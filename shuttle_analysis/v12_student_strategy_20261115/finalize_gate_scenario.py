"""Keep observed full-bus experience; reuse an identical completed diagnostic run."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib, json, shutil
ROOT=Path(__file__).resolve().parent
PARENT=ROOT.parent/'261115153406'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    assert not p.exists(),p
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    stamp=datetime.now(timezone(timedelta(hours=9))).strftime('%y%m%d%H%M%S');w=ROOT.parent/stamp;w.mkdir()
    m=read(PARENT/'repair_manifest.json')
    names=[p.name for p in PARENT.glob('*.py')]+['input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md']
    for name in names:shutil.copy2(PARENT/name,w/name)
    for name,digest in m['frozen_payloads'].items():
        assert sha(PARENT/name)==digest
        target=w/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(PARENT/name,target)
    for p in PARENT.glob('physical_paths_*.json.gz'):shutil.copy2(p,w/p.name)
    c=read(PARENT/'config.json');c.update(release_id=stamp,version_family='V12-student-behavior-final',learn_past_residual_seats=True,
        seat_forecast_interpretation='Retain inherited causal past residual-seat proxy and actual denied-boarding experience. This is a subjective model assumption, not measured numeric onboard occupancy.')
    save(w/'config.json',c)
    lock=read(PARENT/'experiment_lock.json');lock.update(release_id=stamp,implementation_parent=str(PARENT),status='REGISTERED_BEFORE_REMAINING_CASES_WITH_DISCLOSED_REUSE')
    lock['pilot_cases']=[{**r,'case':r['case'].replace('strategy4-','student-')} for r in lock['pilot_cases'] if not r['case'].startswith('ablation')]
    first=next(r for r in lock['pilot_cases'] if r['day']=='월' and r['scenario']=='regular')
    source=PARENT/'runs/ablation-gate-only-mon/attempt_01'
    lock['reused_completed_runs']={first['case']:str(source)}
    lock['refinement_reason']='Keep the inherited observed-full-bus experience mechanism: disabling it was an additional unrequested assumption and increased waiting in the registered Monday sensitivity test. Gate absorbing, complete strategy deduplication, locked route pools, no returns, and prospective heterogeneous patience remain.'
    lock['selection_rule']='Decision follows the completed diagnostic comparison, not unseen-outcome selection. No numerical parameters fitted. Monday is reused only after exact runtime/input/effective-config equivalence excluding inert labeling fields; remaining nine conditions run once. Report all waits, including20min exceedances.'
    save(w/'experiment_lock.json',lock)
    protected={**m['protected'],**{str(PARENT/n):sha(PARENT/n) for n in names+['config.json','experiment_lock.json','future_evaluation_plan.json','ablation-validation.json','observations-validation.json']}}
    for n in ['started.json','result.json','repair_analysis.json','audit-regular-mon.json.gz','regular-mon.json.gz']:
        protected[str(source/n)]=sha(source/n)
    save(w/'repair_manifest.json',{'parent':str(PARENT),'release_id':stamp,'protected':protected,'frozen_payloads':m['frozen_payloads'],'config_sha256':sha(w/'config.json'),'production_writes':False})
    save(ROOT/f'candidate_{stamp}.json',{'release_id':stamp,'path':str(w),'implementation_parent':str(PARENT),'comparison_parent':'261112220847'})
    print(w,flush=True)
if __name__=='__main__':main()
