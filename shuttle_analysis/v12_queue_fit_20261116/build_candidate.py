"""Preserve the student strategy; correct information/commitment mechanisms privately."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,hashlib,shutil
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'261115160710'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    assert not p.exists(),p
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    stamp=datetime.now(timezone(timedelta(hours=9))).strftime('%y%m%d%H%M%S');w=ROOT.parent/stamp;w.mkdir();m=read(PARENT/'repair_manifest.json')
    names=[p.name for p in PARENT.glob('*.py')]+['input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md']
    for name in names:shutil.copy2(PARENT/name,w/name)
    for name,digest in m['frozen_payloads'].items():
        assert sha(PARENT/name)==digest
        t=w/name;t.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(PARENT/name,t)
    for p in PARENT.glob('physical_paths_*.json.gz'):shutil.copy2(p,w/p.name)
    cfg=read(PARENT/'config.json');cfg.update(release_id=stamp,version_family='V12-student-queue-fit',
        retain_released_mode_flexibility=True,city_initial_information='headway_expectation',patience_log_sigma=.1,
        diagnostic_uids=[3900544,3695872,1795089,4625936,2644624],
        known_information='Physical exogenous clocks are unchanged. City initial stop selection uses unknown-phase headway expectation and causal queue delay, not future second-exact phase. Queue reviews retain the inherited scenario-clock information; neither is observed student tracking or validated live prediction.',
        initial_assignment_interpretation='Inherited initial mode retained; city users choose personally perceived fastest boarding stop using headway expectation, current causal queue delay and existing walking prior/2min utility scale. No oracle future-second phase.',
        calibration_status='Mechanism corrections plus declared unmeasured narrower patience dispersion; reused reports assess fit, not independent field validation.',
        patience_interpretation='Fixed per person median20min with log_sigma0.1: approx95%16.4..24.3min. No hard abandonment clock; sigma is a disclosed scenario, not identified by queue snapshots.')
    save(w/'config.json',cfg);lock=read(PARENT/'experiment_lock.json');lock.update(release_id=stamp,implementation_parent=str(PARENT),comparison_parent=PARENT.name,status='REGISTERED_BEFORE_EXECUTION')
    lock['pilot_cases']=[{**x,'case':x['case'].replace('direction-','queuefit-')} for x in lock['pilot_cases']]
    lock['pilot_cases'] += [
        {'case':'ablation-wide-patience-mon','mode':'combined','day':'월','scenario':'regular','seed':0,'operations':'v12_empirical','config_overrides':{'patience_log_sigma':.25}},
        {'case':'ablation-legacy-initial-mon','mode':'combined','day':'월','scenario':'regular','seed':0,'operations':'v12_empirical','config_overrides':{'city_initial_information':'legacy_exact'}}]
    lock['selection_rule']='Main settings fixed before outputs. First mainMon/Tue plus2Monday mechanism diagnostics. If physics/behavior pass and reused gate/combined queue errors improve, run remaining8main cases. All12conditions once; no numeric demand/capacity/clock fitting, no new raw outcome dates opened. Exceedances and all reused-observation regressions retained.'
    lock['retained_user_behavior']=['initial shuttle loyalty until heterogeneous expected-wait threshold','city two actual full buses plus further queue delay reconsideration','no visited boarding-stop returns','unlimited rerouting with repeat aversion','nearby walking and legal enroute boarding','SNU gate final fallback','correct terminal5516 direction']
    save(w/'experiment_lock.json',lock)
    protected={**m['protected'],**{str(PARENT/n):sha(PARENT/n) for n in names+['config.json','experiment_lock.json','future_evaluation_plan.json','grid-validation.json','grid-behavior-validation.json','grid-RESULTS.md','handoff-manifest.json']}}
    save(w/'repair_manifest.json',{'parent':str(PARENT),'release_id':stamp,'protected':protected,'frozen_payloads':m['frozen_payloads'],'config_sha256':sha(w/'config.json'),'production_writes':False})
    save(ROOT/f'candidate_{stamp}.json',{'release_id':stamp,'path':str(w),'comparison_parent':PARENT.name});print(w,flush=True)
if __name__=='__main__':main()
