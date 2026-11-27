"""Map all candidate walking legs, excluding rides, to a terrain surface length."""
import math
from pathlib import Path
import sys

from terrain import HERE, slope_profile

PREVIOUS=HERE.parent/'261124102753'
sys.path.insert(0,str(PREVIOUS))
import model as previous


def stages_in(stages):
    for stage in stages:
        yield stage
        yield from stages_in(stage.get('pool',()))
        yield from stages_in(stage.get('continuation_stages',()))


def walk_ids():
    b=previous.reference.load_v11()
    c=previous.load(PREVIOUS/'viewer-data/common.json.gz')
    ids=set()
    def plan(p):
        ids.add(p[5][0]); stages(p[6])
    def stages(items):
        ids.update(stage['next_walk'][0] for stage in stages_in(items))
    def options(items):
        for row in items:
            ids.add(row['walk'][0]); stages(row['stages'])
    for plans in b['prepared']['plans'].values():
        for p in plans: plan(p)
    for opts in b['alternatives'].values(): options(opts)
    for items in b['compatible_single_stage_pools'].values(): stages(items)
    for items in b['compatible_route_policies'].values(): stages(items)
    for f in (previous.INPUTS).glob('*.json.gz'):
        patch=previous.load(f)
        for row in patch['replacements']: plan(row['plan'])
        for opts in patch['alternatives'].values(): options(opts)
    for file in [previous.reference.PARENT/'walk_catalog.json',previous.REFERENCE/'dorm_paths.json.gz']:
        ids.update(r['path'] for r in previous.load(file)['routes'])
    return c['paths'],sorted(ids)


def tile_keys(paths,ids):
    pairs=set()
    for pid in ids:
        for lat,lon in paths[pid]:
            x=(lon+180)/360*(2**14)*256-.5
            y=(1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*(2**14)*256-.5
            for i in (math.floor(x),math.floor(x)+1):
                for j in (math.floor(y),math.floor(y)+1):
                    pairs.add((i//256,j//256))
    return sorted(pairs)


def build():
    paths,ids=walk_ids()
    keys=tile_keys(paths,ids)
    absent=[(x,y) for x,y in keys if not (HERE/'terrain'/f'{x}-{y}.png').is_file()]
    if absent:
        raise ValueError(f'Missing elevation tiles {absent}')
    profiles={}
    for idx in ids:
        flat,surface,rise,fall=slope_profile(paths[idx])
        profiles[str(idx)]=dict(flat=flat,surface=surface,rise=rise,fall=fall,
                                factor=surface/flat if flat>1e-5 else 1.)
    previous.PACK(HERE/'walking_surface.json.gz',profiles)
    print('walking paths with terrain:',len(profiles),'tiles:',keys)


if __name__=='__main__':
    if '--tiles' in sys.argv:
        paths,ids=walk_ids()
        for x,y in tile_keys(paths,ids): print(f'{x}-{y}')
    else:
        build()
