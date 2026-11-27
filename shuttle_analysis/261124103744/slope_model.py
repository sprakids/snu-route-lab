"""Apply surface distance to walking legs and descent preference to upper-campus dorm trips."""
import hashlib
import math
from pathlib import Path
import shutil

from walk_metrics import HERE, PREVIOUS, previous, stages_in
from terrain import UPPER

MODEL='R261124103744'
DATA=HERE/'viewer-data'
INPUTS=HERE/'inputs'
load=previous.load
ref=previous.reference
DEST=previous.DEST
DAYS=previous.DAYS


def prepare():
    surfaces=load(HERE/'walking_surface.json.gz')
    common=load(PREVIOUS/'viewer-data/common.json.gz')
    common['candidate_id']=common['data_version']=MODEL
    common['terrain_model']=dict(source='Mapzen Terrain Tiles',sampling_max_step_m=25,walking_paths=len(surfaces),
        physical='sum of hypot(horizontal leg, elevation change)',upper_dorms=sorted(UPPER),
        perception='surface distance / (1 + positive net downhill grade / .05); upper dorm trips only')
    common['source_note']+=' 보행거리·시간에 지형 고도차를 반영하고 윗공대 기숙사행의 내리막 선호를 추가.'
    DATA.mkdir(exist_ok=True);INPUTS.mkdir(exist_ok=True)
    previous.PACK(DATA/'common.json.gz',common)
    for did in DAYS.values():
        patch=load(previous.INPUTS/f'{did}.json.gz')
        patch['model']=MODEL
        patch['assignment_source']=previous.MODEL
        previous.PACK(INPUTS/f'{did}.json.gz',patch)
    shutil.copyfile(previous.INPUTS/'weekday_targets.json',INPUTS/'weekday_targets.json')


def revise_dorms(b,day,metrics,terrain):
    catalog=load(previous.REFERENCE/'dorm_paths.json.gz')
    routes={(tuple(r['origin']),r['dorm']):r for r in catalog['routes']}
    original=ref.load_v11()['prepared']['plans'][day]
    source={p[0]:p for p in original if p[2]=='dorm'}
    paths=b['prepared']['common']['paths']
    plans=b['prepared']['plans'][day]
    upper_stats={}
    for i,p in enumerate(plans):
        dest=b['destination_keys'][str(p[0])]
        if dest not in ('dorm_ug','dorm_grad'):
            continue
        uid=p[0]
        orig=source[uid]
        if not orig[6]:
            continue
        route=routes.get((tuple(paths[orig[5][0]][0]),dest))
        if not route:
            continue
        profile=metrics[str(route['path'])]
        key=(p[1],dest)
        meters=terrain[key]['choice_m'] if key in terrain else profile['surface']
        prob=previous.dorm_distance.probability(meters)
        draw=int.from_bytes(hashlib.sha256(f'dorm-walk-v1/{uid}'.encode()).digest()[:8],'big')/2**64
        direct=draw<prob
        if key in terrain:
            row=upper_stats.setdefault('|'.join(key),dict(total=0.,old_direct=0.,new_direct=0.,probability=prob))
            row['total']+=p[3]
            row['old_direct']+=p[3]*int(not p[6])
            row['new_direct']+=p[3]*int(direct)
        if direct:
            plans[i]=[*p[:5],[route['path'],route['seconds']*b['walk_scales'][str(uid)]],[]]
        else:
            plans[i]=[*p[:5],orig[5],orig[6]]
    return upper_stats


def bundle(day,with_rail):
    b,patch,donors=previous.integrated_bundle(day,with_rail)
    metrics=load(HERE/'walking_surface.json.gz')
    terrain={(r['building'],r['dorm']):r for r in load(HERE/'terrain.json')['rows'] if 'path' in r}
    upper=revise_dorms(b,day,metrics,terrain)
    seen=set()
    def adjust_stages(items):
        for st in stages_in(items):
            if id(st) not in seen:
                seen.add(id(st))
                pid,sec=st['next_walk']
                st['next_walk']=[pid,sec*metrics[str(pid)]['factor']]
    plans=b['prepared']['plans'][day]
    for i,p in enumerate(plans):
        pid,sec=p[5]
        plans[i]=[*p[:5],[pid,sec*metrics[str(pid)]['factor']],p[6]]
        adjust_stages(p[6])
    for options in b['alternatives'].values():
        for o in options:
            pid,sec=o['walk'];profile=metrics[str(pid)]
            o['walk']=[pid,sec*profile['factor']]
            if profile['flat']>1e-5:
                o['walk_meters']=profile['surface']
            adjust_stages(o['stages'])
    for kind in ('compatible_single_stage_pools','compatible_route_policies'):
        for items in b[kind].values():
            adjust_stages(items)
    assert math.isclose(math.fsum(p[3] for p in plans),b['prepared']['expected'][day],abs_tol=1e-6)
    return b,patch,donors,upper
