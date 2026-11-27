"""New immutable private candidate; no rewriting completed V12 runs or production."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import argparse,hashlib,json,shutil
from projection_patch import apply
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent;PARENT=ANALYSIS/'261112132736'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists(),str(p)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--known-only',action='store_true');parser.add_argument('--walk-variation',action='store_true');parser.add_argument('--release-scale',type=float,default=1.);args=parser.parse_args()
    assert not args.walk_variation or args.known_only,'Walking contrast uses the known-load projection variant'
    assert args.release_scale in (.5,.75,1.)
    assert args.release_scale==1. or args.walk_variation
    stamp=datetime.now(timezone(timedelta(hours=9))).strftime('%y%m%d%H%M%S');work=ANALYSIS/stamp;work.mkdir()
    names=[p.name for p in PARENT.glob('*.py')]+['input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md']
    for name in names:shutil.copy2(PARENT/name,work/name)
    manifest=read(PARENT/'input_manifest.json');frozen=list(manifest['frozen'])
    for name in ('capacity44_amendment.json','pair_amendment.json'):frozen+=read(PARENT/name).get('additional_frozen',[])
    for row in {x['path']:x for x in frozen}.values():
        source=PARENT/row['path'];assert sha(source)==row['sha256'];target=work/row['path']
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    for p in PARENT.glob('physical_paths_*.json.gz'):shutil.copy2(p,work/p.name)
    cfg=read(PARENT/'config.json');cfg.update(release_id=stamp,version_family='V12-empirical-refinement',
      project_queue_load_for_crowding=True,
      fallback_crowding_interpretation='Same conditional FIFO seat projection used by feasibility and fallback crowding. Includes currently known ahead boardings and inherited past-residual proxy; not observed occupancy or full future route load trajectory. Existing categorical grade exposure unchanged.')
    if args.known_only:
        cfg['crowding_projection_known_only']=True
        cfg['fallback_crowding_interpretation']='Known retained onboard plus this chosen vehicle known FIFO-ahead boardings plus marginal person. Historical reserved capacity is diagnostic only, never imputed as observed passengers. Entry-load proxy held over inherited ride, not full future load trajectory. Categorical grade costs unchanged.'
    save(work/'config.json',cfg);apply(work,known_only=args.known_only)
    if args.walk_variation:
        from walking_variation_patch import apply as walking_apply
        walking_apply(work)
        cfg['restore_source_walking_variation']=True
        cfg['walking_variation_interpretation']='Restore inherited relative person-specific factors from frozen prepared.walk_scales, on top of the retained nominal4.8km/h path-local physics. No new speed distribution or random draws. Factors and nominal speed are scenarios, not SNU measurements.'
        (work/'config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
    if args.release_scale!=1.:
        from release_calibration_patch import apply as release_apply
        frozen+=release_apply(work,ROOT)
        cfg['cohort_release_lag_scale']=args.release_scale
        cfg['cohort_release_interpretation']='Retrospective global scaling of inherited unmeasured class-end-to-building-departure lag; same class, location, destination and mass; no departures before class end. Parameter chosen with already used reports, not independently validated actual egress behavior.'
        cfg['calibration_status']='Only the global effective release-lag scale is retrospectively fit to reused constraints; whole model not independently validated.'
        cfg['unverified_parameters']='Legacy tastes, hazards, walking and grade mappings remain prototype assumptions. Effective release lag is retrospectively calibrated on reused SNU queue constraints; not identified actual building egress.'
        (work/'config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
    shutil.copy2(ROOT/'test_projected_load.py',work/'test_projected_load.py')
    if args.walk_variation:shutil.copy2(ROOT/'test_walking_variation.py',work/'test_walking_variation.py')
    if args.release_scale!=1.:shutil.copy2(ROOT/'test_release_calibration.py',work/'test_release_calibration.py')
    cases=[]
    for case in read(PARENT/'experiment_lock.json')['pilot_cases']:
        if case['case'].startswith('ablation'):continue
        prefix=f'release{str(args.release_scale).replace(".","p")}-combined' if args.release_scale!=1. else 'walkvar-combined' if args.walk_variation else 'knownload-combined' if args.known_only else 'projection-combined'
        cases.append({**case,'case':case['case'].replace('repair-combined',prefix)})
    save(work/'experiment_lock.json',{'status':'REGISTERED_BEFORE_EXECUTION','release_id':stamp,'version_family':'V12-empirical-refinement',
      'pilot_cases':cases,'comparison_parent':str(PARENT),'selection_rule':('Retrospective scalar calibration grid alpha in[.5,.75,1]. Primary objective: mean over three direction-confirmed reports of uniform-minute expected absolute distance to count/interval divided by observation midpoint; culture direction uncertain so secondary only. Preserve all outputs. Prefer feasible candidate with minimum primary loss; ties closest to1. Check full10conditions before accepting; not pristine holdout.' if args.release_scale!=1. else 'First Mon/Tue regular compare four known report constraints; if viable, all weekday/scenario cases. No numerical coefficient fit in this candidate.'),
      'calibrated_parameter':{'name':'cohort_release_lag_scale','value':args.release_scale,'candidate_grid':[.5,.75,1.],'observations_independent_holdout':False} if args.release_scale!=1. else None,
      'gates':['same frozen demand, supply, walking physics and individual seed as parent',
        'same-state first-boardable physical time unchanged; projected load matches its FIFO seat accounting',
        'full capacity/FIFO/mass/time audit; no forced exits or20minute clipping','expose all-recorded waits and whole-journey tails',
        'report every known queue constraint and mean walking/total-time regressions'],
      'pristine_empirical_validation':False,'new_day_outcomes_opened':False,'production_replacement_allowed':False})
    protected={str(PARENT/name):sha(PARENT/name) for name in names+['config.json','RESULTS_FINAL.md','grid-validation.json']}
    latest=ANALYSIS/'simulation_viewer_2026-11-07/public/routing-model/latest.json';protected[str(latest)]=sha(latest)
    save(work/'repair_manifest.json',{'parent':str(PARENT),'release_id':stamp,'protected':protected,
      'frozen_payloads':{r['path']:r['sha256'] for r in frozen},'config_sha256':sha(work/'config.json'),
      'changes':['Fix inconsistent future fallback load after projecting queue boardings. No new parameters, demand shift or capacity change.',
        'Historical reservation excluded from crowding load; retained as separate upper scenario diagnostic.' if args.known_only else 'Historical reservation used as conservative upper load proxy; sensitivity candidate, not observed occupancy.']+(['Restore inherited walking variation and independently reconstruct physical leg durations from frozen parent factor.'] if args.walk_variation else [])+([f'Retrospective departure lag scalar alpha={args.release_scale}; quantity preserved; independent validator uses class-end lineage.'] if args.release_scale!=1. else []),
      'production_writes':False})
    save(ROOT/f'candidate_{stamp}.json',{'release_id':stamp,'path':str(work),'parent':str(PARENT)})
    print(str(work),flush=True)
if __name__=='__main__':main()
