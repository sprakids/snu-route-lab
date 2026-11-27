"""Preserve first pilot and fix demonstrated current-stop return / myopic patience."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,hashlib,shutil
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'261115144206'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):assert not p.exists(),p;p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    stamp=datetime.now(timezone(timedelta(hours=9))).strftime('%y%m%d%H%M%S');w=ROOT.parent/stamp;w.mkdir()
    names=[p.name for p in PARENT.glob('*.py')]+['input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md']
    for name in names:shutil.copy2(PARENT/name,w/name)
    frozen=read(PARENT/'repair_manifest.json')['frozen_payloads']
    for name,digest in frozen.items():
        source=PARENT/name;assert sha(source)==digest;target=w/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    for p in PARENT.glob('physical_paths_*.json.gz'):shutil.copy2(p,w/p.name)
    cfg=read(PARENT/'config.json');cfg['release_id']=stamp;cfg['version_family']='V12-student-strategy-prospective';cfg['patience_uses_elapsed_plus_forecast']=True
    save(w/'config.json',cfg);lock=read(PARENT/'experiment_lock.json');lock.update(release_id=stamp,implementation_parent=str(PARENT),comparison_parent=str(ROOT.parent/'261112220847'))
    lock['pilot_cases']=[{**c,'case':c['case'].replace('strategy-','strategy2-')} for c in lock['pilot_cases']]
    lock['refinement_reason']='First pilot exposed A->B->A via not-yet-left current node; patience considered elapsed only and ignored visibly long prospective queue. Freeze new candidate; preserve first outcomes.'
    save(w/'experiment_lock.json',lock)
    protected={**read(PARENT/'repair_manifest.json')['protected'],**{str(PARENT/n):sha(PARENT/n) for n in names+['config.json','observations-validation.json','observations-behavior-validation.json']}}
    save(w/'repair_manifest.json',{'parent':str(PARENT),'release_id':stamp,'protected':protected,'frozen_payloads':frozen,'config_sha256':sha(w/'config.json'),'production_writes':False})
    p=w/'behavioral_policy.py';s=p.read_text(encoding='utf8')
    s=s.replace("forbidden=frozenset(state.get('visited',()));current=state.get('node') if allow_current and (state.get('queued') or state.get('preparing')) else None", "forbidden=set(state.get('visited',()))\n        if not allow_current and state.get('node') is not None and ('arrival' in state or state.get('queued') or state.get('preparing')):forbidden.add(state['node'])\n        forbidden=frozenset(forbidden);current=state.get('node') if allow_current and (state.get('queued') or state.get('preparing')) else None")
    s=s.replace("    def context(state,at,current=None):", "    missing=object()\n    def context(state,at,current=missing):")
    s=s.replace("        # Count compatible departures BEFORE the first forecast-boardable bus.", "        if current is missing:current=policy.predict(state['stages'][state['stage']:],at,state,keep=True)\n        expected=age+current.first_wait if current is not None else None\n        state['student_expected_queue_wait_seconds']=expected\n        # Count compatible departures BEFORE the first forecast-boardable bus.")
    s=s.replace("            if current is None:current=policy.predict(state['stages'][state['stage']:],at,state,keep=True)\n",'')
    s=s.replace("stressed=unavailable or frustration(age,patience(state)","stressed=current is None or unavailable or frustration(expected,patience(state)")
    s=s.replace("return raw_maybe(state,at,reason,forced)","return raw_maybe(state,at,'student_anticipated_wait_review' if reason=='arrival' else reason,forced)")
    s=s.replace("'student_predicted_additional_passes':context(state,at,current)[2]}","'student_predicted_additional_passes':context(state,at,current)[2],\n          'student_expected_queue_wait_seconds':state.get('student_expected_queue_wait_seconds')}")
    s=s.replace("'twenty_minutes_is_diagnostic_not_forced_exit':True,", "'twenty_minutes_is_diagnostic_not_forced_exit':True,'patience_includes_visible_forecast':True,")
    p.write_text(s,encoding='utf8')
    p=w/'engine.py';s=p.read_text(encoding='utf8');needle="            if option.node in state['visited']:continue\n"
    assert s.count(needle)==1
    s=s.replace(needle,needle+"            resume_probe={**state,'visited':state['visited']|{option.node},'queued':False,'preparing':False}\n            if policy.student_filter_stages(resume_probe,state['stages'][state['stage']:],allow_current=False) is None:continue\n")
    p.write_text(s,encoding='utf8')
    save(ROOT/f'candidate_{stamp}.json',{'release_id':stamp,'path':str(w),'implementation_parent':str(PARENT),'comparison_parent':'261112220847'})
    print(w,flush=True)
if __name__=='__main__':main()
