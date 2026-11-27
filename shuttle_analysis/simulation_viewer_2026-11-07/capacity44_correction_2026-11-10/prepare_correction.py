"""Capacity-only branch of v9: original H files and coefficients stay frozen."""
from pathlib import Path
import sys,copy,json,shutil
HERE=Path(__file__).resolve().parent;SIM=HERE.parent
sys.path.insert(0,str(SIM))
import capacity_model as base
from prepare_walk_choices import read

SOURCE=SIM/'crowding_walk_choices_2026-11-10/initial_refit_H'
OBS=SIM.parent/'field_observations_2026-11-10'

def prepare():
    path=HERE/'prepared.json.gz'
    if path.exists():return read(path)
    bundle=read(SOURCE/'prepared.json.gz');before=copy.deepcopy(bundle['prepared']['common']['route_info'])
    correction=read(OBS/'shuttle_capacity_correction.json');assert correction['preferred_max_passengers']==44
    info=bundle['prepared']['common']['route_info']['shuttle-41841']
    info['capacity']=44
    info['capacity_periods']=[{'start_second':21*3600,'end_second':48*3600,'capacity':60,
       'source':'legacy library-night paired-service assumption; not independently verified; daytime report does not establish night fleet capacity'}]
    expected=copy.deepcopy(before);expected['shuttle-41841']=copy.deepcopy(info)
    assert bundle['prepared']['common']['route_info']==expected
    assert bundle['prepared']['plans']==read(SOURCE/'prepared.json.gz')['prepared']['plans']
    meta={'schema':'route_specific_capacity_correction_v1','route_id':'shuttle-41841','daytime_max_passengers':44,
          'daytime_end_second':21*3600,'night_paired_assumption_max_passengers':60,'source':'latest user report; vehicle registration not independently checked',
          'source_observation_id':correction['source_observation_id'],'source_sha256':base.sha(OBS/'shuttle_capacity_correction.json'),
          'parent_dataset':'capacity_v9','parent_model_id':'261110150729','parent_prepared_sha256':base.sha(SOURCE/'prepared.json.gz'),
          'only_capacity_input_changed':True,'behavior_demand_speed_supply_geometry_unchanged':True,
          'other_shuttle_capacities_unchanged':True,'independent_empirical_validation':False}
    bundle['capacity_correction']=meta;common=bundle['prepared']['common'];common['capacity_correction']=meta;common['data_version']=10
    common['queue_note']='변경 횟수 상한 없음. 설입 행정관 통학셔틀 주간44명으로 정정. 도서관야간 그룹60명은 기존 미확인 가정 유지. 20분은 검토 기준.'
    base.packed(path,bundle)
    source=(SOURCE.parent.parent/'walk_choice_model.py').read_text(encoding='utf8')
    source=source.replace('import capacity_model as base','import capacity_model as base\nfrom capacity_policy import capacity_at_clock',1)
    old="'cap':info.get('capacity',25 if rid=='shuttle-41914' else 60)"
    new="'cap':capacity_at_clock({**info,'capacity':info.get('capacity',25 if rid=='shuttle-41914' else 60)},clock)"
    assert old in source;source=source.replace(old,new,1)
    old="capacity=min(ri[s['rid']].get('capacity',25 if s['rid']=='shuttle-41914' else 60) for s in stage.get('pool',[stage]))"
    new="capacity=min(capacity_at_clock({**ri[s['rid']],'capacity':ri[s['rid']].get('capacity',25 if s['rid']=='shuttle-41914' else 60)},t) for s in stage.get('pool',[stage]))"
    assert old in source;source=source.replace(old,new,1)
    (HERE/'engine.py').write_text(source,encoding='utf8')
    base.save(HERE/'preparation_verification.json',{'status':'PASS','correction':meta,'changed_route_info_keys':['shuttle-41841.capacity','shuttle-41841.capacity_periods'],
                  'same_student_plans':True,'engine_sha256':base.sha(HERE/'engine.py'),'capacity_policy_sha256':base.sha(HERE/'capacity_policy.py')})
    return bundle

if __name__=='__main__':prepare();print('Prepared separate capacity44 branch without changing the original engine')
