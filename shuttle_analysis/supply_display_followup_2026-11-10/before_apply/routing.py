"""Time-aware route candidates and preference scoring. No invented live arrivals."""
import heapq
import math
from collections import defaultdict, OrderedDict
from datetime import datetime, timedelta
from strategies import GATE_STOP,STATION_STOP,GATE_ROUTES,strategy_for
from walking_profile import WALK_MPS,STEP_MPS
from calculation_context import refresh_calculation_clock

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
    for c in candidates:
        c.setdefault('crowd_risk',c['crowd_cost'] if c['crowd_cost'] is not None else 3.)
    if weights['crowd']>0 and any(c['crowd_cost'] is None for c in candidates):
        omitted.append('혼잡 미확인·추정 경로에는 별도의 불확실성 비용을 반영합니다. 정보 부족은 실제 혼잡 관측이 아닙니다.')
    if sum(active.values()) == 0:
        candidates.sort(key=lambda c:c['total_seconds'])
        return {'candidates': candidates, 'effective_weights':{}, 'notes': omitted+['알려진 평가 지표에 가중치를 지정해 주세요.'], 'winners':{}}
    active = {k:v/sum(active.values()) for k,v in active.items()}
    metrics = {'time':'total_seconds', 'walk':'walk_m', 'transfers':'transfers', 'crowd':'crowd_risk'}
    normalized = {k:normalize([c[field] for c in candidates]) for k,field in metrics.items() if active[k] > 0}
    for i,c in enumerate(candidates):
        c['normalized'] = {k:v[i] for k,v in normalized.items()}
        c['score'] = round(100*sum(active[k]*v[i] for k,v in normalized.items()),2)
        c['badges'] = []
    winners = {}
    for mode,field in [('fast','total_seconds'),('walk','walk_m'),('transfer','transfers'),('comfort','crowd_risk')]:
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

def retain_ranked(ranked, limit=40, continuation=None):
    """Limit transport/storage after timing every candidate, preserving best choices."""
    rows=ranked['candidates'];keep=[];ids=set()
    def add(row):
        if row['id'] not in ids and len(keep)<limit:keep.append(row);ids.add(row['id'])
    winners=set(ranked.get('winners',{}).values())
    for row in rows:
        if row['id'] in winners:add(row)
    if rows:add(rows[0])
    if continuation:
        current=[r for r in rows if r.get('continuation_key')==continuation]
        if current:add(min(current,key=lambda r:r['total_seconds']))
    for row in rows:
        if row['id']=='walk-only' or row.get('common_gate_service'):add(row)
    # Preserve direct gate services and each shuttle even when continuity
    # forecasts make many more transfer patterns feasible than before.
    for rid in sorted(GATE_ROUTES):
        options=[r for r in rows if len(r.get('route_names',[]))==1 and not r.get('common_gate_service') and
                 any(l.get('route_id')==rid and l.get('station_id')==GATE_STOP for l in r.get('legs',[]))]
        if options:add(min(options,key=lambda r:r['total_seconds']))
    for rid in sorted({l['route_id'] for row in rows for l in row.get('legs',[]) if l.get('mode')=='shuttle'}):
        options=[r for r in rows if next((l.get('route_id') for l in r.get('legs',[]) if l['type']=='bus'),None)==rid]
        if options:add(min(options,key=lambda r:r['total_seconds']))
    groups=defaultdict(list)
    for row in rows:
        rides=[l for l in row.get('legs',[]) if l['type']=='bus']
        if not rides:continue
        first=rides[0]
        groups[(first['route_id'],len(rides),row.get('strategy'))].append(row)
    for values in groups.values():add(min(values,key=lambda r:(r['total_seconds'],r['crowd_risk'])))
    for row in rows:add(row)
    ranked['candidates']=[row for row in rows if row['id'] in ids]
    ranked['evaluated_candidate_count']=len(rows)
    ranked['output_candidate_limit']=limit
    ranked['output_reduced']=len(rows)>len(keep)
    return ranked

class WalkingGraph:
    """Routes follow extracted OSM ways. Short endpoint connectors are disclosed."""
    ALLOWED = {'footway','pedestrian','path','steps','living_street','residential','service',
               'unclassified','tertiary','secondary','primary','tertiary_link','secondary_link','primary_link','track'}

    def __init__(self, payload, buildings=None):
        from road_geometry import Buildings
        self.buildings=Buildings(buildings)
        source_nodes={e['id']:(e['lat'],e['lon']) for e in payload['elements'] if e['type']=='node'}
        barred={e['id'] for e in payload['elements'] if e['type']=='node' and
                e.get('tags',{}).get('access') in ('private','no') and e.get('tags',{}).get('foot') not in ('yes','designated','permissive')}
        self.nodes={}; self.edges=defaultdict(list); self.cache=OrderedDict(); self.endpoint_cache=OrderedDict(); virtual=-1
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
                if tags.get('tunnel') not in ('yes','building_passage') and not tags.get('bridge') and self.buildings.blocked(p,q):continue
                if length<=0: continue
                segments=max(1,math.ceil(length/25)); chain=[a]
                self.nodes[a]=p;self.nodes[b]=q
                for i in range(1,segments):
                    self.nodes[virtual]=(p[0]+(q[0]-p[0])*i/segments,p[1]+(q[1]-p[1])*i/segments)
                    chain.append(virtual);virtual-=1
                chain.append(b)
                for x,y in zip(chain,chain[1:]):
                    step_m=length/segments if tags.get('highway')=='steps' else 0
                    # User-selected average 4.8 km/h across the whole walking route.
                    seconds=length/segments/(STEP_MPS if step_m else WALK_MPS)
                    if directed!='-1':self.edges[x].append((y,seconds,length/segments,step_m))
                    if directed!='yes':self.edges[y].append((x,seconds,length/segments,step_m))
        self.points=list(self.nodes.items());self.point_grid=defaultdict(list)
        for order,(n,p) in enumerate(self.points):
            self.point_grid[(math.floor(p[0]*1000),math.floor(p[1]*1000))].append((order,n,p))

    def nearest(self,point):
        node,coord=min(self.points,key=lambda item:(item[1][0]-point[0])**2+((item[1][1]-point[1])*0.794)**2)
        return node,distance(coord,point)

    def endpoint(self,point):
        # The graph/building snapshot is immutable. Repeated stop coordinates use
        # exactly the same visibility/entrance result, including disconnected points.
        key=tuple(point)
        if key not in self.endpoint_cache:
            self.endpoint_cache[key]=self._endpoint(point)
            if len(self.endpoint_cache)>1024:self.endpoint_cache.popitem(last=False)
        else:self.endpoint_cache.move_to_end(key)
        return self.endpoint_cache[key]

    def _endpoint(self,point):
        buildings=self.buildings.containing(point)
        if buildings:
            # Keep device coordinates intact; omit unmeasured indoor geometry/time.
            exits=[e for b in buildings for e in b.get('entrances',[]) if distance(point,e['point'])<=150]
            options=[]
            for e in exits:
                anchor=self.visible_node(e['point'])
                if anchor:options.append((distance(point,e['point']),anchor,e))
            if not options:return None
            _,anchor,e=min(options,key=lambda x:x[0])
            return (*anchor,e['point'],True)
        anchor=self.visible_node(point)
        return (*anchor,point,False) if anchor else None

    def visible_node(self,point):
        # At campus latitude all nodes within the 30 m access limit lie in
        # these nine cells. Keep the original nearest-24 ordering and tie order.
        x,y=math.floor(point[0]*1000),math.floor(point[1]*1000)
        nearby=[item for i in range(x-1,x+2) for j in range(y-1,y+2) for item in self.point_grid.get((i,j),())]
        choices=heapq.nsmallest(24,nearby,key=lambda item:((item[2][0]-point[0])**2+((item[2][1]-point[1])*.794)**2,item[0]))
        for _,n,p in choices:
            d=distance(point,p)
            if d<=30 and not self.buildings.blocked(point,p):return n,d
        return None

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
        first=self.endpoint(start);last=self.endpoint(end)
        if not first or not last:return None
        a,da,start_access,indoor_start=first;b,db,end_access,indoor_end=last
        costs,parents=self.tree(a)
        if b not in costs:return None
        chain=[b];meters=0;steps=0
        while chain[-1]!=a:
            parent,length,step=parents[chain[-1]];chain.append(parent);meters+=length;steps+=step
        chain.reverse()
        return {'seconds':round(costs[b]+(da+db)/WALK_MPS),'meters':round(meters+da+db),
                'steps_m':round(steps),'geometry':[list(start_access)]+[list(self.nodes[i]) for i in chain]+[list(end_access)],
                'connectors_m':round(da+db),'source':'OpenStreetMap 보행망·출입구 · 현장 검증 전',
                'geometry_source':'osm_walkways_and_visible_access','geometry_version':'walk-access-v1',
                'indoor_access_unknown':indoor_start or indoor_end,'indoor_note':'건물 내부 이동시간은 미확인입니다. 경로는 지도에 등록된 출입구에서 연결합니다.' if indoor_start or indoor_end else None}

def finish_candidate(identifier,legs,departure_at,quality_notes=None):
    if not legs:return None
    bus=[leg for leg in legs if leg['type']=='bus']
    walk=[leg for leg in legs if leg['type']=='walk']
    total=sum(leg['seconds'] for leg in legs)
    crowd = max((leg['crowd_cost'] for leg in bus),default=0) if all(leg['crowd_cost'] is not None for leg in bus) else None
    return {'id':identifier,'legs':legs,'total_seconds':round(total),'walk_seconds':sum(x['seconds'] for x in walk),
            'walk_m':round(sum(x['meters'] for x in walk)), 'wait_seconds':sum(x['seconds'] for x in legs if x['type']=='wait'),
            'ride_seconds':sum(x['seconds'] for x in bus),'boarding_seconds':sum(x['seconds'] for x in legs if x['type']=='board'),
            'transfers':max(0,len(bus)-1),'crowd_cost':crowd,
            'crowd_risk':max((x.get('crowd_risk',x.get('crowd_cost') if x.get('crowd_cost') is not None else 3.) for x in bus),default=0),
            'crowd_label':('일부 정보 부족' if any(x.get('crowd_source')=='unavailable' for x in bus) else '혼잡도 모형 추정') if crowd is None else
                ('도보' if not bus else {0:'여유',1:'보통',2:'혼잡',3:'매우혼잡'}[int(crowd)]),
            'steps_m':sum(x.get('steps_m',0) for x in walk),
            'departure_at':departure_at,'arrival_at':departure_at+total,
            'route_names':[x['route_name'] for x in bus], 'quality_notes':quality_notes or [],
            'evidence':'live_shuttle' if bus and all(x.get('arrival_source')=='live_shuttle' for x in bus) else
                'mixed_live' if any(x.get('arrival_source')=='live_shuttle' for x in bus) else
                'live' if bus and all(x.get('arrival_source')=='live' for x in bus) else 'estimate' if bus else 'walking'}

class Planner:
    def __init__(self, network, walker, transit):
        from road_geometry import RoadGeometry
        self.geometry=RoadGeometry()
        from travel_time import TravelTime
        self.travel=TravelTime(geometry=self.geometry)
        self.routes=network['routes'];self.walker=walker;self.transit=transit
        self.routing_model=self.travel.simulation.info(self.routes)
        self.routing_model['shuttle_extension']={k:v for k,v in self.travel.extension.items() if k!='routes'}
        self.routing_model['shuttle_extension']['routes']={rid:len(r['segments']) for rid,r in self.travel.extension['routes'].items()}
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

    def patterns(self,origin,destination,include_shuttle=False,at=None,continuation=None,unpruned=False):
        starts=[]
        active=[r for r in self.routes if r.get('kind')!='shuttle' or include_shuttle and (self.transit.shuttle.available(r) or
            hasattr(self.transit.shuttle,'scheduled_available') and self.transit.shuttle.scheduled_available(r,at or self.transit.now()))]
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
        # Deliberately compare walking to the northbound gate even from upper campus.
        # Other distant stops retain the local search limits; no straight-line fallback.
        for route in active:
            if route['id'] not in GATE_ROUTES:continue
            for i,stop in enumerate(route['stops']):
                if stop['id']!=GATE_STOP:continue
                j=next((k for k in range(i+1,min(i+13,len(route['stops'])))
                        if route['stops'][k]['id']==STATION_STOP and distance(self.point(route['stops'][k]),destination)<80),None)
                if j is None:continue
                foot=self.walk(origin,self.point(stop));endwalk=self.walk(self.point(route['stops'][j]),destination)
                if foot and endwalk:patterns.append({'rides':[(route['id'],i,j)],'first_walk':foot,
                    'last_walk':endwalk,'preserve_gate':True})
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
            p['strategy']=strategy_for(p['rides'],self.by_id)
            p['rough']=p['first_walk']['seconds']+p['last_walk']['seconds']+p.get('transfer_walk',{}).get('seconds',0)+sum(self.ride_estimate(self.by_id[r],i,j,at or self.transit.now(),False)['seconds']+(90 if self.by_id[r].get('kind')=='shuttle' else self.by_id[r]['interval_minutes']*30) for r,i,j in p['rides'])
        # Diversify by first route/boarding occurrence; preserve walk alternatives.
        patterns.sort(key=lambda x:x['rough'])
        selected=[];counts=defaultdict(int);seen=set()
        protected=[p for p in patterns if p['rides'][0][0]+':'+self.by_id[p['rides'][0][0]]['stops'][p['rides'][0][1]]['id']==continuation][:3]
        protected.extend(p for p in patterns if p.get('preserve_gate'))
        for rid in dict.fromkeys(p['rides'][0][0] for p in patterns if p['strategy']=='shuttle_wait'):
            protected.append(next(p for p in patterns if p['rides'][0][0]==rid and p['strategy']=='shuttle_wait'))
        for p in protected+patterns:
            signature=tuple(p['rides'])
            group=(p['rides'][0][0],len(p['rides']))
            if signature in seen or not unpruned and counts[group]>=3:continue
            selected.append(p);seen.add(signature);counts[group]+=1
            if not unpruned and len(selected)>=40:break
        return selected

    def ride_seconds(self,route,i,j):
        return self.ride_estimate(route,i,j,self.transit.now(),False)['seconds']

    def ride_estimate(self,route,i,j,when,live):
        snapshot=getattr(self.transit,'plan_snapshot',getattr(self.transit,'snapshot',{})) if live else getattr(self.transit,'history_snapshot',{})
        return self.travel.estimate(route,i,j,when,snapshot,live)

    def plan(self,origin,destination,departure,mode,weights,include_shuttle=True,queue_context=None,decision_context=None):
        # Real-time predictions are used only near the present, never for future timetables.
        live=mode=='live' and abs(departure-self.transit.now())<=90
        if include_shuttle and live and getattr(self.transit,'shuttle',None) and not getattr(self.transit.shuttle,'model_only',False):self.transit.shuttle.refresh()
        patterns=self.patterns(origin,destination,include_shuttle,departure,(decision_context or {}).get('current_key'),unpruned=True)
        if include_shuttle and live and getattr(self.transit.shuttle,'model_only',False):
            if hasattr(self.transit.shuttle,'can_condition_clock'):
                relevant={self.by_id[rid]['provider_id'] for p in patterns for rid,i,j in p['rides'] if
                    self.by_id[rid].get('kind')=='shuttle' and self.transit.shuttle.can_condition_clock(self.by_id[rid],i)}
                self.transit.shuttle.load_cached_positions(relevant)
            else:self.transit.shuttle.load_cached_positions()
        requests=[]
        if live:
            for p in patterns:
                for n,(rid,i,j) in enumerate(p['rides']):
                    r=self.by_id[rid]
                    if r.get('kind')!='shuttle':
                        if n==0 and not self.transit.in_service(r,departure+p['first_walk']['seconds']+20):continue
                        pair=[x for x in [(rid,i),(rid,j)] if x not in requests]
                        if len(requests)+len(pair)<=16:requests.extend(pair)
            self.transit.prefetch([(self.by_id[r],i) for r,i in requests])
        refresh_calculation_clock()
        candidates=[]
        direct=self.walk(origin,destination)
        if direct:
            candidates.append(finish_candidate('walk-only',[{'type':'walk','label':'목적지까지 도보',**direct}],departure,
                ['보행속도와 지도 연결은 추정입니다. 교내 통행 가능성·경사는 현장 확인 전입니다.']))
            candidates[-1]['strategy']='walk_only'
        for index,p in enumerate(patterns):
            legs=[{'type':'walk','label':'승차 정류소까지',**p['first_walk']}]
            clock=departure+p['first_walk']['seconds'];notes=[];valid=True
            for n,(rid,i,j) in enumerate(p['rides']):
                r=self.by_id[rid];board=r['stops'][i];alight=r['stops'][j]
                road=self.geometry.leg(r,i,j)
                if road is None:valid=False;break
                if n and p.get('transfer_walk'):
                    change=p['transfer_walk'];legs.append({'type':'walk','label':'환승 정류소까지',**change});clock+=change['seconds']
                waiting_since=(decision_context or {}).get('waiting_since')
                current_key=(decision_context or {}).get('current_key')
                already_ready=bool(n==0 and waiting_since is not None and self.transit.now()-waiting_since>=20 and
                    distance(origin,self.point(board))<=60 and (current_key==rid+':'+board['id'] or
                    current_key=='gate-first:120000029' and rid in GATE_ROUTES and board['id']==GATE_STOP))
                prep=0 if already_ready else 20;ready=clock+prep
                observed=(self.transit.shuttle.ready_arrivals(r,i,ready) if r.get('kind')=='shuttle' and hasattr(self.transit.shuttle,'ready_arrivals') else self.transit.arrivals(r,i)) if live else []
                if not live and r.get('kind')=='shuttle' and hasattr(self.transit.shuttle,'scheduled_arrivals'):
                    observed=self.transit.shuttle.scheduled_arrivals(r,i,ready)
                opportunity=None
                if live and r.get('kind')=='shuttle':
                    first_live=min((a for a in observed if a.get('arrival_source')=='live_shuttle' and a.get('earliest_departure_at',a['departure_at'])>=ready),key=lambda a:a['departure_at'],default=None)
                    first=first_live or self.transit.shuttle.timetable._schedule_arrival(r,i,ready)
                    if first:opportunity={'departure_at':first['departure_at'],'vehicle_id':first.get('vehicle_id') if first_live else None}
                queue_applied=bool(live and n==0 and queue_context and r.get('kind')=='shuttle' and
                    queue_context['route_id']==rid and queue_context['station_id']==board['id'] and distance(origin,self.point(board))<=60)
                if queue_applied:
                    from adaptive import queue_arrivals
                    projected=queue_arrivals(r,i,ready,observed,queue_context,self.transit.shuttle.timetable,self.transit.now())
                    if projected is None:queue_applied=False
                    else:
                        observed=projected
                        if not observed:valid=False;break
                automatic_applied=False
                if not queue_applied and r.get('kind')=='shuttle' and getattr(self.transit,'automatic_queue',None):
                    snapshot=getattr(self.transit,'plan_snapshot',getattr(self.transit,'snapshot',{})) if live else {}
                    automatic=self.transit.automatic_queue.arrival(r,i,ready,observed,self.transit.shuttle.timetable,self.transit.now(),snapshot,live)
                    if automatic is not None:
                        observed=automatic;automatic_applied=bool(automatic)
                        if not observed:valid=False;break
                selected=eligible_departure(observed,ready)
                fallback=self.transit.forecast_service(r,i,ready,observed,live) if hasattr(self.transit,'forecast_service') else None
                if selected is None and fallback:
                    selected=fallback;observed=[*observed,fallback]
                    notes.append('실제 차량은 미확인입니다. 이전 운행·시간표·시뮬레이션으로 다음 운행기회를 추정합니다.')
                if r.get('kind')!='shuttle' and selected and hasattr(self.transit,'city_boarding'):
                    base={**selected,'arrival_forecast':(fallback or selected).get('arrival_forecast',{})}
                    selected=self.transit.city_boarding(r,i,ready,base,live)
                    if selected is None:valid=False;break
                    fallback=selected
                ride_info=self.ride_estimate(r,i,j,ready,live);ride=ride_info['seconds'];ride_source=ride_info['label']
                if live and observed and selected is None:
                    after_shuttle=n>0 and any(leg.get('mode')=='shuttle' for leg in legs)
                    predictions_expired=all(a['departure_at']<ready for a in observed)
                    if r.get('kind')!='shuttle' and (after_shuttle or p.get('strategy')=='walk_to_gate') and predictions_expired:
                        notes.append('정류소까지 이동하는 동안 조회된 두 대가 먼저 통과하여 이후 버스는 배차간격 시나리오입니다. 실제 차량은 미확인입니다.')
                    else:valid=False;break
                if selected:
                    leave=selected['departure_at'];source=selected.get('arrival_source','live')
                    crowd=selected.get('crowd_cost');label=selected.get('crowd_label','정보 없음')
                    ride_info=self.ride_estimate(r,i,j,leave,live)
                    end_observations=self.transit.arrivals(r,j)
                    matching=next((v for v in end_observations if v.get('vehicle_id')==selected.get('vehicle_id') and v['departure_at']>leave),None)
                    from travel_time import paired_arrival_time
                    paired=paired_arrival_time(selected,matching,road['meters'],self.transit.now()) if source=='live' else None
                    if paired:ride_info=paired
                    ride=ride_info['seconds'];ride_source=ride_info['label']
                    if ride_info.get('note'):notes.append(ride_info['note'])
                    if source in ('live_shuttle','shuttle_timetable_estimate','shuttle_queue_estimate','shuttle_auto_queue_estimate'):
                        notes.append(selected['prediction_note'])
                        if not queue_applied and not automatic_applied:notes.append('셔틀 GPS가 아닌 구간·정류소 관측입니다. 정류소 정차 관측은 출발 시각을 확인해야 합니다.' if selected['observed_at_stop'] else '접근 중인 셔틀은 보행 도착시각보다 추정 도착범위의 시작이 늦은 차량만 연결합니다.')
                else:
                    if r.get('kind')=='shuttle':valid=False;break
                    # Expected wait scenario is never labeled an observed departure.
                    if not self.transit.in_service(r,ready):valid=False;break
                    leave=ready+self.transit.interval(r,ready)*30;source='estimate'
                    if not self.transit.in_service(r,leave):valid=False;break
                    crowd=None;label='정보 없음'
                    ride_info=self.ride_estimate(r,i,j,leave,live);ride=ride_info['seconds'];ride_source=ride_info['label']
                    notes.append('미래 운행은 확정 시간표가 아닌 배차간격의 절반 대기 시나리오입니다.')
                if not ride_info.get('available',True):valid=False;break
                legs.append({'type':'board','seconds':prep,'label':'승차 준비 완료' if already_ready else '승차·환승 여유'})
                legs.append({'type':'wait','seconds':round(max(0,leave-ready)),'label':r['name']+' 대기','source':source})
                legs.append({'type':'bus','seconds':ride,'route_id':rid,'route_name':r['name'],
                    'mode':r.get('kind','bus'),'route_color':r.get('color'),
                    'from_name':board['name'],'to_name':alight['name'],'from_seq':board['seq'],'to_seq':alight['seq'],
                    'station_id':board['id'],'station_ars':board.get('ars'),'ready_at':ready,**road,
                    'crowd_cost':crowd,'crowd_label':label,'arrival_source':source,'ride_source':ride_source,
                    'departure_at':leave,'arrival_at':leave+ride,'vehicle_id':selected.get('vehicle_id') if selected else None,
                    'ride_model':ride_info,'arrival_options':[{**a,'catchable_at_search':a.get('earliest_departure_at',a['departure_at'])>=ready} for a in observed[:2]]})
                from prediction import crowd_evidence
                evidence=self.transit.crowd_for(r,i,selected,leave,live) if hasattr(self.transit,'crowd_for') else crowd_evidence(selected,self.transit.now()) if live else crowd_evidence(None,self.transit.now())
                legs[-1].update(evidence,eta_source=source,eta_observed_at=selected.get('provided_at') if selected else None)
                legs[-1]['arrival_forecast']=(fallback or selected or {}).get('arrival_forecast')
                if source in ('live_shuttle','shuttle_timetable_estimate','shuttle_queue_estimate','shuttle_auto_queue_estimate'):
                    legs[-1].update({key:selected[key] for key in ('observed_interval','eta_window_seconds','prediction_note','observed_at_stop')})
                if selected and selected.get('queue_projection'):legs[-1]['queue_projection']=selected['queue_projection']
                if selected and selected.get('automatic_queue'):legs[-1]['automatic_queue']=selected['automatic_queue']
                if selected and selected.get('city_wait'):legs[-1]['city_wait']=selected['city_wait']
                if opportunity:legs[-1]['queue_report_opportunity']=opportunity
                clock=leave+ride
            if not valid:continue
            legs.append({'type':'walk','label':'목적지까지',**p['last_walk']})
            if any(x.get('connectors_m',0)>10 for x in legs):notes.append('핀·정류소와 보행망 사이의 짧은 연결 구간은 현장 확인 전입니다.')
            notes.extend(x['indoor_note'] for x in legs if x.get('indoor_note'))
            candidate=finish_candidate('route-'+str(index),legs,departure,list(dict.fromkeys(notes)))
            candidate['strategy']=p['strategy']
            if candidate['total_seconds']<3*3600:candidates.append(candidate)
        # Same vehicle and physical route can appear at repeated stop occurrences;
        # keep the faster representative without fabricating four distinct winners.
        unique={}
        for c in candidates:
            signature=tuple((x.get('route_id'),x.get('station_id'),x.get('to_name')) for x in c['legs'] if x['type']=='bus')
            if signature not in unique or c['total_seconds']<unique[signature]['total_seconds']:unique[signature]=c
        from gate_service import add_common_gate
        from adaptive import boarding_key
        values=add_common_gate(list(unique.values()),self,departure,live)
        for c in values:c['continuation_key']=boarding_key(c)
        if decision_context:
            values=[c for c in values if c['continuation_key'] not in decision_context['abandoned_keys'] or c['continuation_key']==decision_context['current_key']]
        ranked=retain_ranked(rank_candidates(values,weights),40,(decision_context or {}).get('current_key'))
        ranked.update({'requested_mode':mode,'live_predictions_used':live,
            'include_shuttle':include_shuttle,
            'generated_at':self.transit.now(),'departure_at':departure,'candidate_count':len(ranked['candidates']),
            'candidate_search':{'patterns_evaluated':len(patterns),'early_time_pruning':False,
                                'returned_limit':40,'provider_prefetch_limit':16},
            'routing_model':self.routing_model,
            'scope':f"시내버스 8개·셔틀 {sum(r.get('kind')=='shuttle' for r in self.routes)}개 노선 · 최대 1회 환승 · 셔틀 환승은 보행 경로 300m 이내 · 전역 최적 보장 아님",
            'assumptions':['전체 보행 평균4.8km/h(1.333m/s) · 계단 구간 별도 표시','승차·환승 여유 20초','차내시간: 같은 차량 도착예정 차이·완료 관측·최신 구간속도 우선, 나머지 일치 구간은 v5 주행모형',
                           'v5 주행모형: 교내40·외부65km/h 상한·가감속1m/s²·도착지 정차15초 포함의 시나리오 · 실측 운행이나 법정 속도 아님',
                           'v5 입력과 일치하지 않는 시내 구간은 과거 구간속도 또는18km/h 가정 · 실측 정확도 개선은 미검증',
                           '대학동 주간·야간 셔틀: 공식 시간표 대기·도로거리/18km/h 가정 · 노선 전용 줄·주행시간 보정 자료 미구축',
                           '미관측 대기: 이전 도착·저장 통과간격·등록 시간표·최신 셔틀모형의 예상 운행기회','역 앞 대표 정류소 기준 · 출입구 현장 확인 전'],
            'source_notes':self.transit.notes()})
        return ranked
