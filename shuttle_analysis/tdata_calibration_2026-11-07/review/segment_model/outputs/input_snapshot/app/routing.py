"""Time-aware route candidates and preference scoring. No invented live arrivals."""
import heapq
import math
from collections import defaultdict, OrderedDict
from datetime import datetime, timedelta

PRESETS = {
    'fast': {'time': 75, 'crowd': 5, 'walk': 15, 'transfers': 5},
    'comfort': {'time': 25, 'crowd': 45, 'walk': 20, 'transfers': 10},
    'walk': {'time': 20, 'crowd': 5, 'walk': 70, 'transfers': 5},
    'transfer': {'time': 25, 'crowd': 5, 'walk': 10, 'transfers': 60},
}
CROWD_COST = {'3': 0.0, '4': 1.0, '5': 2.0, '6': 3.0}

def distance(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2-p1, math.radians(b[1]-a[1])
    x = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 6371000*2*math.atan2(math.sqrt(x), math.sqrt(max(0,1-x)))

def normalize(values):
    if not values:
        return []
    lo, hi = min(values), max(values)
    return [0.0 for _ in values] if hi == lo else [(v-lo)/(hi-lo) for v in values]

def rank_candidates(candidates, weights):
    weights = {k: float(weights.get(k, 0)) for k in ('time','crowd','walk','transfers')}
    if any(not math.isfinite(v) or v < 0 or v > 100 for v in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError('가중치는 0~100이며 합계가 0보다 커야 합니다.')
    active = dict(weights)
    omitted = []
    for c in candidates:
        c['normalized'] = {}
        c['score'] = None
        c['badges'] = []
    # Compare everyone on the same observed criteria. Unknown is never zero crowd.
    if any(c['crowd_cost'] is None for c in candidates):
        active['crowd'] = 0
        if weights['crowd'] > 0:
            omitted.append('일부 경로의 혼잡 정보가 없어 종합점수에서 혼잡 항목을 제외했습니다.')
    if sum(active.values()) == 0:
        candidates.sort(key=lambda c:c['total_seconds'])
        return {'candidates': candidates, 'effective_weights':{}, 'notes': omitted+['알려진 평가 지표에 가중치를 지정해 주세요.'], 'winners':{}}
    active = {k:v/sum(active.values()) for k,v in active.items()}
    metrics = {'time':'total_seconds', 'walk':'walk_m', 'transfers':'transfers', 'crowd':'crowd_cost'}
    normalized = {k:normalize([c[field] for c in candidates]) for k,field in metrics.items() if active[k] > 0}
    for i,c in enumerate(candidates):
        c['normalized'] = {k:v[i] for k,v in normalized.items()}
        c['score'] = round(100*sum(active[k]*v[i] for k,v in normalized.items()),2)
        c['badges'] = []
    winners = {}
    for mode,field in [('fast','total_seconds'),('walk','walk_m'),('transfer','transfers'),('comfort','crowd_cost')]:
        if mode=='comfort' and any(c['crowd_cost'] is None for c in candidates):
            continue
        eligible = [c for c in candidates if c[field] is not None]
        if eligible:
            winner=min(eligible,key=lambda c:(c[field],c['total_seconds']))
            winners[mode]=winner['id']
            winner['badges'].append(mode)
    candidates.sort(key=lambda c:(c.get('score',math.inf),c['total_seconds']))
    return {'candidates':candidates, 'effective_weights':active, 'notes':omitted, 'winners':winners}

def eligible_departure(arrivals, ready_at):
    eligible = [a for a in arrivals if a.get('departure_at') is not None and a.get('earliest_departure_at',a['departure_at']) >= ready_at and not a.get('full')]
    return min(eligible, key=lambda a:a['departure_at']) if eligible else None

class WalkingGraph:
    """Routes follow extracted OSM ways. Short endpoint connectors are disclosed."""
    ALLOWED = {'footway','pedestrian','path','steps','living_street','residential','service',
               'unclassified','tertiary','secondary','primary','tertiary_link','secondary_link','primary_link','track'}

    def __init__(self, payload):
        source_nodes={e['id']:(e['lat'],e['lon']) for e in payload['elements'] if e['type']=='node'}
        barred={e['id'] for e in payload['elements'] if e['type']=='node' and
                e.get('tags',{}).get('access') in ('private','no') and e.get('tags',{}).get('foot') not in ('yes','designated','permissive')}
        self.nodes={}; self.edges=defaultdict(list); self.cache=OrderedDict(); virtual=-1
        self.excluded_ways=0
        for way in payload['elements']:
            tags=way.get('tags',{})
            if way['type']!='way' or tags.get('highway') not in self.ALLOWED:
                continue
            if tags.get('foot') in ('no','private') or (tags.get('access') in ('no','private') and tags.get('foot') not in ('yes','designated','permissive')) or 'access:conditional' in tags or 'foot:conditional' in tags:
                self.excluded_ways+=1; continue
            directed=tags.get('oneway:foot','no')
            for a,b in zip(way['nodes'],way['nodes'][1:]):
                if a not in source_nodes or b not in source_nodes or a in barred or b in barred:
                    continue
                p,q=source_nodes[a],source_nodes[b]; length=distance(p,q)
                if length<=0: continue
                segments=max(1,math.ceil(length/25)); chain=[a]
                self.nodes[a]=p;self.nodes[b]=q
                for i in range(1,segments):
                    self.nodes[virtual]=(p[0]+(q[0]-p[0])*i/segments,p[1]+(q[1]-p[1])*i/segments)
                    chain.append(virtual);virtual-=1
                chain.append(b)
                for x,y in zip(chain,chain[1:]):
                    step_m=length/segments if tags.get('highway')=='steps' else 0
                    # 4.3 km/h ordinary walking, 2.5 km/h on mapped steps: assumptions.
                    seconds=length/segments/(0.7 if step_m else 1.2)
                    if directed!='-1':self.edges[x].append((y,seconds,length/segments,step_m))
                    if directed!='yes':self.edges[y].append((x,seconds,length/segments,step_m))
        self.points=list(self.nodes.items())

    def nearest(self,point):
        node,coord=min(self.points,key=lambda item:(item[1][0]-point[0])**2+((item[1][1]-point[1])*0.794)**2)
        return node,distance(coord,point)

    def tree(self,source):
        if source in self.cache:
            self.cache.move_to_end(source);return self.cache[source]
        costs={source:0}; parents={}; queue=[(0,source)]
        while queue:
            cost,node=heapq.heappop(queue)
            if cost!=costs.get(node):continue
            for neighbor,seconds,meters,steps in self.edges[node]:
                new=cost+seconds
                if new<costs.get(neighbor,math.inf):
                    costs[neighbor]=new;parents[neighbor]=(node,meters,steps);heapq.heappush(queue,(new,neighbor))
        self.cache[source]=(costs,parents)
        if len(self.cache)>24:self.cache.popitem(last=False)
        return costs,parents

    def walk(self,start,end):
        if distance(start,end)<1:
            return {'seconds':0,'meters':0,'steps_m':0,'geometry':[list(start),list(end)],'connectors_m':0,'source':'같은 지점'}
        a,da=self.nearest(start);b,db=self.nearest(end)
        if max(da,db)>110:
            return None
        costs,parents=self.tree(a)
        if b not in costs:return None
        chain=[b];meters=0;steps=0
        while chain[-1]!=a:
            parent,length,step=parents[chain[-1]];chain.append(parent);meters+=length;steps+=step
        chain.reverse()
        return {'seconds':round(costs[b]+(da+db)/1.2),'meters':round(meters+da+db),
                'steps_m':round(steps),'geometry':[list(start)]+[list(self.nodes[i]) for i in chain]+[list(end)],
                'connectors_m':round(da+db),'source':'OpenStreetMap 보행망 · 현장 검증 전'}

def finish_candidate(identifier,legs,departure_at,quality_notes=None):
    if not legs:return None
    bus=[leg for leg in legs if leg['type']=='bus']
    walk=[leg for leg in legs if leg['type']=='walk']
    total=sum(leg['seconds'] for leg in legs)
    crowd = max((leg['crowd_cost'] for leg in bus),default=0) if all(leg['crowd_cost'] is not None for leg in bus) else None
    return {'id':identifier,'legs':legs,'total_seconds':round(total),'walk_seconds':sum(x['seconds'] for x in walk),
            'walk_m':round(sum(x['meters'] for x in walk)), 'wait_seconds':sum(x['seconds'] for x in legs if x['type']=='wait'),
            'ride_seconds':sum(x['seconds'] for x in bus),'boarding_seconds':sum(x['seconds'] for x in legs if x['type']=='board'),
            'transfers':max(0,len(bus)-1),'crowd_cost':crowd,'crowd_label':'정보 없음' if crowd is None else
                ('도보' if not bus else {0:'여유',1:'보통',2:'혼잡',3:'매우혼잡'}[int(crowd)]),
            'steps_m':sum(x.get('steps_m',0) for x in walk),
            'departure_at':departure_at,'arrival_at':departure_at+total,
            'route_names':[x['route_name'] for x in bus], 'quality_notes':quality_notes or [],
            'evidence':'live_shuttle' if bus and all(x.get('arrival_source')=='live_shuttle' for x in bus) else
                'mixed_live' if any(x.get('arrival_source')=='live_shuttle' for x in bus) else
                'live' if bus and all(x.get('arrival_source')=='live' for x in bus) else 'estimate' if bus else 'walking'}

class Planner:
    def __init__(self, network, walker, transit):
        self.routes=network['routes'];self.walker=walker;self.transit=transit
        self.by_id={r['id']:r for r in self.routes}
        self.occurrences=defaultdict(list)
        for route in self.routes:
            for index,stop in enumerate(route['stops']):self.occurrences[stop['id']].append((route['id'],index))
        self.local_walks={}
        self.interchanges={}
        for first in self.routes:
            for i,a in enumerate(first['stops']):
                if not a.get('alight_allowed',True):continue
                options=list(self.occurrences[a['id']])
                for second in self.routes:
                    if first['id']==second['id'] or not (first.get('kind')=='shuttle' or second.get('kind')=='shuttle'):continue
                    nearby=sorted([(distance(self.point(a),self.point(b)),k) for k,b in enumerate(second['stops'])
                                   if b.get('board_allowed',True) and distance(self.point(a),self.point(b))<=180])[:2]
                    options.extend((second['id'],k) for _,k in nearby)
                self.interchanges[(first['id'],i)]=list(dict.fromkeys(options))

    @staticmethod
    def point(stop):return (stop['lat'],stop['lon'])

    def walk(self,a,b):
        key=tuple(round(x,6) for x in (*a,*b))
        if key not in self.local_walks:
            if len(self.local_walks)>2000:self.local_walks.clear()
            self.local_walks[key]=self.walker.walk(a,b)
        return self.local_walks[key]

    def downstream(self,route,board,destination):
        options=[]
        for j in range(board+1,len(route['stops'])):
            if route.get('cycle_length') and j-board>route['cycle_length']:break
            stop=route['stops'][j]
            if stop.get('alight_allowed',True) and distance(self.point(stop),destination)<650:
                foot=self.walk(self.point(stop),destination)
                if foot and foot['meters']<=1000:options.append((j,foot))
        # Keep two geographically best alighting points, never wrap a route silently.
        return sorted(options,key=lambda x:(x[1]['meters'],x[0]))[:2]

    def patterns(self,origin,destination,include_shuttle=False):
        starts=[]
        active=[r for r in self.routes if r.get('kind')!='shuttle' or include_shuttle and self.transit.shuttle.available(r)]
        active_ids={r['id'] for r in active}
        for route in active:
            nearby=sorted([(i,s) for i,s in enumerate(route['stops']) if s.get('board_allowed',True) and distance(origin,self.point(s))<800],
                          key=lambda x:distance(origin,self.point(x[1])))[:5]
            valid=[]
            for i,s in nearby:
                foot=self.walk(origin,self.point(s))
                if foot and foot['meters']<=1300:valid.append((foot['seconds'],i,foot))
            for _,i,foot in sorted(valid)[:3]:starts.append((route,i,foot))
        patterns=[]
        for route,i,foot in starts:
            for j,endwalk in self.downstream(route,i,destination):
                patterns.append({'rides':[(route['id'],i,j)],'first_walk':foot,'last_walk':endwalk})
            # Nearby shuttle/city interchanges include an actual walking leg.
            for j in range(i+1,min(len(route['stops']),i+17)):
                if route.get('cycle_length') and j-i>route['cycle_length']:break
                for second_id,k in self.interchanges.get((route['id'],j),[]):
                    if second_id==route['id'] or second_id not in active_ids:continue
                    second=self.by_id[second_id]
                    if not second['stops'][k].get('board_allowed',True):continue
                    change=self.walk(self.point(route['stops'][j]),self.point(second['stops'][k]))
                    if not change or change['meters']>300:continue
                    for end,endwalk in self.downstream(second,k,destination):
                        patterns.append({'rides':[(route['id'],i,j),(second_id,k,end)],'first_walk':foot,'last_walk':endwalk,'transfer_walk':change})
        for p in patterns:
            p['rough']=p['first_walk']['seconds']+p['last_walk']['seconds']+p.get('transfer_walk',{}).get('seconds',0)+sum(self.ride_seconds(self.by_id[r],i,j)+(90 if self.by_id[r].get('kind')=='shuttle' else self.by_id[r]['interval_minutes']*30) for r,i,j in p['rides'])
        # Diversify by first route/boarding occurrence; preserve walk alternatives.
        patterns.sort(key=lambda x:x['rough'])
        selected=[];counts=defaultdict(int)
        for p in patterns:
            signature=tuple(p['rides'])
            group=(p['rides'][0][0],len(p['rides']))
            if signature in {tuple(x['rides']) for x in selected} or counts[group]>=3:continue
            selected.append(p);counts[group]+=1
            if len(selected)>=32:break
        return selected

    def ride_seconds(self,route,i,j):
        meters=0
        for a,b in zip(route['stops'][i:j],route['stops'][i+1:j+1]):
            straight=distance(self.point(a),self.point(b))
            reported=b.get('segment_m',0)
            meters+=reported if straight*.7<=reported<=max(200,straight*3) else straight*1.2
        return round(meters/5 + (j-i)*15)  # 18 km/h + 15s per stop; disclosed assumption.

    def plan(self,origin,destination,departure,mode,weights,include_shuttle=True):
        # Real-time predictions are used only near the present, never for future timetables.
        live=mode=='live' and abs(departure-self.transit.now())<=90
        if include_shuttle and live and getattr(self.transit,'shuttle',None):self.transit.shuttle.refresh()
        patterns=self.patterns(origin,destination,include_shuttle and live)
        requests=set()
        if live:
            for p in patterns:
                for rid,i,j in p['rides']:
                    r=self.by_id[rid]
                    if r.get('kind')!='shuttle':requests.add((rid,i));requests.add((rid,j))
            self.transit.prefetch([(self.by_id[r],i) for r,i in sorted(requests)])
        candidates=[]
        direct=self.walk(origin,destination)
        if direct:
            candidates.append(finish_candidate('walk-only',[{'type':'walk','label':'목적지까지 도보',**direct}],departure,
                ['보행속도와 지도 연결은 추정입니다. 교내 통행 가능성·경사는 현장 확인 전입니다.']))
        for index,p in enumerate(patterns):
            legs=[{'type':'walk','label':'승차 정류소까지',**p['first_walk']}]
            clock=departure+p['first_walk']['seconds'];notes=[];valid=True
            for n,(rid,i,j) in enumerate(p['rides']):
                r=self.by_id[rid];board=r['stops'][i];alight=r['stops'][j]
                if n and p.get('transfer_walk'):
                    change=p['transfer_walk'];legs.append({'type':'walk','label':'환승 정류소까지',**change});clock+=change['seconds']
                ready=clock+20
                observed=self.transit.arrivals(r,i) if live else []
                selected=eligible_departure(observed,ready)
                ride=self.ride_seconds(r,i,j)
                if live and observed and selected is None:
                    after_shuttle=n>0 and any(leg.get('mode')=='shuttle' for leg in legs)
                    predictions_expired=all(a['departure_at']<ready for a in observed)
                    if r.get('kind')!='shuttle' and after_shuttle and predictions_expired:
                        notes.append('셔틀 환승 도착시각이 시내버스의 두 대 도착예정 범위를 넘어 이후 버스는 배차간격 시나리오입니다. 실제 차량은 미확인입니다.')
                    else:valid=False;break
                if selected:
                    leave=selected['departure_at'];source=selected.get('arrival_source','live')
                    crowd=selected.get('crowd_cost');label=selected.get('crowd_label','정보 없음')
                    end_observations=self.transit.arrivals(r,j)
                    matching=next((v for v in end_observations if v.get('vehicle_id')==selected.get('vehicle_id') and v['departure_at']>leave),None)
                    if matching and source=='live':
                        ride=round(matching['departure_at']-leave);ride_source='같은 차량의 정류소별 도착예정 차이'
                    else:
                        ride_source='구간거리·18km/h·정차 15초 가정'
                        notes.append('차내시간 일부는 구간거리·속도 가정입니다.')
                    if source=='live_shuttle':
                        notes.append(selected['prediction_note'])
                        notes.append('셔틀 GPS가 아닌 구간·정류소 관측입니다. 정류소 정차 관측은 출발 시각을 확인해야 합니다.' if selected['observed_at_stop'] else '접근 중인 셔틀은 보행 도착시각보다 추정 도착범위의 시작이 늦은 차량만 연결합니다.')
                else:
                    if r.get('kind')=='shuttle':valid=False;break
                    # Expected wait scenario is never labeled an observed departure.
                    if not self.transit.in_service(r,ready):valid=False;break
                    leave=ready+self.transit.interval(r,ready)*30;source='estimate'
                    if not self.transit.in_service(r,leave):valid=False;break
                    crowd=None;label='정보 없음';ride_source='구간거리·18km/h·정차 15초 가정'
                    notes.append('미래 운행은 확정 시간표가 아닌 배차간격의 절반 대기 시나리오입니다.')
                legs.append({'type':'board','seconds':20,'label':'승차·환승 여유'})
                legs.append({'type':'wait','seconds':round(max(0,leave-ready)),'label':r['name']+' 대기','source':source})
                legs.append({'type':'bus','seconds':ride,'route_id':rid,'route_name':r['name'],
                    'mode':r.get('kind','bus'),'route_color':r.get('color'),
                    'from_name':board['name'],'to_name':alight['name'],'from_seq':board['seq'],'to_seq':alight['seq'],
                    'station_id':board['id'],'geometry':[[s['lat'],s['lon']] for s in r['stops'][i:j+1]],
                    'crowd_cost':crowd,'crowd_label':label,'arrival_source':source,'ride_source':ride_source,
                    'departure_at':leave,'arrival_at':leave+ride,'vehicle_id':selected.get('vehicle_id') if selected else None})
                if source=='live_shuttle':
                    legs[-1].update({key:selected[key] for key in ('observed_interval','eta_window_seconds','prediction_note','observed_at_stop')})
                clock=leave+ride
            if not valid:continue
            legs.append({'type':'walk','label':'목적지까지',**p['last_walk']})
            if any(x.get('connectors_m',0)>10 for x in legs):notes.append('핀·정류소와 보행망 사이의 짧은 연결 구간은 현장 확인 전입니다.')
            candidate=finish_candidate('route-'+str(index),legs,departure,list(dict.fromkeys(notes)))
            if candidate['total_seconds']<3*3600:candidates.append(candidate)
        # Same vehicle and physical route can appear at repeated stop occurrences;
        # keep the faster representative without fabricating four distinct winners.
        unique={}
        for c in candidates:
            signature=tuple((x.get('route_id'),x.get('station_id'),x.get('to_name')) for x in c['legs'] if x['type']=='bus')
            if signature not in unique or c['total_seconds']<unique[signature]['total_seconds']:unique[signature]=c
        ranked=rank_candidates(list(unique.values()),weights)
        ranked.update({'requested_mode':mode,'live_predictions_used':live,
            'generated_at':self.transit.now(),'departure_at':departure,'candidate_count':len(unique),
            'scope':'시내버스 5개·셔틀 3개 노선 · 최대 1회 환승 · 셔틀 환승은 보행 경로 300m 이내 · 전역 최적 보장 아님',
            'assumptions':['일반 보행 1.2m/s · 계단 0.7m/s','승차·환승 여유 20초','도착예정 대응이 없는 차내 구간: 18km/h · 정차 15초',
                           '미관측 대기: 등록 배차간격의 절반','역 앞 대표 정류소 기준 · 출입구 현장 확인 전'],
            'source_notes':self.transit.notes()})
        return ranked
