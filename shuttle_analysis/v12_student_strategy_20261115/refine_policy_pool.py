"""Correct the route-pool dominance counterexample in another immutable candidate."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,hashlib,shutil
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'261115150714'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):assert not p.exists(),p;p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    stamp=datetime.now(timezone(timedelta(hours=9))).strftime('%y%m%d%H%M%S');w=ROOT.parent/stamp;w.mkdir()
    names=[p.name for p in PARENT.glob('*.py')]+['input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md']
    for name in names:shutil.copy2(PARENT/name,w/name)
    m=read(PARENT/'repair_manifest.json')
    for name,digest in m['frozen_payloads'].items():
        source=PARENT/name;assert sha(source)==digest;target=w/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    for p in PARENT.glob('physical_paths_*.json.gz'):shutil.copy2(p,w/p.name)
    cfg=read(PARENT/'config.json');cfg.update(release_id=stamp,version_family='V12-student-strategy-consistent-pool',respect_selected_route_pool=True);save(w/'config.json',cfg)
    lock=read(PARENT/'experiment_lock.json');lock.update(release_id=stamp,implementation_parent=str(PARENT));lock['pilot_cases']=[{**c,'case':c['case'].replace('strategy2-','strategy3-')} for c in lock['pilot_cases']]
    lock['refinement_reason']='More compulsory services do not dominate a narrower strategy: fast arrival B can be a much slower ride than A. Keep distinct eligible policies and honor locked pools in execution.';save(w/'experiment_lock.json',lock)
    protected={**m['protected'],**{str(PARENT/n):sha(PARENT/n) for n in names+['config.json','experiment_lock.json','future_evaluation_plan.json']}}
    save(w/'repair_manifest.json',{'parent':str(PARENT),'release_id':stamp,'protected':protected,'frozen_payloads':m['frozen_payloads'],'config_sha256':sha(w/'config.json'),'production_writes':False})
    p=w/'behavioral_policy.py';s=p.read_text(encoding='utf8');start=s.index('def remove_redundant(candidates):');end=s.index('\ndef frustration(',start)
    s=s[:start]+'''def remove_redundant(candidates):
    # With compulsory first-compatible boarding, a larger service set may
    # force a slow earlier bus. Only identical strategies are duplicates.
    unique={}
    for c in candidates:
        o=c.get('option')
        key=('stay',c['key']) if o is None else (o['walk'][0],complete_signature(o['stages']))
        if key not in unique or c['cost']<unique[key]['cost']:unique[key]=c
    return list(unique.values())
''' + s[end:]
    s=s.replace("initialize(state);result=raw_complete(state,stage,node)","initialize(state);result=stage if stage.get('choice_pool_locked') else raw_complete(state,stage,node)")
    p.write_text(s,encoding='utf8');save(ROOT/f'candidate_{stamp}.json',{'release_id':stamp,'path':str(w),'implementation_parent':str(PARENT),'comparison_parent':'261112220847'});print(w,flush=True)
if __name__=='__main__':main()
