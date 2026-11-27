"""Probe the audited city FIFO state without rerunning or duplicating demand.

Only aggregate five-minute conditional probe curves are exported. Each probe
is a virtual unit behind existing compatible queues; later arrivals cannot
jump it. Source upstream loads stay fixed, as in the frozen bridge contract.
"""
import bisect,hashlib,json,math,statistics
from collections import defaultdict
from pathlib import Path

SCHEMA='city_conditional_fifo_v1'
ALGORITHM='frozen_v5_city_compatible_fifo_v1'

def first_boardable(events,waiting,ready,wanted):
    """events=(time,pair,free-before-boarding), waiting=(mass,pairs,exit)."""
    queue=[[w,pairs,exit_at] for w,pairs,exit_at in waiting];skips=0;first=None
    for at,pair,free in events:
        if at<ready-1e-8:continue
        if pair in wanted and first is None:first=at
        for entry in queue:
            if entry[2] is not None and entry[2]<=at:entry[0]=0.
            if entry[0]<=1e-8 or pair not in entry[1]:continue
            take=min(free,entry[0]);entry[0]-=take;free-=take
            if free<=1e-8:break
        if pair in wanted:
            if free>=1-1e-8:return at,skips,first
            skips+=1
    return None,skips,first

class CityQueueBuilder:
    def __init__(self,common):
        self.common=common;self.services={};self.profiles={};self.audit=[]
        path=Path(__file__).parent/'data/network.json';raw=path.read_bytes()
        self.network_sha=hashlib.sha256(raw).hexdigest();network=json.loads(raw)
        self.routes={r['id']:r for r in network['routes']};self.by_node=defaultdict(list)
        from strategies import GATE_ROUTES,GATE_STOP,STATION_STOP
        for node_index in common['city_nodes']:
            node=common['nodes'][node_index];gate=[]
            for s in node['services']:
                rid=s['rid'];seq=s['seq'];route=self.routes[rid]
                stop=next((a for a in route['stops'] if a['seq']==seq and a['id']==node['stop_id']),None)
                if stop is None:raise ValueError('city_stop_mapping')
                key=f'{rid}:{seq}';pair=(rid,s['board'])
                self.services[key]={'route_id':rid,'seq':seq,'stop_id':stop['id'],'members':[[rid,seq]],
                    'reference_capacity_assumption':common['route_info'][rid]['capacity']}
                self.by_node[node_index].append((key,{pair}))
                if node['stop_id']==GATE_STOP and rid in GATE_ROUTES and any(a['id']==STATION_STOP and a['seq']>seq for a in route['stops']):gate.append((key,pair))
            if gate:
                key='pool:'+GATE_STOP
                self.services[key]={'stop_id':GATE_STOP,'members':[self.services[k]['members'][0] for k,p in gate]}
                self.by_node[node_index].append((key,{p for k,p in gate}))

    def add_day(self,day,audit):
        if audit['report']['capacity_violations']!=0:raise ValueError('unverified_city_capacity')
        waiting=defaultdict(list);events=defaultdict(list)
        for row in audit['wait_audit']:
            if row['node'] not in self.by_node or row['end']<=row['ready']+1e-8 or row['ticket'] is None:continue
            if row['weight']<0 or not math.isfinite(row['weight']):raise ValueError('city_mass')
            waiting[row['node']].append((row['ready'],row['end'],row['ticket'],row['weight'],
                frozenset((r,int(i)) for r,i in row['eligibility']),row['end'] if row['outcome']!='boarded' else None))
        for e in audit['events']:
            if e[1] not in self.by_node:continue
            free=e[3]-e[4]+e[5]
            if not -1e-6<=free<=e[3]+1e-6:raise ValueError('city_free_capacity')
            events[e[1]].append((e[0],(e[11],int(e[12])),max(0.,free)))
        censored=0;probes=0
        for node,groups in self.by_node.items():
            rows=sorted(waiting[node],key=lambda r:(r[0],r[2]));ready_times=[r[0] for r in rows];supply=sorted(events[node]);times=[r[0] for r in supply]
            for key,wanted in groups:
                heads=[]
                for pair in wanted:
                    selected=[t for t,p,f in supply if p==pair]
                    gaps=[b-a for a,b in zip(selected,selected[1:]) if b-a>1e-6]
                    if gaps:heads.append(statistics.median(gaps))
                reference=1/sum(1/h for h in heads) if heads else 600.
                self.services[key]['reference_headway_seconds']=round(reference,6)
                output=[]
                for minute in range(680,1390,5):
                    values=[];weights=[];skips=[];unserved=0
                    for phase in (50,150,250):
                        ready=minute*60+phase
                        ahead=[(w,pairs,exit_at) for a,b,ticket,w,pairs,exit_at in rows[:bisect.bisect_right(ready_times,ready)] if b>ready]
                        weights.append(math.fsum(w for w,pairs,e in ahead if pairs&wanted))
                        selected_at,missed,first=first_boardable(supply[bisect.bisect_left(times,ready):],ahead,ready,wanted)
                        probes+=1
                        if selected_at is None:unserved+=1;censored+=1
                        else:values.append(selected_at-first);skips.append(missed)
                    # Censoring stays explicit; never average only served phases.
                    if any(weights) or any(values) or unserved:
                        output.append([minute,None if unserved else round(statistics.mean(values),6),
                            None if unserved else round(statistics.mean(skips),6),round(statistics.mean(weights),6),unserved])
                self.profiles[f'{day}:{key}']=output
        self.audit.append({'weekday':day,'conditional_probes':probes,'censored_probes':censored})

    def result(self):
        return {'schema':SCHEMA,'algorithm_id':ALGORITHM,'network_sha256':self.network_sha,
            'unit':'conditional_virtual_unit_fifo_probe_not_observed_queue','start_minute':680,'end_minute':1390,'bin_minutes':5,
            'phase_seconds':[50,150,250],'services':self.services,'profiles':self.profiles,'audit':self.audit,
            'term_start':'2026-09-01','term_end':'2026-12-21',
            'scenario':'regular','independent_status':'PASS','external_background_passengers_included':False,
            'note':'보존 v5 상류 재차·조건부 대기흐름 고정. 경로 전환 유출은 원본 시각에 제거. 정원50/24는 시나리오 입력이며 실제 차량 여석 아님.'}
