from pathlib import Path
import sys,copy,shutil
HERE=Path(__file__).resolve().parent;SIM=HERE.parent
sys.path.insert(0,str(SIM))
import capacity_model as base
from prepare_walk_choices import read

SOURCE=SIM/'capacity44_correction_2026-11-10'
EVIDENCE=SIM.parent/'field_observations_2026-11-10/peak_pair_operation_evidence.json'

def prepare():
    path=HERE/'prepared.json.gz'
    if path.exists():return read(path)
    bundle=read(SOURCE/'prepared.json.gz');old=copy.deepcopy(bundle['prepared']['common']['route_info'])
    info=bundle['prepared']['common']['route_info']['shuttle-41841']
    info['capacity_periods']=[{'start_second':75600,'capacity':60}]
    info['dispatch_batches']=[{'start_second':54000,'end_second':68400,'vehicles':2}]
    meta={'schema':'peak_pair_operation_scenario_v1','route_id':'shuttle-41841','vehicles_per_peak_dispatch':2,
          'capacity_each_peak_vehicle':44,'start_second':54000,'end_second':68400,
          'window_is_assumed_existing_peak_window_not_measured':True,
          'cadence_is_preserved_regular4_peak3_plan_not_measured_exact_repetition':True,
          'evidence':'user repeated experience and reported common testimony; not independently timestamped repeated batches',
          'evidence_sha256':base.sha(EVIDENCE),'source_prepared_sha256':base.sha(SOURCE/'prepared.json.gz'),
          'not_single_88_seat_vehicle':True,'not_uniform_90_second_dispatches':True,
          'only_dispatch_multiplicity_changed_from_capacity44':True,'independent_empirical_validation':False}
    common=bundle['prepared']['common'];common['peak_pair_operation']=meta;common['data_version']=11
    bundle['peak_pair_operation']=meta
    common['queue_note']='변경 횟수 상한 없음. 주간 행정관 설입44명/차·가정한15~19피크창에2대묶음. 정확한묶음주기/피크경계는미확인. 야간60명은기존미확인가정.'
    assert bundle['prepared']['plans']==read(SOURCE/'prepared.json.gz')['prepared']['plans']
    for rid in old:
        if rid!='shuttle-41841':assert common['route_info'][rid]==old[rid]
    base.packed(path,bundle)
    source=(SOURCE/'engine.py').read_text(encoding='utf8')
    source=source.replace('from capacity_policy import capacity_at_clock','from capacity_policy import capacity_at_clock,batch_size_at_clock',1)
    a='        for clock in clocks:';assert a in source
    source=source.replace(a,"        clocks=[clock for clock in clocks for _ in range(batch_size_at_clock(info,clock))]\n"+a,1)
    (HERE/'engine.py').write_text(source,encoding='utf8')
    base.save(HERE/'preparation_verification.json',{'status':'PASS','operation':meta,'same_student_plans':True,
        'capacity_semantics_same_as_capacity44_baseline':True,'engine_sha256':base.sha(HERE/'engine.py'),
        'capacity_policy_sha256':base.sha(HERE/'capacity_policy.py')})
    return bundle

if __name__=='__main__':prepare();print('Prepared separate two-vehicle peak-batch scenario')
