"""Create an isolated candidate for the user's stated student departure strategy."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'261112220847'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def save(p,v):assert not p.exists(),p;p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    stamp=datetime.now(timezone(timedelta(hours=9))).strftime('%y%m%d%H%M%S');w=ROOT.parent/stamp;w.mkdir()
    names=[p.name for p in PARENT.glob('*.py')]+['input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md']
    for name in names:shutil.copy2(PARENT/name,w/name)
    shutil.copytree(PARENT/'frozen',w/'frozen',ignore=shutil.ignore_patterns('__pycache__'))
    inherited=read(PARENT/'input_manifest.json')['frozen']
    for name in ('capacity44_amendment.json','pair_amendment.json'):inherited+=read(PARENT/name).get('additional_frozen',[])
    for record in {r['path']:r for r in inherited}.values():
        source=PARENT/record['path'];target=w/record['path'];assert sha(source)==record['sha256']
        if not target.exists():target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        else:assert sha(target)==record['sha256']
    for p in PARENT.glob('physical_paths_*.json.gz'):shutil.copy2(p,w/p.name)
    c=read(PARENT/'config.json');c.update(release_id=stamp,version_family='V12-student-strategy',student_strategy=True,
      initial_assignment_policy='preserve_source_mode_optimize_city_stop',shuttle_patience_median_seconds=1200.,city_patience_median_seconds=1200.,
      patience_log_sigma=.25,dorm_walk_patience_factor=1.,city_denial_trigger=2,city_additional_pass_trigger=2,
      forbid_revisited_boarding_stops=True,far_terminal_walk_max_meters=1000.,gate_fallback_node=62,
      enroute_boarding_window_seconds=30.,enroute_max_extra_meters=80.,enroute_max_lateral_meters=30.,
      scenario_scope='User-reported behavioral hypotheses; patience dispersion and short enroute encounter window are unmeasured scenarios.20min is a diagnostic, not forced abandonment. Source modal cohorts, destination and mass retained; far initial SNU walk redirected to a city-bus strategy.',
      later_walking_preference='Repeated-change terminal-walk probability retained for accessible destinations; far SNU walkers use transit/gate fallback. Personal patience and denial experience govern opportunities.')
    save(w/'config.json',c)
    lock=read(PARENT/'experiment_lock.json');cases=[{**r,'case':r['case'].replace('repeatwalk-','strategy-')} for r in lock['pilot_cases']]
    save(w/'experiment_lock.json',{'status':'REGISTERED_BEFORE_EXECUTION','release_id':stamp,'pilot_cases':cases,'comparison_parent':str(PARENT),
      'change_scope':'Initial mode loyalty, earliest boardable city stop, heterogeneous patience, two-denial plus remaining queue trigger, no stop return, accessible destination walk, gate fallback, legal enroute boarding.',
      'selection_rule':'Mon/Tue regular pilot then all weekdays x regular/peak if capacity/FIFO/mass/physical time, destination, revisit and far-walk checks pass.20min exceedances and unfinished mass remain visible diagnostics; never delete or force-exit demand to pass.',
      'new_day_outcomes_opened':False,'pristine_empirical_validation':False,'production_replacement_allowed':False})
    protected={str(PARENT/name):sha(PARENT/name) for name in names+['config.json','RESULTS_FINAL.md','grid-validation.json']}
    live=ROOT.parent/'simulation_viewer_2026-11-07/public/routing-model/latest.json';protected[str(live)]=sha(live)
    frozen={str(p.relative_to(w)):sha(p) for p in (w/'frozen').iterdir() if p.is_file()}
    frozen.update({r['path']:r['sha256'] for r in inherited})
    save(w/'repair_manifest.json',{'parent':str(PARENT),'release_id':stamp,'protected':protected,'frozen_payloads':frozen,'config_sha256':sha(w/'config.json'),'production_writes':False})
    # New modules must join the STARTED source snapshots before running anything.
    p=w/'run_case.py';s=p.read_text(encoding='utf8');s=s.replace("'time_profiles.py','run_case.py')","'time_profiles.py','behavioral_policy.py','walking_opportunities.py','run_case.py')");p.write_text(s,encoding='utf8')
    save(ROOT/f'candidate_{stamp}.json',{'release_id':stamp,'path':str(w),'parent':str(PARENT)});print(w,flush=True)
if __name__=='__main__':main()
