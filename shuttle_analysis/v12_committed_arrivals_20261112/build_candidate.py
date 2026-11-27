"""Separate immutable candidate from171315; no change to tastes or fitted timing."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,shutil
from forecast_patch import apply
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent;PARENT=ANALYSIS/'261112171315'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists(),str(p);p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    stamp=datetime.now(timezone(timedelta(hours=9))).strftime('%y%m%d%H%M%S');work=ANALYSIS/stamp;work.mkdir()
    names=[p.name for p in PARENT.glob('*.py')]+['input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md']
    for name in names:shutil.copy2(PARENT/name,work/name)
    frozen=read(PARENT/'input_manifest.json')['frozen']
    for name in ('capacity44_amendment.json','pair_amendment.json'):frozen+=read(PARENT/name).get('additional_frozen',[])
    for r in {r['path']:r for r in frozen}.values():
        source=PARENT/r['path'];assert sha(source)==r['sha256'];dest=work/r['path'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
    for path in PARENT.glob('physical_paths_*.json.gz'):shutil.copy2(path,work/path.name)
    cfg=read(PARENT/'config.json');cfg.update(release_id=stamp,version_family='V12-committed-arrivals',forecast_committed_arrivals=True,
      committed_arrivals_information='Simulation information assumption: already-started approach intent and readiness known to predictor; excludes future departures, later rerouting and realized future queue. Not measured student tracking.',
      later_walking_preference='Preserve171315 preferences, cumulative wait burden, unlimited changes and walking distance priors unchanged as requested.')
    save(work/'config.json',cfg);apply(work)
    shutil.copy2(ROOT/'test_committed_arrivals.py',work/'test_committed_arrivals.py')
    cases=[{**c,'case':c['case'].replace('release1p125-combined','committed-combined')} for c in read(PARENT/'experiment_lock.json')['pilot_cases']]
    save(work/'experiment_lock.json',{'status':'REGISTERED_BEFORE_EXECUTION','release_id':stamp,'pilot_cases':cases,'comparison_parent':str(PARENT),
      'change_scope':'Known committed approaches/preparation in FIFO seat forecast and complete decline prediction logging only; no preference or supply fitting.',
      'selection_rule':'Mon/Tue regular first. Reject continuous wait>20 or unserved. Review budget: primary reused-report loss not more than10percent worse; each pilot mean total not more than0.5min worse and p99 not more than1min worse. These are engineering review budgets, not statistical confidence bounds. Report all regressions and rare tails. Full weekday by regular/peak10 conditions before recommendation.',
      'unchanged_parameters':'alpha1.125, all tastes/hazards/walking priors/speed factors/supply/source mass and initial mixture.',
      'pristine_empirical_validation':False,'new_day_outcomes_opened':False,'production_replacement_allowed':False})
    protected={str(PARENT/n):sha(PARENT/n) for n in names+['config.json','RESULTS_FINAL.md','grid-validation.json']}
    latest=ANALYSIS/'simulation_viewer_2026-11-07/public/routing-model/latest.json';protected[str(latest)]=sha(latest)
    save(work/'repair_manifest.json',{'parent':str(PARENT),'release_id':stamp,'protected':protected,
      'frozen_payloads':{r['path']:r['sha256'] for r in frozen},'config_sha256':sha(work/'config.json'),
      'changes':['Causal pending FIFO forecast, already-started commitments only','Full board/wait/selected vectors logged for declined opportunities; walking preference unchanged'],
      'production_writes':False})
    save(ROOT/f'candidate_{stamp}.json',{'release_id':stamp,'path':str(work),'parent':str(PARENT)})
    print(work,flush=True)
if __name__=='__main__':main()
