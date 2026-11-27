"""Run the V11-based 44-passenger R candidate with a 15:00–16:00 departure peak."""
import argparse
import math
import os
from pathlib import Path
import sys
sys.dont_write_bytecode=True

HERE = Path(__file__).resolve().parent
PROFILE = HERE.parent/'261124094834'
sys.path.insert(0,str(PROFILE))
from departure import class_events
from peak_departure import apply_departures, MAX_CHANGE
from population import DAILY_TRIP_LIMIT, cap_daily_departures, check_result
PARENT = HERE.parent/'261123191229'
sys.path.insert(0,str(PARENT))
from candidate import apply_choice, base, engine, load, load_v11, SIM
from validate import validate

MODEL = 'R261124100719'
WALK_SHARE = .60
CAPACITY_SOURCE = HERE.parent/'field_observations_2026-11-24/daehak_capacity.json'
COURSES = HERE.parent/'scenario_comparison_2026-11-07/simulation_outputs/input_snapshot/course_endings_current.json'

def configure(common):
    route = common['route_info']['shuttle-daehak']
    if route.get('capacity_periods'):
        raise ValueError('Review university shuttle capacity overrides')
    route['capacity'] = 44
    common['daehak_capacity'] = load(CAPACITY_SOURCE)
    common['initial_home_walk'] = dict(target_share_of_direct_daehak_shuttle_group=WALK_SHARE,
        applies_to_destination='daehak', walk_label='도보 (개인형 이동장치 포함)',
        personal_mobility_proxy='Both use the preserved V11 walking path and walking time',
        evidence='User qualitative experience; shares and personal mobility supply not measured')
    common['candidate_id'] = MODEL
    common['departure_model'] = dict(time_field='class_end_minute', peak_inclusive=[900,960],
        nominal_max_absolute_change=MAX_CHANGE, uncapped_weekday_enrollment_weighted_mean=.5,
        daily_homebound_trip_limit=DAILY_TRIP_LIMIT,
        meaning='Probability of the immediate homebound trip after this class event')
    common['source_note'] = '수강인원 기반 모의 이동. 수업 종료 시각별 하교확률(15~16시 최고, 기존 R의 시간대 간 차이를 3배로 확대), 대학동 승객 정원 44명. 대학동행 도보 분류에는 개인형 이동장치를 포함하며 거리와 소요시간은 도보로 근사.'

def common_file():
    common=load(PARENT/'common.json.gz')
    configure(common)
    base.packed(HERE/'common.json.gz',common)

def run(day, service, new_attempt=False):
    case=f'{service}-{base.DAYS[day]}'
    location=HERE/'runs'/case
    location.mkdir(parents=True,exist_ok=True)
    done=sorted(location.glob('attempt-*/result.json'))
    if done:
        result=load(done[-1])
        assert result['model_id']==MODEL and result['status']=='verified'
        result['trip_limit_check']=check_result(result)
        return result
    attempts=sorted(location.glob('attempt-*'))
    if attempts and not new_attempt:
        raise RuntimeError(f'Case has an existing attempt. Inspect {location} before --new-attempt.')
    output=location/f'attempt-{len(attempts)+1:02}'
    output.mkdir()
    b=load_v11()
    configure(b['prepared']['common'])
    changed, original_choice=apply_choice(b,load(PARENT/'walk_catalog.json'),day,WALK_SHARE)
    profile=apply_departures(b,class_events(load(COURSES)),day,changed)
    cap_daily_departures(b,day,profile,changed)
    base.save(output/'departure_profile.json',profile)
    plans=b['prepared']['plans'][day]
    daehak=[p for p in plans if b['destination_keys'][str(p[0])]=='daehak']
    daehak_mass=math.fsum(p[3] for p in daehak)
    remaining=math.fsum(p[3] for p in daehak if p[6] and p[6][0]['rid']=='shuttle-daehak' and p[6][0]['board']==0)
    moved=math.fsum(row[0] for row in changed.values())
    direct_walk=math.fsum(p[3] for p in daehak if not p[6])
    selection=dict(target=WALK_SHARE,eligible_mass=remaining+moved,converted_mass=moved,
                   realized_fraction=moved/(remaining+moved),destination_mass=daehak_mass,
                   first_daehak_shuttle_fraction=remaining/daehak_mass,walk_only_fraction=direct_walk/daehak_mass)
    base.save(output/'case.json',dict(model_id=MODEL,case=case,day=day,service=service,
        route_capacity=load(CAPACITY_SOURCE),selection=selection,flat_selection=original_choice,
        sha256={str(f.name):base.sha(f) for f in [Path(__file__),HERE/'peak_departure.py',PROFILE/'departure.py',PROFILE/'population.py',Path(engine.__file__),
         PARENT/'candidate.py',PARENT/'validate.py',PARENT/'walk_catalog.json',CAPACITY_SOURCE,COURSES]}))
    engine.WORK=engine.OUT=base.OUT=output
    engine.simulate(b,day,service)
    result=validate(b,output,day,service,changed)
    assert result['candidate']['capacity']==44 and result['invariants']['capacity_violations']==0
    assert math.isclose(profile['total_trip_mass'],result['invariants']['final_weight'],abs_tol=1e-6)
    result['trip_limit_check']=check_result(result)
    result.update(model_id=MODEL,case=case,selection=selection,capacity=44)
    base.save(output/'result.tmp',result)
    os.replace(output/'result.tmp',output/'result.json')
    return result

if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--common',action='store_true')
    cli.add_argument('--day',choices=base.DAYS,default='월')
    cli.add_argument('--service',choices=['regular','peak'],default='regular')
    cli.add_argument('--new-attempt',action='store_true')
    args=cli.parse_args()
    if args.common:
        common_file()
    else:
        result=run(args.day,args.service,args.new_attempt)
        print(MODEL,result['case'],result['status'],result['candidate'],flush=True)
