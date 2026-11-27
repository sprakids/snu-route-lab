"""Build comparison and research-map statistics using existing verified simulation ledgers."""
import math
import sys
import time

from grade_demand import HERE, MODEL, REFERENCE, PROFILE, multiplier, ref
sys.path.insert(0,str(REFERENCE/'local-map'))
import build_stats as maps


def first_walks(ledger):
    samples={}
    for row in ledger['legs']:
        legs=row['legs']
        if legs and legs[0][0]==0:
            leg=legs[0]
            key=(row['id'],leg[3])
            samples.setdefault(key,set()).add(round(leg[2]-leg[1],5))
    return samples


def main(wait=False):
    assert [multiplier(g) for g in (-.4,-.1,0,.1,.4)]==[.5,.75,1.,2.,3.]
    maps.PREVIOUS=REFERENCE
    maps.VERSION=MODEL
    base=ref.ref.load_v11()['prepared']['plans']
    upper={day:{p[0] for p in plans if p[1] in ('300','301','302') and p[2]=='dorm'} for day,plans in base.items()}
    dest={day:{p[0]:p[2] for p in plans} for day,plans in base.items()}
    del base
    common=ref.load(HERE/'viewer-data/common.json.gz')
    before=ref.load(ref.DATA/'common.json.gz')
    for key in ('paths','route_info','nodes','destinations','motion_profiles'):
        assert common[key]==before[key]
    profiles=ref.load(PROFILE)
    physical=ref.load(REFERENCE/'walking_surface.json.gz')
    assert profiles.keys()==physical.keys()
    examples=[]
    for row in ref.load(REFERENCE/'terrain.json')['rows']:
        if 'path' in row:
            dist=profiles[str(row['path'])]
            examples.append(dict(building=row['building'],dorm=row['dorm'],previous_choice_m=row['choice_m'],
                ascent_m=row['ascent_m'],descent_m=row['descent_m'],physical_seconds=row['revised_seconds'],**dist))
    runs={};halves={};records=[]
    for service in ('regular','peak'):
        runs[service]={};halves[service]={}
        for day,did in ref.DAYS.items():
            key=f'{service}-{did}'
            results=sorted((HERE/'runs'/key).glob('attempt-*/result.json'))
            while wait and not results:
                time.sleep(4)
                results=sorted((HERE/'runs'/key).glob('attempt-*/result.json'))
            if not results:
                raise FileNotFoundError(f'Missing verified run: {key}')
            current=results[-1]
            previous=sorted((REFERENCE/'runs'/key).glob('attempt-*/result.json'))[-1]
            a=ref.load(current);v=ref.load(previous)
            assert a['status']==v['status']=='verified' and a['model']==MODEL
            name=f'audit-{key}.json.gz'
            patch=ref.load(ref.INPUTS/f'{did}.json.gz')
            assert patch['model']==ref.MODEL
            halves[service][did],counts,_=maps.case(current.parent/name,HERE/'viewer-data'/f'{key}.json.gz',
                dest[day],upper[day],{**patch,'model':MODEL},common,did,service)
            runs[service][did]=counts
            old_times=first_walks(ref.load(previous.parent/name))
            new_times=first_walks(ref.load(current.parent/name))
            shared=old_times.keys() & new_times.keys()
            same=sum(bool(new_times[k] & old_times[k]) for k in shared)
            assert same==len(shared)>0,(key,'physical walking duration mismatch',len(shared)-same)
            assert a['identical_supply_events']==v['identical_supply_events']
            records.append(dict(day=day,service=service,total=a['weekday_demand'],before=a['selection']['reference_initial_walk'],
                after=a['selection']['candidate_initial_walk'],completed_walk=a['completed_no_vehicle'],
                old_completed_walk=sum(g.get('walk',0.) for g in v['completed'].values()),
                route_changes_at_origin=a['selection']['initial_route_changes_after_home_choice'],
                destinations={d:{'total':g['total'],'initial_walk':g.get('walk',0.),'old_initial_walk':v['initial'][d].get('walk',0.),
                                 'completed_walk':a['completed'][d].get('walk',0.),'old_completed_walk':v['completed'][d].get('walk',0.)} for d,g in a['initial'].items()},
                upper_dorm=counts['upper_dorm'],rail=a['rail_target'],unserved=a['unserved'],capacity_violations=a['capacity_violations'],
                max_wait_min=a['max_continuous_wait'],over20_weight=a['over20_weight'],
                shared_first_walk_paths= len(shared),matched_first_walk_durations=same))
    maps.publish(HERE/'map-stats.json.gz',dict(interval_seconds=1800,scenarios=halves,runs=runs))
    ref.previous.SAVE(HERE/'comparison.json',dict(model=MODEL,reference=ref.MODEL,paths=len(profiles),
        grade_percent_to_factor=common['terrain_model']['grade_percent_to_factor'],upper_examples=examples,cases=records))


if __name__=='__main__':
    main('--wait' in sys.argv)
