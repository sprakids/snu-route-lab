"""Run the demand-only grade experiment on the five weekdays and both timetables."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import contextlib
import math
import os
import shutil
import sys
sys.dont_write_bytecode=True

from grade_demand import HERE, MODEL, REFERENCE, build_profiles, bundle, ref, multiplier
import demand_engine
from run_integrated import audit_case

DATA=HERE/'viewer-data'
CASES=[(d,s) for d in ('목','월','화','수','금') for s in ('regular','peak')]


def prepare():
    build_profiles()
    common=ref.load(ref.DATA/'common.json.gz')
    common['candidate_id']=common['data_version']=MODEL
    common['terrain_model'].pop('upper_dorms',None)
    common['terrain_model']={**common['terrain_model'],'perception':'signed piecewise segment weights in demand choice only',
        'scope':'all modeled walking paths','grade_percent_to_factor':{str(g):multiplier(g/100) for g in (-20,-10,0,10,20)}}
    common['dorm_choice']['distance_unit']='grade-weighted perceived metres'
    common['initial_home_walk']['target_applies_to']='reference distance curve before the grade adjustment'
    common['source_note']=common['source_note'].replace('보행거리·시간에 지형 고도차를 반영하고 윗공대 기숙사행의 내리막 선호를 추가.',
        '실제 보행시간은 지형 표면거리로 계산하며, 수요 선택에는 오르막·내리막 구간별 체감거리를 사용한다.')
    DATA.mkdir(exist_ok=True)
    staged=DATA/'common.tmp'
    ref.previous.PACK(staged,common)
    os.replace(staged,DATA/'common.json.gz')


def run_case(case):
    day,service=case
    key=f'{service}-{ref.DAYS[day]}'
    folder=HERE/'runs'/key
    folder.mkdir(parents=True,exist_ok=True)
    old=sorted(folder.glob('attempt-*/result.json'))
    if old:
        result=ref.load(old[-1])
        if result['model']!=MODEL or result['status']!='verified':
            raise ValueError(old[-1])
        return key
    out=folder/'attempt-01'
    out.mkdir()
    with (out/'run.log').open('w',encoding='utf8') as log,contextlib.redirect_stdout(log):
        b,patch,donors,choices=bundle(day,service)
        demand_engine.WORK=demand_engine.OUT=ref.ref.base.OUT=out
        demand_engine.simulate(b,day,service)
        result=audit_case(b,day,service,out,patch,donors,True)
        baseline=ref.load(sorted((REFERENCE/'runs'/key).glob('attempt-*/result.json'))[-1])
        assert baseline['weekday_demand']==result['weekday_demand']
        assert all(math.isclose(r['total'],baseline['initial'][d]['total'],abs_tol=1e-6) for d,r in result['initial'].items())
        locations={p[0]:p[1] for p in b['prepared']['plans'][day]}
        destinations=b['destination_keys']
        completed=Counter()
        no_vehicle=0.
        for r in ref.load(out/f'audit-{key}.json.gz')['legs']:
            d=destinations[str(r['id'])]
            if r['unserved']:
                continue
            walk=all(s[0]!=3 for s in r['legs'])
            if d.startswith('dorm_') and locations[r['id']] in ('300','301','302'):
                completed['total']+=r['weight']
                completed['walk']+=r['weight']*walk
            no_vehicle+=r['weight']*walk
        result.update(model=MODEL,reference=ref.MODEL,selection=choices,upper_dorm=completed,completed_no_vehicle=no_vehicle)
        staged=DATA/(key+'.tmp')
        shutil.copyfile(out/(key+'.json.gz'),staged)
        os.replace(staged,DATA/(key+'.json.gz'))
        ref.previous.SAVE(out/'result.tmp',result)
        os.replace(out/'result.tmp',out/'result.json')
    return key


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--day',choices=ref.DAYS,default='목')
    parser.add_argument('--service',choices=['regular','peak'],default='regular')
    parser.add_argument('--all',action='store_true')
    args=parser.parse_args()
    if args.prepare:
        prepare()
    elif args.all:
        with ProcessPoolExecutor(max_workers=3) as pool:
            for case in pool.map(run_case,CASES):
                print('verified',case,flush=True)
    else:
        print('verified',run_case((args.day,args.service)))
