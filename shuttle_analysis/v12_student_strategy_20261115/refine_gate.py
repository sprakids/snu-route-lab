"""Make the stated last-resort gate absorbing; separate perceived-seat sensitivity."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,hashlib,shutil
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'261115151942'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):assert not p.exists(),p;p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    stamp=datetime.now(timezone(timedelta(hours=9))).strftime('%y%m%d%H%M%S');w=ROOT.parent/stamp;w.mkdir()
    names=[p.name for p in PARENT.glob('*.py')]+['input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md'];m=read(PARENT/'repair_manifest.json')
    for name in names:shutil.copy2(PARENT/name,w/name)
    for name,digest in m['frozen_payloads'].items():
        source=PARENT/name;assert sha(source)==digest;target=w/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    for p in PARENT.glob('physical_paths_*.json.gz'):shutil.copy2(p,w/p.name)
    c=read(PARENT/'config.json');c.update(release_id=stamp,version_family='V12-student-gate-final',gate_is_final_fallback=True,learn_past_residual_seats=False,
      seat_forecast_interpretation='Subjective expected boarding uses current known model onboard/FIFO/approaches. Two past full arrivals do not hard-reserve all capacity as0 on every future departure within30min. Actual full_passes remain in behavior. This is not observed numeric occupancy.')
    save(w/'config.json',c);lock=read(PARENT/'experiment_lock.json');lock.update(release_id=stamp,implementation_parent=str(PARENT))
    lock['pilot_cases']=[{**r,'case':r['case'].replace('strategy3-','strategy4-')} for r in lock['pilot_cases']]
    lock['pilot_cases'].append({'case':'ablation-gate-only-mon','mode':'combined','day':'월','scenario':'regular','seed':0,'operations':'v12_empirical','config_overrides':{'learn_past_residual_seats':True}})
    lock['refinement_reason']='Observed SNU last-resort gate departure led back into campus and59min waits. Gate becomes final waiting strategy. Separately disclose/sensitivity-test the old hard zero future-seat proxy; no actual supply or load changed.'
    lock['selection_rule']='Fixed final user-shaped scenario before outcomes; gate-only/history-enabled Monday ablation is diagnostic, not parameter tuning. Main Mon/Tue pilot then10main conditions if behavior and physics pass; all20min/patience/unserved diagnostics disclosed.'
    save(w/'experiment_lock.json',lock);protected={**m['protected'],**{str(PARENT/n):sha(PARENT/n) for n in names+['config.json','experiment_lock.json','future_evaluation_plan.json','observations-validation.json']}}
    save(w/'repair_manifest.json',{'parent':str(PARENT),'release_id':stamp,'protected':protected,'frozen_payloads':m['frozen_payloads'],'config_sha256':sha(w/'config.json'),'production_writes':False})
    p=w/'behavioral_policy.py';s=p.read_text(encoding='utf8')
    s=s.replace("        stressed,age,more=context(state,at,current)\n        if not stressed:return candidates", "        if config.get('gate_is_final_fallback') and state['dest']=='snu' and node==config['gate_fallback_node']:return candidates\n        stressed,age,more=context(state,at,current)\n        if not stressed:return candidates")
    s=s.replace("        initialize(state)\n        if state.get('enroute_intercept')", "        initialize(state)\n        if config.get('gate_is_final_fallback') and state['dest']=='snu' and state.get('node')==config['gate_fallback_node']:return False\n        if state.get('enroute_intercept')",1)
    s=s.replace("        if not state.get('queued') or state['done']:return", "        if not state.get('queued') or state['done']:return\n        if config.get('gate_is_final_fallback') and state['dest']=='snu' and state.get('node')==config['gate_fallback_node']:return")
    needle="        initialize(state);result=stage if stage.get('choice_pool_locked') else raw_complete(state,stage,node)"
    replace=needle+"\n        if config.get('gate_is_final_fallback') and state['dest']=='snu' and node==config['gate_fallback_node']:\n            entries=scaled_stages(bundle.get('compatible_route_policies',{}).get(f\"{node}|snu\",[]),state['factor'])\n            for e in entries:e.setdefault('continuation_stages',[])\n            if entries:result={**entries[0],'pool':entries,'choice_pool_locked':True}"
    assert needle in s;s=s.replace(needle,replace);s=s.replace("'patience_includes_visible_forecast':True,", "'patience_includes_visible_forecast':True,'gate_is_final_fallback':True,")
    p.write_text(s,encoding='utf8');save(ROOT/f'candidate_{stamp}.json',{'release_id':stamp,'path':str(w),'implementation_parent':str(PARENT),'comparison_parent':'261112220847'});print(w,flush=True)
if __name__=='__main__':main()
