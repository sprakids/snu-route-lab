"""Paired interventions on evening station assignment and Gwanak 02-1 access."""
import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
import csv
from functools import lru_cache
import importlib.util
from pathlib import Path

HERE=Path(__file__).resolve().parent
PARENT=HERE.parent/'261127162719'
spec=importlib.util.spec_from_file_location('accepted_stop_research', PARENT/'run.py')
parent=importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)
core=parent.prior
core.HERE=HERE
LINE='120900011'
STATION_STOPS={'120900119','120900110'}
POLICIES=('station','route','both','control','alternative','station_alternative','law_transfer','station_law')


def initial_mode(plan):
    if not plan[6]:return 'walk'
    return 'shuttle' if plan[6][0]['rid'].startswith('shuttle') else 'city'


def prepare(day, service, policy):
    bundle, donors, stats, upper, baseline=parent.original_inputs(day,service,'choice')
    weekday=core.official.prior.DAYS[day]
    plans=bundle['prepared']['plans'][weekday]
    common=bundle['prepared']['common']
    changes,_=parent.refine(bundle,plans,service,'october')
    for i,(walk,stages) in changes.items():
        plans[i]=[*plans[i][:5],walk,stages]
    paths=common['paths']; info=common['route_info']
    scales=bundle['walk_scales']; dest=bundle['destination_keys']
    details=Counter()
    def origin(p):
        return p[1], tuple(paths[p[5][0]][0])
    def evening(p):
        return p[0] in upper and 17*3600<=p[4]<21*3600
    def direct(p):
        return (len(p[6])==1 and p[6][0]['rid']==LINE and
                common['city_route_stops'][LINE][p[6][0]['alight']]['id'] in STATION_STOPS)
    @lru_cache(maxsize=None)
    def clocks(rid,board):
        row=info[rid]
        times=core.E.planned_departures(row['plan']) if row.get('city') else core.E.base.dispatches(rid,service)
        offset=row.get('origin_to_modeled_first_stop_seconds',0.)+row['offsets'][board]-row['offsets'][row['anchor']]
        return sorted(t+offset for t in times if t+offset<=core.E.END)
    def arrival_clock(p,template):
        ratio=scales[str(p[0])]/scales[str(template[0])]
        t=p[4]+ratio*template[5][1]
        for stage in template[6]:
            rid=stage['rid']; schedule=clocks(rid,stage['board'])
            i=bisect_left(schedule,t+20)
            if i==len(schedule):return float('inf')
            off=info[rid]['offsets']
            t=schedule[i]+off[stage['alight']]-off[stage['board']]+ratio*stage['next_walk'][1]
        return t if t<=core.E.END else float('inf')
    def transplant(p,d):
        assert origin(p)==origin(d) and initial_mode(p)==initial_mode(d)
        ratio=scales[str(p[0])]/scales[str(d[0])]
        return [p[0],p[1],'nak',p[3],p[4],[d[5][0],d[5][1]*ratio],core.E.scaled_stages(d[6],ratio)]

    # Freeze the reference donors and mix before applying either treatment.
    pool=defaultdict(list); mix=defaultdict(Counter)
    for p in plans:
        if p[0] not in upper:continue
        label=dest[str(p[0])]
        if evening(p) and label in ('snu','nak'):
            mix[origin(p),int(p[4]//3600)][label]+=p[3]
        if label=='nak':
            pool[origin(p),initial_mode(p)].append(p)
    def draw_template(p,only_direct,seed):
        # Within the same actual departure hour where possible; fall back to the adjacent hours.
        eligible=pool[origin(p),initial_mode(p)]
        h=int(p[4]//3600)
        for distance in (0,1):
            options=[x for x in eligible if abs(int(x[4]//3600)-h)==distance
                     and (not only_direct or direct(x)) and arrival_clock(p,x)<=core.E.END]
            if options:
                ticket=core.timing.uniform(f'nak-evening/{seed}/{p[0]}')*sum(x[3] for x in options)
                for x in options:
                    ticket-=x[3]
                    if ticket<=0:return x
                return options[-1]
        return None

    alternative=defaultdict(dict)
    if policy in ('alternative','station_alternative','law_transfer','station_law'):
        # Join an existing upper-campus access leg and its real transfer walk
        # to a compatible 02-2 stage at that exact boarding node.
        lookup={n['id']:i for i,n in enumerate(common['nodes'])}
        for x in plans:
            if x[0] not in upper or len(x[6])<2:continue
            first,second=x[6][:2]
            if first['rid']==LINE or first.get('pool') or first.get('continuation_stages'):continue
            ref=f"{second['rid']}|{second['board']}"
            node=lookup.get(ref) if second['rid'].startswith('shuttle') else bundle['city_node_lookup'].get(ref)
            candidates=bundle['compatible_single_stage_pools'].get(f'{node}|nak',[])
            if any(s['rid']==LINE for s in candidates):continue
            for s in candidates:
                if s['rid']!='120900012' or s.get('continuation_stages'):continue
                if common['city_route_stops'][s['rid']][s['alight']]['id'] not in STATION_STOPS:continue
                walk_end=paths[first['next_walk'][0]][-1]
                wait_start=paths[s['wait_path']][0]
                if max(abs(a-b) for a,b in zip(walk_end,wait_start))>1e-5:continue
                alt=[*x[:5],x[5],[first,*core.E.scaled_stages([s],scales[str(x[0])])]]
                shape=(x[5][0],first['rid'],first['board'],first['alight'],first['next_walk'][0],s['board'],s['alight'])
                alternative[origin(x),initial_mode(x)].setdefault(shape,alt)
        if policy in ('law_transfer','station_law'):
            # Both routes stop at the identical outward Law/Social Sciences platform.
            first_id='100100250'; next_id='120900012'; transfer_stop='120000196'
            rr=common['city_route_stops']
            end=next(i for i,s in enumerate(rr[first_id]) if s['id']==transfer_stop)
            join=next(i for i,s in enumerate(rr[next_id]) if s['id']==transfer_stop)
            n=bundle['city_node_lookup'][f'{first_id}|{end}']
            assert n==bundle['city_node_lookup'][f'{next_id}|{join}']
            final=next(s for s in bundle['compatible_single_stage_pools'][f'{n}|nak']
                       if s['rid']==next_id and s['board']==join and rr[next_id][s['alight']]['id']=='120900119')
            assert len({tuple(point) for point in paths[final['wait_path']]})==1
            bundle['grade_excess_ratio'].setdefault(final['wait_path'],0.)
            route_paths={}
            for x in plans:
                if x[0] not in upper or not x[6]:continue
                f=x[6][0];start=f['board']
                if f['rid']!=first_id or start>=end or rr[first_id][start]['id'] not in (core.TARGET,'120000174'):continue
                if start not in route_paths:
                    segments=info[first_id]['segments'][start:end]
                    route_paths[start]=len(paths)
                    paths.append([point for pid in segments for point in paths[pid]])
                first_stage=dict(rid=first_id,board=start,alight=end,ride_path=route_paths[start],
                                 ride_seconds=info[first_id]['offsets'][end]-info[first_id]['offsets'][start],
                                 wait_path=f['wait_path'],dynamic_city=True,city_wait=0.,
                                 next_walk=[final['wait_path'],0.])
                alt=[*x[:5],x[5],[first_stage,*core.E.scaled_stages([final],scales[str(x[0])])]]
                alternative[origin(x),initial_mode(x)].setdefault(('law',x[5][0],start),alt)
    records=[]
    for i,old in enumerate(plans):
        if not evening(old):continue
        p=old; uid=str(p[0]); before=dest[uid]; after=before
        if policy in ('station','both','station_alternative','station_law') and before=='snu':
            cell=mix[origin(old),int(old[4]//3600)]
            q=cell['nak']/(cell['snu']+cell['nak'])
            # Equivalent to doubling the odds of Nakseongdae among the two subway gateways in expectation.
            if core.timing.uniform(f'nak-station-draw/{uid}')<q/(1+q):
                donor=draw_template(p,False,'destination-path')
                if donor is None:details['dest_no_feasible']+=p[3]
                else:
                    p=transplant(p,donor)
                    after='nak'
                    details['dest_changed']+=p[3]
        if policy in ('route','both') and after=='nak' and initial_mode(p)=='city' and not direct(p):
            details['route_eligible']+=p[3]
            if core.timing.uniform(f'nak-direct-draw/{uid}')<.5:
                donor=draw_template(p,True,'direct-path')
                if donor is None:details['route_no_feasible']+=p[3]
                else:
                    p=transplant(p,donor)
                    details['route_changed']+=p[3]
        if policy in ('alternative','station_alternative','law_transfer','station_law') and after=='nak' and any(s['rid']==LINE for s in p[6]):
            options=[]
            original_arrival=arrival_clock(p,p)
            for alt in alternative[origin(p),initial_mode(p)].values():
                t=arrival_clock(p,alt)
                if t<=core.E.END and t<=original_arrival+300:options.append((t,alt[0],alt))
            if options:
                details['alternative_feasible']+=p[3]
                if core.timing.uniform(f'nak-02-2/{uid}')<.5:
                    p=transplant(p,min(options,key=lambda z:z[:2])[2])
                    details['alternative_changed']+=p[3]
        assert p[0:2]==old[0:2] and p[3:5]==old[3:5] and initial_mode(p)==initial_mode(old)
        if p is not old:
            assert after=='nak' and before in ('snu','nak')
            path=p[6][-1]['next_walk'][0] if p[6] else p[5][0]
            end=paths[path][-1]
            assert all(abs(a-b)<1e-6 for a,b in zip(end,common['destinations']['nak']))
        dest[uid]=after; plans[i]=p
        records.append((p[0],p[1],p[4],p[3],before,after,int(direct(old)),int(direct(p)),
                        int(any(s['rid']==LINE for s in old[6])),int(any(s['rid']==LINE for s in p[6]))))
    folder=HERE/'runs'/policy/f'{service}-{day}'
    with (folder/'evening_cohorts.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['uid','building','start','weight','dest_before','dest_after','direct_before','direct_after','uses_before','uses_after']);w.writerows(records)
    stats['first_target_r']=sum(p[3] for p in plans if p[0] in upper and core.first_target(p,common))
    common['candidate_id']=common['data_version']='R'+HERE.name
    core.save(folder/'treatment.json',details)
    return bundle,donors,stats,upper,baseline


if __name__=='__main__':
    a=argparse.ArgumentParser()
    a.add_argument('day',choices=core.official.prior.DAYS)
    a.add_argument('service',choices=('peak','regular'))
    a.add_argument('policy',choices=POLICIES)
    args=a.parse_args()
    core.inputs=prepare
    core.run(args.day,args.service,args.policy)
