"""Freeze existing inputs and pre-register a finite offline pilot, never latest."""
from pathlib import Path
import sys,shutil,json
from artifacts import ROOT,SIM,SOURCE,read,save,sha,packed

def main():
    target=ROOT/'input_manifest.json';assert not target.exists(),'Existing experiment lock must be preserved'
    selection=read(SIM/'crowding_walk_choices_2026-11-10/selected_candidate.json')
    assert selection['prepared_sha256']=='2b7284d40bab677b2f232e8444c522d3fa88995ac8d42342c9638adb7988ebf2'
    assert sha(SOURCE/'prepared.json.gz')==selection['prepared_sha256']
    assert sha(SIM/'walk_choice_model.py')=='bd645a47900570cd60031196dd298530c1e8f7270cacae0bc0911e249621d141'
    manifest=read(SIM/'public/routing-model/latest.json');assert manifest['model_id']=='261110150729'
    assert manifest['sha256']=='185564956f609a46ef5016ab0c4ee24799bfeecf01da6a4f0f7bc45994ab133c'
    frozen=ROOT/'frozen';frozen.mkdir(exist_ok=True)
    for name,source in [('prepared.json.gz',SOURCE/'prepared.json.gz'),('v9_engine.py',SIM/'walk_choice_model.py'),
                        ('walking_osm.json',SIM/'model_snapshot/app/data/walking_osm.json'),('baseline_verification.json',SOURCE/'independent_verification.json')]:
        dest=frozen/name;assert not dest.exists();shutil.copy2(source,dest)
    sys.path.insert(0,str(SIM))
    import capacity_model as base
    from prepare_city import planned_departures
    bundle=read(frozen/'prepared.json.gz');supply={}
    for scenario in ('regular','peak'):
        supply[scenario]={}
        for rid,info in bundle['prepared']['common']['route_info'].items():
            supply[scenario][rid]=planned_departures(info['plan']) if info.get('city') else base.dispatches(rid,scenario)
    save(frozen/'supply.json',supply)
    files=[SOURCE/'prepared.json.gz',SOURCE/'independent_verification.json',SIM/'walk_choice_model.py',
           SIM/'public/routing-model/latest.json',SIM/'public/routing-model/releases/261110150729.json',SIM/'model_snapshot/app/data/walking_osm.json']
    files += [SOURCE/f'audit-{s}-{d}.json.gz' for s in ('regular','peak') for d in ('mon','tue','wed','thu','fri')]
    files += [SIM/'capacity_model.py',SIM/'prepare_city.py',SIM/'adaptive_capacity_model.py']
    files += [SIM.parent/'app'/name for name in ('prepare_latest_queue.py','prepare_shuttle_queue.py','prepare_city_queue.py','queue_readiness.py','queue_release.py','data/auto_queue_inputs.json')]
    save(target,{'baseline_release':manifest,'prepared_sha256':selection['prepared_sha256'],'engine_sha256':selection['model_sha256'],
                 'protected':[{'path':p.relative_to(SIM) .as_posix() if p.is_relative_to(SIM) else '../'+p.relative_to(SIM.parent).as_posix(),'sha256':sha(p)} for p in files],
                 'frozen':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in frozen.iterdir() if p.is_file()],
                 'supply_speed_capacity_network_fixed':True,'no_production_writes':True})
    experiment={'status':'PREREGISTERED_BEFORE_PILOT','baseline_model_id':manifest['model_id'],
      'calibration_dates':None,'selection_dates':None,'heldout_dates':None,
      'reason':'No sufficiently aligned unused queue/travel truth is currently supplied; old three reports are diagnostic only.',
      'future_split':{'status':'prospective_plan_not_scheduled','calibration':['2026-11-11','2026-11-24'],
                      'selection':['2026-11-25','2026-12-01'],'heldout':['2026-12-02','2026-12-08']},
      'internal_rules':{'maximum_mass_error':1e-5,'capacity_and_fifo_violations':0,'preparation_cancelled_in_ready_inflow':0,
                        'long_wait_minutes':20,'long_wait_action':'report and investigate; no clipping or forced abandonment',
                        'named_queue_reference':40,'queue_reference_is_measured':False},
      'promotion':{'requires_aligned_unused_wait_truth':True,'requires_paired_date_groups':True,
                   'primary_wait_mae_improvement':{'relative':.1,'absolute_minutes':1.,'both_required':True,
                     'reason':'Initial practical threshold: at least a minute and ten percent; must be reconsidered only before any heldout truth is opened if resolution cannot support it.'},
                   'secondary_no_regression':'No observed wait-count, board/alight, total-time metric may worsen; report by stop/route/date. Do not substitute missing truth with internal outcomes.',
                   'uncertainty':'date-clustered differences, not 15-second rows or random seeds as independent real samples',
                   'missing_required_truth':'NOT_EVALUABLE','adequate_truth_but_failed_rules':'DISCARDED',
                   'no_invariant_or_operational_regression':True},
      'pilot_cases':[
        {'case':'control-regular-fri','mode':'control','day':'금','scenario':'regular','seed':0},
        {'case':'physics-regular-mon','mode':'physics','day':'월','scenario':'regular','seed':0},
        {'case':'behavior-regular-mon','mode':'behavior','day':'월','scenario':'regular','seed':0},
        {'case':'combined-regular-mon','mode':'combined','day':'월','scenario':'regular','seed':0},
        {'case':'combined-regular-fri','mode':'combined','day':'금','scenario':'regular','seed':0},
        {'case':'combined-peak-mon','mode':'combined','day':'월','scenario':'peak','seed':0},
        {'case':'combined-regular-mon-seed1','mode':'combined','day':'월','scenario':'regular','seed':1},
        {'case':'combined-regular-mon-seed2','mode':'combined','day':'월','scenario':'regular','seed':2},
        {'case':'fare-scenario-regular-mon','mode':'fare_scenario','day':'월','scenario':'regular','seed':0}],
      'randomness':'Frozen v9 random input is retained. Named new-agent streams are matched across prototype variants; v9 has no identical counterparts to newly introduced tastes/hazard draws.',
      'no_parameter_search_against_old_three_reports':True,'full_week_expansion':'After a usable empirical validation target is available; no claim of full-week coverage from this finite pilot.'}
    save(ROOT/'experiment_lock.json',experiment)
    print('Frozen v9, supplies, protected inputs; nine offline cases pre-registered')

if __name__=='__main__':main()
