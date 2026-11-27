"""Matched stop-choice experiment using feasible routes from the existing R choice library."""
import argparse
import csv
from bisect import bisect_left
from collections import Counter, defaultdict
from functools import lru_cache
import importlib.util
from pathlib import Path

HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent/'261127160713'
spec=importlib.util.spec_from_file_location('previous_upper_experiment',PRIOR/'experiment.py')
prior=importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
original_inputs=prior.inputs
prior.HERE=HERE
EPS=1e-6
NEXT_STOP='120000174'


def refine(bundle, plans, service, policy):
    common=bundle['prepared']['common']
    stops=common['city_route_stops']
    route_info=common['route_info']
    paths=common['paths']
    scales=bundle['walk_scales']
    grade=bundle['grade_excess_ratio']
    @lru_cache(maxsize=None)
    def schedule(rid,board):
        info=route_info[rid]
        offset=info.get('origin_to_modeled_first_stop_seconds',0)+info['offsets'][board]-info['offsets'][info['anchor']]
        return sorted(t+offset for t in prior.E.planned_departures(info['plan']) if t+offset<=prior.E.END)

    def eligible(p):
        if p[1] not in prior.UPPER or bundle['destination_keys'][str(p[0])]==prior.RAIL or len(p[6])!=1:
            return False
        stage=p[6][0]
        return stage['rid'] in stops and not stage.get('pool') and not stage.get('continuation_stages')

    def group_key(p):
        return (p[1],tuple(paths[p[5][0]][0]),bundle['destination_keys'][str(p[0])],
                tuple(paths[p[6][0]['next_walk'][0]][-1]))

    def score(template,p):
        stage=template[6][0]
        rid=stage['rid']; i,j=stage['board'],stage['alight']
        ratio=scales[str(p[0])]/scales[str(template[0])]
        access=template[5][1]*ratio
        egress=stage['next_walk'][1]*ratio
        times=schedule(rid,i)
        index=bisect_left(times,p[4]+access+20)
        if index==len(times):
            return None
        dep=times[index]
        arrival=dep+route_info[rid]['offsets'][j]-route_info[rid]['offsets'][i]+egress
        if arrival>prior.E.END:
            return None
        access_cost=access*(1+grade[template[5][0]])
        walk_cost=access_cost+egress*(1+grade[stage['next_walk'][0]])
        return dep,arrival,access_cost,walk_cost

    catalog=defaultdict(dict)
    for p in plans:
        if eligible(p):
            s=p[6][0]
            route_key=(p[5][0],s['rid'],s['board'],s['alight'],s['next_walk'][0])
            catalog[group_key(p)].setdefault(route_key,p)
    if policy in ('october','october02'):
        # Estimate a stop fraction within an already selected route and direction.
        # A physically repeated stop ID (5511 sequence 66) is a different opportunity.
        pair={}
        for rid,rr in stops.items():
            if policy=='october02' and rid!='120900011':
                continue
            for j in range(len(rr)-1):
                if (rr[j]['id'],rr[j+1]['id'])==(prior.TARGET,NEXT_STOP):
                    pair[rid]=(j,j+1)
        route_ids={r['name']:r['id'] for r in prior.read(HERE.parent/'app/data/network.json')['routes']}
        month=defaultdict(Counter)
        source=HERE.parent/'seoul_boardings_2026-11-10/outputs/campus_hourly_monthly_202610_long.csv'
        with source.open(encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                rid=route_ids.get(r['route_no'])
                if rid not in pair:
                    continue
                for j in pair[rid]:
                    if (r['stop_id'],int(r['stop_sequence']))==(stops[rid][j]['id'],stops[rid][j]['seq']):
                        month[rid,int(r['hour_kst'])][j]+=int(r['monthly_boardings'])
        base=defaultdict(Counter)
        for p in plans:
            if not p[6]:
                continue
            s=p[6][0]; rid=s['rid']; j=s['board']
            if rid not in pair or j not in pair[rid]:
                continue
            times=schedule(rid,j); index=bisect_left(times,p[4]+p[5][1]+20)
            if index<len(times):
                base[rid,int(times[index]//3600)][j]+=p[3]
        changes={}; details=Counter()
        for i,p in enumerate(plans):
            if not eligible(p):
                continue
            s=p[6][0]; rid=s['rid']; j=s['board']
            if rid not in pair or j not in pair[rid]:
                continue
            current=score(p,p)
            if current is None:
                continue
            key=rid,int(current[0]//3600)
            historic=month[key]; original=base[key]; upstream,downstream=pair[rid]
            if not sum(historic.values()) or not sum(original.values()):
                continue
            measured=historic[upstream]/sum(historic.values())
            fraction=original[upstream]/sum(original.values())
            delta=(measured-fraction)/2
            if (delta>0 and j==downstream) or (delta<0 and j==upstream):
                probability=delta/(1-fraction) if delta>0 else -delta/fraction
            else:
                continue
            details['eligible']+=p[3]
            if prior.timing.uniform(f'paired-october/{p[0]}')>=probability:
                continue
            old_run=current[0]-route_info[rid]['offsets'][j]
            candidates=[]
            for d in catalog[group_key(p)].values():
                a=d[6][0]
                if a['rid']!=rid or a['board'] not in pair[rid] or a['board']==j or a['alight']!=s['alight']:
                    continue
                alt=score(d,p)
                if alt is None or abs(alt[0]-route_info[rid]['offsets'][a['board']]-old_run)>EPS:
                    continue
                ratio=scales[str(p[0])]/scales[str(d[0])]
                if d[5][1]*ratio>p[5][1]+300 or alt[1]>current[1]+EPS:
                    continue
                candidates.append((alt[2],d[0],d,ratio))
            if candidates:
                _,_,d,ratio=min(candidates)
                changes[i]=([d[5][0],d[5][1]*ratio],prior.E.scaled_stages(d[6],ratio))
                details['changed']+=p[3]
                details['to_target' if j==downstream else 'from_target']+=p[3]
        return changes,details
    changed={}
    details=Counter()
    for i,p in enumerate(plans):
        if not eligible(p):
            continue
        details['eligible']+=p[3]
        original=score(p,p)
        if original is None:
            continue
        s=p[6][0]; old_stop=stops[s['rid']][s['board']]['id']
        best=None
        for d in catalog[group_key(p)].values():
            a=d[6][0]; new_stop=stops[a['rid']][a['board']]['id']
            if old_stop==new_stop:
                continue
            adjacent=(a['rid']==s['rid'] and a['alight']==s['alight'] and abs(a['board']-s['board'])==1)
            if policy=='adjacent' and not adjacent:
                continue
            candidate=score(d,p)
            if candidate is None or any(new>old+EPS for new,old in zip(candidate,original)):
                continue
            if original[0]-candidate[0]<1 and original[2]-candidate[2]<1:
                continue
            rank=(candidate[0],candidate[2],candidate[1],candidate[3],d[0])
            if best is None or rank<best[0]:
                best=(rank,d,new_stop,adjacent)
        if best is None:
            continue
        _,d,new_stop,adjacent=best
        ratio=scales[str(p[0])]/scales[str(d[0])]
        changed[i]=([d[5][0],d[5][1]*ratio],prior.E.scaled_stages(d[6],ratio))
        for k in ('changed','same_line_adjacent' if adjacent else 'other_direct',
                  'to_target' if new_stop==prior.TARGET else 'to_other',
                  'from_target' if old_stop==prior.TARGET else 'from_other'):
            details[k]+=p[3]
    return changed,details


def prepare(day,service,policy):
    bundle,donors,stats,upper,reference=original_inputs(day,service,'choice')
    common=bundle['prepared']['common']
    plans=bundle['prepared']['plans'][prior.official.prior.DAYS[day]]
    changes,details=({},Counter()) if policy=='previous' else refine(bundle,plans,service,policy)
    for i,(walk,stages) in changes.items():
        old=plans[i]
        new=[*old[:5],walk,stages]
        assert old[6][0]['rid'] in common['city_route_stops'] and stages[0]['rid'] in common['city_route_stops']
        assert old[1] in prior.UPPER and len(old[6])==len(stages)==1
        assert common['paths'][old[5][0]][0]==common['paths'][walk[0]][0]
        assert common['paths'][old[6][0]['next_walk'][0]][-1]==common['paths'][stages[0]['next_walk'][0]][-1]
        plans[i]=new
    details['changes_count']=len(changes)
    stats['first_target_r']=sum(p[3] for p in plans if p[0] in upper and prior.first_target(p,common))
    assert abs(stats['upper_r']-stats['upper_v12'])<1e-6
    prior.save(HERE/'runs'/policy/f'{service}-{day}'/'choice_changes.json',details)
    return bundle,donors,stats,upper,reference


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('day',choices=prior.official.prior.DAYS)
    parser.add_argument('service',choices=('peak','regular'))
    policies=('adjacent','direct','october','october02','previous')
    parser.add_argument('policy',nargs='?',choices=policies)
    a=parser.parse_args()
    prior.inputs=prepare
    selected=a.policy or prior.read(HERE/'research-model.json')['policy']
    if selected not in policies:
        parser.error('Unknown research policy in research-model.json')
    prior.run(a.day,a.service,selected)
