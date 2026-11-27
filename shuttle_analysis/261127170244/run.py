"""Fixed-demand experiments on post-class stays and walking to engineering bus stops."""
from bisect import bisect_left
from collections import Counter,defaultdict
from functools import lru_cache
import argparse
import csv
import gzip
import importlib.util
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('accepted_origin_choice',ROOT/'261127162719/run.py')
parent=importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)
core=parent.prior
core.HERE=HERE
PAIR=('120000173','120000174')
MODES=('control','stay','access','joint','access_wide','joint_wide','access_soft','joint_soft')


def prepare(day,service,policy,diagnostic=False):
    b,donors,stats,upper,reference=parent.original_inputs(day,service,'choice')
    weekday=core.official.prior.DAYS[day]
    plans=b['prepared']['plans'][weekday];common=b['prepared']['common'];paths=common['paths']
    changes,_=parent.refine(b,plans,service,'october')
    for i,(walk,stages) in changes.items():plans[i]=[*plans[i][:5],walk,stages]
    stops=common['city_route_stops'];routes=common['route_info'];speed=b['walk_scales']
    dest=b['destination_keys']
    courses=core.timing.ref.ref.class_events(core.timing.ref.load(core.timing.ref.ref.COURSES))
    folder=HERE/'runs'/policy/f'{service}-{day}'
    access=core.read(HERE/'access_paths.json') if policy.startswith(('access','joint')) else None
    base_path=len(paths)
    if access:
        for j,row in enumerate(access['paths']):
            paths.append(row['polyline'])
            b['grade_excess_ratio'][base_path+j]=row['felt']/row['meters']-1
    templates=defaultdict(dict)
    for p in plans:
        if len(p[6])!=1 or dest[str(p[0])] not in ('snu','nak'):continue
        s=p[6][0];rid=s['rid']
        if rid not in stops or s.get('pool') or s.get('continuation_stages'):continue
        stop=stops[rid][s['board']]['id']
        if stop in PAIR:
            end=tuple(paths[s['next_walk'][0]][-1])
            templates[dest[str(p[0])],end,stop].setdefault((rid,s['board'],s['alight'],s['next_walk'][0]),p)

    @lru_cache(maxsize=None)
    def clocks(rid,board):
        info=routes[rid];offset=info.get('origin_to_modeled_first_stop_seconds',0)+info['offsets'][board]-info['offsets'][info['anchor']]
        dispatch=core.E.planned_departures(info['plan']) if info.get('city') else core.E.base.dispatches(rid,service)
        return sorted(t+offset for t in dispatch if t+offset<=core.E.END)

    def predicted(start,walk,stages):
        time=start+walk
        for s in stages:
            rid=s['rid'];i,j=s['board'],s['alight']
            times=clocks(rid,i);n=bisect_left(times,time+20)
            if n==len(times):return None
            main_board=times[n]
            offsets=routes[rid]['offsets']
            time=main_board+offsets[j]-offsets[i]+s['next_walk'][1]
        return (main_board,time) if stages and time<core.E.END else None

    counts=Counter();ledger=[];by_building=defaultdict(Counter)
    for idx,p in enumerate(plans):
        uid,building,_,weight,start,oldwalk,oldstages=p
        destination=dest[str(uid)];owner=donors.get(uid,uid)
        end_min=courses[(owner-1)//48]['end_minute']
        t=start;walk=oldwalk;stages=oldstages;changed=False
        if ((policy=='stay' or policy.startswith('joint')) and uid in upper and destination!=core.RAIL and
                15*60<=end_min<=17*60 and start<=(end_min+30)*60):
            counts['stay_eligible']+=weight
            if core.timing.uniform(f'evening-stay-pick/{owner}')<.25:
                t+=3600*(1+core.timing.uniform(f'evening-stay-length/{owner}'))
                counts['stay_changed']+=weight
        if access and uid not in upper and 17*3600<=t<21*3600 and destination in ('snu','nak'):
            counts['other_gateway_departures']+=weight
            if stages and stages[0]['rid'] in stops:counts['other_gateway_city_first']+=weight
        if (access and uid not in upper and 17*3600<=t<21*3600 and destination in ('snu','nak')
                and stages and stages[0]['rid'] in stops and not any(s.get('pool') or s.get('continuation_stages') for s in stages)
                and stops[stages[0]['rid']][stages[0]['board']]['id'] not in PAIR):
            end=tuple(paths[stages[-1]['next_walk'][0]][-1])
            options=[];original=predicted(t,walk[1],stages)
            oldfelt=walk[1]*(1+b['grade_excess_ratio'][walk[0]])
            flags={'eligible_first_plan'}
            for stop in PAIR:
                j=access['options'].get(f'{walk[0]}|{stop}')
                if j is None:continue
                flags.add('access_800m');row=access['paths'][j]
                seconds=row['meters']/(4/3)*speed[str(uid)]
                felt=seconds*row['felt']/row['meters']
                wide=policy.endswith(('_wide','_soft'))
                if row['felt']<=1000:flags.add('felt_under_1km')
                elif not policy.endswith('_soft'):continue
                if felt>oldfelt+(600 if wide else 300):continue
                flags.add('walk_cost_accepted')
                for other in templates[destination,end,stop].values():
                    ratio=speed[str(uid)]/speed[str(other[0])]
                    chain=core.E.scaled_stages(other[6],ratio)
                    scheduled=predicted(t,seconds,chain)
                    if not scheduled or not original:continue
                    flags.add('scheduled_direct')
                    if scheduled[0]>original[0]+(300 if wide else 0):continue
                    flags.add('board_clock_accepted')
                    if scheduled[1]>original[1]+(600 if wide else 300):continue
                    options.append((scheduled[0],felt,scheduled[1],other[0],j,seconds,chain))
            for flag in flags:
                counts[flag]+=weight
                if diagnostic:by_building[building][flag]+=weight
            if options:
                counts['access_eligible']+=weight
                _,_,_,_,j,seconds,choice=min(options,key=lambda x:x[:5])
                probability=.5
                if policy.endswith('_soft'):
                    probability*=.5**(max(0.,access['paths'][j]['felt']-1000)/300)
                if core.timing.uniform(f'campus-access-pick/{uid}')<probability:
                    stages=choice
                    walk=[base_path+j,seconds];changed=True
                    assert paths[walk[0]][0]==paths[oldwalk[0]][0]
                    assert tuple(paths[stages[-1]['next_walk'][0]][-1])==end
                    counts['access_changed']+=weight
                    if diagnostic:by_building[building]['changed']+=weight
        assert t>=start and len(p)==7
        plans[idx]=[*p[:4],t,walk,stages]
        ledger.append((uid,building,destination,weight,start,t,int(changed)))
    if diagnostic:
        return dict(total=counts,buildings=by_building)
    with gzip.open(folder/'inputs.csv.gz','wt',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(('uid','building','dest','weight','old_start','start','new_access'));w.writerows(ledger)
    core.save(folder/'treatment.json',counts)
    common['candidate_id']=common['data_version']='R'+HERE.name
    stats['first_target_r']=sum(p[3] for p in plans if p[0] in upper and core.first_target(p,common))
    return b,donors,stats,upper,reference


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('day',choices=core.official.prior.DAYS)
    parser.add_argument('service',choices=('regular','peak'))
    parser.add_argument('policy',choices=MODES)
    parser.add_argument('--diagnostic',action='store_true')
    a=parser.parse_args()
    core.inputs=prepare
    if a.diagnostic:
        core.save(HERE/f'walking_{a.policy}_{a.service}_{a.day}.json',prepare(a.day,a.service,a.policy,True))
    else:
        core.run(a.day,a.service,a.policy)
