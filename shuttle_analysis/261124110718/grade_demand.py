"""Directional, perceived walking distance. Only the demand simulation imports this module."""
from collections import Counter, defaultdict
from bisect import bisect_left
from copy import deepcopy
from functools import lru_cache
import hashlib
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REFERENCE = HERE.parent / '261124103744'
sys.path.insert(0,str(REFERENCE))
import slope_model as ref
from terrain import elevation, horizontal
import candidate

MODEL = 'R' + HERE.name
UP_AT_TEN, DOWN_AT_TEN = 2., .75
MIN_FACTOR, MAX_FACTOR = .5, 3.
STEP = 25.
PROFILE = HERE / 'choice_distance.json.gz'


def multiplier(grade):
    slope = (UP_AT_TEN-1.)/.10 if grade >= 0 else (1.-DOWN_AT_TEN)/.10
    return min(MAX_FACTOR,max(MIN_FACTOR,1.+slope*grade))


@lru_cache(maxsize=100000)
def segment(a,b):
    length=horizontal(a,b)
    if length<1e-6:
        return 0.,0.
    pieces=math.ceil(length/STEP)
    dx=length/pieces
    z=elevation(*a)
    physical=perceived=0.
    for i in range(1,pieces+1):
        f=i/pieces
        next_z=elevation(a[0]+f*(b[0]-a[0]),a[1]+f*(b[1]-a[1]))
        dz=next_z-z
        ds=math.hypot(dx,dz)
        physical+=ds
        perceived+=ds*multiplier(dz/dx)
        z=next_z
    return physical,perceived


def build_profiles():
    paths=ref.load(ref.DATA/'common.json.gz')['paths']
    physics=ref.load(REFERENCE/'walking_surface.json.gz')
    costs={}
    for key,old in physics.items():
        poly=paths[int(key)]
        pieces=[segment(tuple(a),tuple(b)) for a,b in zip(poly,poly[1:])]
        physical=sum(x for x,_ in pieces)
        assert math.isclose(physical,old['surface'],abs_tol=.001)
        felt=sum(x for _,x in pieces)
        assert MIN_FACTOR*physical-.001<=felt<=MAX_FACTOR*physical+.001
        costs[key]=dict(physical_m=physical,perceived_m=felt)
    staged=PROFILE.with_suffix('.tmp')
    ref.previous.PACK(staged,costs)
    staged.replace(PROFILE)


def draw(seed):
    return int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8],'big')/2**64


def restore_physical_stages(stages,physics):
    restored=deepcopy(stages)
    seen=set()
    for st in ref.stages_in(restored):
        if id(st) in seen:
            continue
        seen.add(id(st))
        pid,sec=st['next_walk']
        st['next_walk']=[pid,sec*physics[str(pid)]['factor']]
    return restored


def select_home_walk(b,day,profiles,physics):
    """Reuse the existing home-choice curves and random draws, replacing their distance input."""
    raw=ref.ref.load_v11()
    originals=raw['prepared']['plans'][day]
    by_id={p[0]:p for p in originals}
    paths=b['prepared']['common']['paths']
    def catalog(name):
        return ref.load(name)['routes']
    dorm={(tuple(r['origin']),r['dorm']):r for r in catalog(ref.previous.REFERENCE/'dorm_paths.json.gz')}
    town={tuple(r['origin']):r for r in catalog(ref.ref.PARENT/'walk_catalog.json')}
    weights=Counter()
    for p in originals:
        if candidate.eligible(p,raw):
            origin=tuple(paths[p[5][0]][0])
            weights[town[origin]['meters']]+=p[3]
    base_probs=candidate.target_probabilities(weights,ref.ref.WALK_SHARE)
    plans=b['prepared']['plans'][day]
    for i,p in enumerate(plans):
        uid=p[0]
        dest=b['destination_keys'][str(uid)]
        original=by_id.get(uid)
        if original is None or not original[6]:
            continue
        origin=tuple(paths[original[5][0]][0])
        if dest in ('dorm_ug','dorm_grad') and (origin,dest) in dorm:
            route=dorm[origin,dest]
            prob=ref.previous.dorm_distance.probability(profiles[str(route['path'])]['perceived_m'])
            seed=f'dorm-walk-v1/{uid}'
        elif dest=='daehak' and candidate.eligible(original,raw):
            route=town[origin]
            meters=route['meters']
            p0=base_probs[meters]
            # Keep the original reference intercept. Only walking-distance disutility changes.
            new_m=profiles[str(route['path'])]['perceived_m']
            log_odds=math.log(p0/(1-p0))+(max(0,meters-500)-max(0,new_m-500))/1000
            prob=1/(1+math.exp(-log_odds))
            seed=f'{candidate.MODEL_ID}/first-walk/{uid}'
        else:
            continue
        if draw(seed)<prob:
            pid=route['path']
            walk=[pid,route['seconds']*b['walk_scales'][str(uid)]*physics[str(pid)]['factor']]
            plans[i]=[*p[:5],walk,[]]
        elif not p[6]:
            pid,sec=original[5]
            plans[i]=[*p[:5],[pid,sec*physics[str(pid)]['factor']],restore_physical_stages(original[6],physics)]


def tilt_origin_choices(b,day,profiles,service):
    """Adjust the existing initial route mix, keeping each person's supply and timing constraints."""
    plans=b['prepared']['plans'][day]
    factors=b['walk_scales']
    common=b['prepared']['common']
    groups=defaultdict(lambda:defaultdict(list))
    # Preserve the explicit destination-specific walk/vehicle decision above.
    for i,p in enumerate(plans):
        uid,building,_,_,start,access,stages=p
        dest=b['destination_keys'][str(uid)]
        key=(building,tuple(common['paths'][access[0]][0]),dest,int(start//1800),
             bool(stages) if dest in ('daehak','dorm_grad','dorm_ug') else None)
        pattern=(access[0],tuple((s['rid'],s['board'],s['alight'],s['next_walk'][0]) for s in stages))
        groups[key][pattern].append(i)
    ri=common['route_info']
    @lru_cache(maxsize=None)
    def departures(rid,board):
        r=ri[rid]
        clocks=ref.ref.engine.planned_departures(r['plan']) if r.get('city') else ref.ref.base.dispatches(rid,service)
        offset=r.get('origin_to_modeled_first_stop_seconds',0.)+r['offsets'][board]-r['offsets'][r['anchor']]
        return sorted(t+offset for t in clocks if t+offset<=ref.ref.engine.END)
    def available(p,template,ratio):
        t=p[4]+template[5][1]*ratio
        for s in template[6]:
            rows=departures(s['rid'],s['board'])
            index=bisect_left(rows,t+20)
            if index==len(rows):
                return False
            r=ri[s['rid']]
            t=rows[index]+r['offsets'][s['alight']]-r['offsets'][s['board']]+s['next_walk'][1]*ratio
        return t<=ref.ref.engine.END
    changes=0
    for patterns in groups.values():
        if len(patterns)<2:
            continue
        mass={k:sum(plans[i][3] for i in indexes) for k,indexes in patterns.items()}
        def extra(k):
            legs=[k[0],*[s[3] for s in k[1]]]
            return sum(profiles[str(pid)]['perceived_m']-profiles[str(pid)]['physical_m'] for pid in legs)
        raw={k:w*math.exp(-extra(k)/1000) for k,w in mass.items()}
        scale=sum(mass.values())/sum(raw.values())
        diff={k:raw[k]*scale-m for k,m in mass.items()}
        gain=[(k,d,plans[patterns[k][0]]) for k,d in diff.items() if d>1e-9]
        if not gain:
            continue
        for key,indices in patterns.items():
            if diff[key]>=-1e-9:
                continue
            for i in indices:
                p=plans[i]
                if draw(f'grade-leave/{p[0]}')>=-diff[key]/mass[key]:
                    continue
                # A previously modeled alternative with the same origin/destination must
                # have an actual scheduled connection left for this departure and walk speed.
                options=[]
                for _,weight,template in gain:
                    ratio=factors[str(p[0])]/factors[str(template[0])]
                    if available(p,template,ratio):
                        options.append((weight,template,ratio))
                if not options:
                    continue
                ticket=draw(f'grade-enter/{p[0]}')*sum(x[0] for x in options)
                for weight,template,ratio in options:
                    ticket-=weight
                    if ticket<=0:
                        break
                pid,sec=template[5]
                plans[i]=[*p[:5],[pid,sec*ratio],ref.ref.engine.scaled_stages(template[6],ratio)]
                changes+=1
    return changes


def bundle(day,service):
    b,patch,donors,_=ref.bundle(day,True)
    plans=b['prepared']['plans'][day]
    baseline=[tuple(p[:5]) for p in plans]
    old_walk=sum(p[3] for p in plans if not p[6])
    # All event clocks and surface-path lengths stay in the previous R's physical units.
    profiles=ref.load(PROFILE)
    physics=ref.load(REFERENCE/'walking_surface.json.gz')
    select_home_walk(b,day,profiles,physics)
    changed=tilt_origin_choices(b,day,profiles,service)
    b['grade_excess_ratio']={int(k):v['perceived_m']/v['physical_m']-1. if v['physical_m'] else 0.
                             for k,v in profiles.items()}
    assert baseline==[tuple(p[:5]) for p in plans]
    b['prepared']['common']['candidate_id']=MODEL
    return b,patch,donors,dict(reference_initial_walk=old_walk,candidate_initial_walk=sum(p[3] for p in plans if not p[6]),
                                initial_route_changes_after_home_choice=changed)
