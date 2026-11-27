"""Private user-requested geometric walking scenario, fixed growth2 before runs."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,shutil
from repeat_patch import apply
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent;PARENT=ANALYSIS/'261112210916'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists(),str(p);p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    stamp=datetime.now(timezone(timedelta(hours=9))).strftime('%y%m%d%H%M%S');w=ANALYSIS/stamp;w.mkdir()
    names=[p.name for p in PARENT.glob('*.py')]+['input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md']
    for name in names:shutil.copy2(PARENT/name,w/name)
    frozen=read(PARENT/'input_manifest.json')['frozen']
    for name in ('capacity44_amendment.json','pair_amendment.json'):frozen+=read(PARENT/name).get('additional_frozen',[])
    for r in {r['path']:r for r in frozen}.values():
        src=PARENT/r['path'];assert sha(src)==r['sha256'];p=w/r['path'];p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,p)
    for p in PARENT.glob('physical_paths_*.json.gz'):shutil.copy2(p,w/p.name)
    cfg=read(PARENT/'config.json');cfg.update(release_id=stamp,version_family='V12-repeat-walk',exponential_repeat_walk=True,
      repeat_walk_growth_factor=2.,repeat_walk_numeric_epsilon=1e-12,
      repeat_walk_interpretation='User-directed terminal walk probability p_n=1-(1-p_reference)^(2^n), conditional on an actual decision opportunity. Reference neutralizes only incremental count-dependent changing-action fee. Same current distance/wait/cost context; probability, not physical ETA. Not estimated from observed students.',
      later_walking_preference='Base costs/distance priors retained; completed rerouting count now explicitly increases terminal-walk choice probability. Transfers to another bus stop are not boosted. Review timing and unlimited change counts unchanged.')
    save(w/'config.json',cfg);apply(w);shutil.copy2(ROOT/'test_repeat_walk.py',w/'test_repeat_walk.py')
    cases=[{**c,'case':c['case'].replace('committed-combined','repeatwalk-combined')} for c in read(PARENT/'experiment_lock.json')['pilot_cases']]
    save(w/'experiment_lock.json',{'status':'REGISTERED_BEFORE_EXECUTION','release_id':stamp,'pilot_cases':cases,'comparison_parent':str(PARENT),
      'change_scope':'User-requested exponentially increasing conditional probability of terminal walking; fixed growth2, no fitting. Base costs, distance function, review timing, supply, causal approach forecast and alpha1.125 retained.',
      'selection_rule':'Mon/Tue regular first then all weekday by regular/peak10 if physical invariants, all-recorded continuous wait<=20 and no unserved pass. Report all field errors, mean/p99/max, walking and change distributions; no tuning of growth against four reused reports.',
      'probability_scope':'Conditional on feasible decision set and current iid choice errors. Population rates across surviving contexts and review frequency are separate.',
      'new_day_outcomes_opened':False,'pristine_empirical_validation':False,'production_replacement_allowed':False})
    protected={str(PARENT/name):sha(PARENT/name) for name in names+['config.json','RESULTS_FINAL.md','grid-validation.json']}
    latest=ANALYSIS/'simulation_viewer_2026-11-07/public/routing-model/latest.json';protected[str(latest)]=sha(latest)
    save(w/'repair_manifest.json',{'parent':str(PARENT),'release_id':stamp,'protected':protected,'frozen_payloads':{r['path']:r['sha256'] for r in frozen},
      'config_sha256':sha(w/'config.json'),'changes':['Group probability exponential transform for terminal walking only','Reference cost removes counteracting count increment only for baseline probability; raw cost/physical ETA retained','Existing route-change review rate and no hard maximum retained'],
      'production_writes':False})
    save(ROOT/f'candidate_{stamp}.json',{'release_id':stamp,'path':str(w),'parent':str(PARENT)});print(w,flush=True)
if __name__=='__main__':main()
