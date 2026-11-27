"""Independent BUSIN live routes; geographic labels are stop areas, not vehicle GPS."""
import json
import math
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from routing import distance
from road_geometry import RoadGeometry,length

ENDPOINT='https://web.busin.co.kr/BuslineCircleS.aspx/GetRoute'
CATALOG=json.loads((Path(__file__).parent/'data/shuttle_network.json').read_text(encoding='utf-8'))
ADMIN_ROUTE=CATALOG['routes'][0]
SOURCE_URL=ADMIN_ROUTE['source_url']
SCHEMATIC=[(a['x'],a['y'],a['name']) for a in ADMIN_ROUTE['anchors']]
SCHEMATIC.append(SCHEMATIC[0])

def point(a):return (a['lat'],a['lon']) if 'lat' in a else None

def locate(x,y,anchors=None):
    anchors=anchors or ADMIN_ROUTE['anchors']
    near=min(range(len(anchors)),key=lambda i:math.hypot(x-anchors[i]['x'],y-anchors[i]['y']))
    at_stop=math.hypot(x-anchors[near]['x'],y-anchors[near]['y'])<=11
    best=None
    for i,a in enumerate(anchors):
        b=anchors[(i+1)%len(anchors)];dx,dy=b['x']-a['x'],b['y']-a['y']
        t=max(0,min(1,((x-a['x'])*dx+(y-a['y'])*dy)/(dx*dx+dy*dy)))
        offset=math.hypot(x-a['x']-t*dx,y-a['y']-t*dy)
        if best is None or offset<best[0]:best=(offset,i,t)
    if best[0]>45:return None
    _,i,t=best
    if at_stop:i=near;t=0
    a,b=anchors[i],anchors[(i+1)%len(anchors)]
    return {'segment_index':i,'at_stop_index':near if at_stop else None,'at_stop':at_stop,
            'from_name':a['name'],'to_name':b['name'],
            'direction':'towards_admin' if i<4 else 'towards_station',
            'position_kind':'schematic_stop_area' if at_stop else 'schematic_landmark_interval',
            'schematic_progress':round(t,3)}

class LiveShuttle:
    def __init__(self,network,transit,route=None):
        self.route=route or ADMIN_ROUTE;self.transit=transit;self.lock=threading.Lock()
        self.geometry=RoadGeometry()
        self.previous={};self.last_attempt=0
        self.state={'captured_at':None,'vehicles':[],'error':None,'provider_timestamp':None}

    def refresh(self):
        if getattr(self.transit,'shared',None):
            key='shuttle-v2-'+self.route['id']
            def produce():
                old=self.transit.shared.read('cache-'+key)[0].get('value') or {}
                if old:self.state=old
                self.previous={v['id']:(v['x'],v['y']) for v in old.get('vehicles',[])}
                return self._refresh_direct()
            value=self.transit.shared.cached(key,15,produce)
            if value:self.state=value
            return self.status()
        return self._refresh_direct()

    def _refresh_direct(self):
        with self.lock:
            if time.time()-self.last_attempt<15:return self.status()
            self.last_attempt=time.time()
            if not self.transit.budget('busin_live',6000):
                self.state['error']='시제품의 셔틀 조회 보호 한도에 도달했습니다.';return self.status()
            request=urllib.request.Request(ENDPOINT,data=json.dumps({'data':',F,'+self.route['id']+',snu_1'}).encode(),
                headers={'Content-Type':'application/json; charset=utf-8','User-Agent':'SNU-Route-Lab/0.2'})
            try:
                with urllib.request.urlopen(request,timeout=6) as response:data=json.load(response)
                if not isinstance(data.get('d'),str):raise ValueError('Unexpected shuttle response')
                vehicles=[];seen=set();changed=0;now=time.time();anchors=self.route['anchors']
                for raw in data['d'].split(';'):
                    fields=raw.split('/')
                    if len(fields)!=6:continue
                    try:identifier,x,y=fields[0],float(fields[1]),float(fields[2])
                    except (TypeError,ValueError):continue
                    if identifier in seen or not identifier or not all(math.isfinite(v) for v in (x,y)):continue
                    seen.add(identifier);position=locate(x,y,anchors)
                    if position and self.route['id']!='41841':position['direction']=self.route['direction_label']
                    before=self.previous.get(identifier);moved=before is not None and before!=(x,y)
                    changed+=int(moved);self.previous[identifier]=(x,y)
                    vehicle={'id':identifier,'route_id':'shuttle-'+self.route['id'],'route_name':self.route['name'],
                        'x':x,'y':y,'captured_at':now,'position':position,'moved_since_previous':moved}
                    if position and self.route.get('routing_live_compatible',True):
                        i=position['segment_index'];a,b=anchors[i],anchors[(i+1)%len(anchors)]
                        if position['at_stop'] and point(a):
                            parts=self.geometry.routes.get('shuttle-'+self.route['id'],{}).get('anchor_segments',[])
                            road=parts[i]['geometry'][0] if i<len(parts) and parts[i] else None
                            if road:vehicle['geographic_interval']=[road,road]
                            if a.get('coordinate_kind')=='road_reference_not_verified_stop':vehicle['coordinate_note']=a['coordinate_note']
                        elif point(a) and point(b):
                            parts=self.geometry.routes.get('shuttle-'+self.route['id'],{}).get('anchor_segments',[])
                            if i<len(parts) and parts[i]:vehicle['geographic_interval']=parts[i]['geometry']
                    vehicles.append(vehicle)
                if any(raw.strip() for raw in data['d'].split(';')) and not vehicles:raise ValueError('Unrecognized vehicle records')
                self.state={'captured_at':now,'vehicles':vehicles,'error':None,'provider_timestamp':None,'moved_observations':changed}
            except Exception:self.state['error']='실시간 조회에 연결하지 못했습니다. 이전 위치는 기준시각과 함께 표시합니다.'
            return self.status()

    def status(self):
        result={**self.state,'id':self.route['id'],'name':self.route['name'],'short_name':self.route.get('short_name',self.route['name']),'color':self.route['color'],
                'source_url':self.route['source_url'],'direction_label':self.route['direction_label'],
                'schematic_anchors':self.route['anchors'],'coordinate_note':self.route['coordinate_note']}
        result['stale']=not result.get('captured_at') or time.time()-result['captured_at']>60
        result['empty']=not result['vehicles'] and not result['error'] and not result['stale']
        result['position_kind']='schematic_stop_area_or_interval'
        result['eta_note']='정류소 구간 거리·12~25km/h·정차 여유로 추정합니다. 공식 도착예정이 아닙니다.'
        return result

    def eta_window(self,vehicle,target):
        p=vehicle.get('position');anchors=self.route['anchors'];count=len(anchors)
        if not p:return None
        start=p['segment_index']
        if p['at_stop'] and start==target:return {'at_stop':True,'seconds':[0,60]}
        next_index=(start+1)%count
        if not point(anchors[start]) or not point(anchors[next_index]):return None
        parts=self.geometry.routes.get('shuttle-'+self.route['id'],{}).get('anchor_segments',[])
        if start>=len(parts) or not parts[start]:return None
        current=parts[start]['meters']
        after=0;intermediate=0;i=next_index
        for _ in range(count):
            if i==target:break
            j=(i+1)%count
            if i>=len(parts) or not parts[i]:return None
            after+=parts[i]['meters']
            intermediate+=int(anchors[i]['board_allowed']);i=j
        else:return None
        minimum=after+(current if p['at_stop'] else 0)
        return {'at_stop':False,'seconds':[round(minimum/(25/3.6)+intermediate*10),
                                        round((after+current)/(12/3.6)+intermediate*25)]}

    def arrivals(self,stop,ready=None):
        state=self.status()
        if state['stale'] or state['error']:return []
        results=[];now=time.time()
        for vehicle in state['vehicles']:
            window=self.eta_window(vehicle,stop['anchor_index'])
            if not window:continue
            lo,hi=window['seconds'];present=window['at_stop']
            if hi>2400:continue
            planned=None
            if present and self.route['id']=='41841' and stop['anchor_index']==4:
                from shuttle import parked_admin_departure
                planned=parked_admin_departure(ready if ready is not None else now+20)
                if not planned:continue
            elif present:
                # No published exact departure for this parked vehicle.
                continue
            arrival={'departure_at':now+30 if present else vehicle['captured_at']+(lo+hi)/2,
                'vehicle_id':vehicle['id'],'provided_at':vehicle['captured_at'],'full':False,'crowd_cost':None,
                'crowd_label':'정보 없음','arrival_source':'live_shuttle','observed_interval':vehicle['position'],
                'eta_window_seconds':[lo,hi],'observed_at_stop':present,
                'prediction_note':'정류소 부근 관측 · 출발시각 미제공 · 30초 뒤 출발 가정' if present else '실시간 노선도 구간 · 거리·속도 가정으로 도착 범위 추정'}
            if planned:arrival.update(planned,vehicle_id=None,observed_vehicle_id=vehicle['id'],arrival_source='shuttle_timetable_estimate')
            if not present:arrival['earliest_departure_at']=vehicle['captured_at']+lo
            results.append(arrival)
        return sorted(results,key=lambda a:a['departure_at'])

from calculation_context import calculation_request

class ShuttleService:
    model_only=True
    def __init__(self,network,transit):
        self.transit=transit
        self.last_cache_load=0;self.cache_load_times={}
        from shuttle_timetable import ShuttleTimetable
        self.timetable=ShuttleTimetable(transit.geometry)
        self.lines={r['id']:LiveShuttle(network,transit,r) for r in CATALOG['routes']};self.routes=[]
        for spec in CATALOG['routes']:
            base=[]
            for a in spec.get('routing_stops',spec['anchors']):
                if point(a) and (a['board_allowed'] or a['alight_allowed']):
                    base.append({'id':a.get('stop_id',a.get('id')),'name':a['name'],'lat':a['lat'],'lon':a['lon'],
                        'anchor_index':a.get('index',next((n for n,x in enumerate(spec['anchors']) if x.get('stop_id')==a.get('id')),None)),
                        'board_allowed':a['board_allowed'],'alight_allowed':a['alight_allowed'],
                        'direction':spec['direction_label']})
            stops=[{**s,'seq':i+1,'board_allowed':s['board_allowed'] and i<len(base)}
                   for i,s in enumerate(base+base if spec['loop'] else base)]
            self.routes.append({'id':'shuttle-'+spec['id'],'name':spec['name'],'kind':'shuttle',
                'provider_id':spec['id'],'color':spec['color'],'stops':stops,'cycle_length':len(base) if spec['loop'] else None,
                'travel_prior':spec.get('travel_prior'),
                'capacity':spec.get('capacity',25 if spec['id']=='41914' else 60),
                'arrival_policy':'timetable_and_simulation',
                'interval_minutes':0,'source_url':spec['source_url']})

    def refresh(self):
        with ThreadPoolExecutor(max_workers=5) as pool:list(pool.map(lambda line:line.refresh(),self.lines.values()))
        return self.status()

    @calculation_request
    def status(self):
        routes=[line.status() for line in self.lines.values()]
        predictions=[];now=time.time()
        for route in self.routes:
            index=next((i for i,s in enumerate(route['stops']) if s['board_allowed'] and
                        (s['id']=='snu-410' if route['provider_id'] in ('41841','41843','41915','41942') else True)),0)
            base=self.timetable._schedule_arrival(route,index,now+20)
            item={'route_id':route['id'],'boarding_stop':route['stops'][index]['name'],
                  'model_only':True,'position_used_as_departure':False,'source_url':self.timetable.info(now)['source_url']}
            if base:
                values=self.transit.automatic_queue.arrival(route,index,now+20,[],self.timetable,now,{},True) if getattr(self.transit,'automatic_queue',None) and base['departure_at']-now<10800 else None
                value=(values or [base])[0] if values!=[] else None
                if value:item.update(expected_boarding_at=value['departure_at'],remaining_seconds=round(value['departure_at']-now),
                                     next_scheduled_departure_at=base['departure_at'] if base.get('fixed_departure') else None,
                                     automatic_queue=value.get('automatic_queue'),label='시간표·시뮬레이션 예상 승차 · 실제 출발 미확인')
                else:item['reason']='정원 시나리오에서 막차 전 승차기회를 찾지 못했습니다.'
            else:item['reason']='현재 날짜·방향의 정규 시간표 운행시간 밖입니다.'
            predictions.append(item)
        return {'routes':routes,'vehicles':[v for r in routes for v in r['vehicles']],
                'model_predictions':predictions,'arrival_policy':'timetable_and_simulation',
                'timetable':self.timetable.info(time.time()),
                'captured_at':max((r['captured_at'] or 0 for r in routes),default=0) or None,
                'stale':all(r['stale'] for r in routes),'error':'모든 셔틀 조회에 연결하지 못했습니다.' if all(r['error'] for r in routes) else None,
                'provider_timestamp':None,'source_url':CATALOG['source_route_selector'],
                'position_kind':'schematic_stop_area_or_interval','coordinate_note':'차량 GPS가 아닌 운영사 실시간 노선도 위치입니다. 예상 승차·도착은 시간표와 별도 모형으로 계산합니다.'}

    def available(self,route):
        state=self.lines[route['provider_id']].status()
        return not state['stale'] and not state['error'] and bool(state['vehicles'])

    def arrivals(self,route,index):return self.scheduled_arrivals(route,index,time.time()+20)

    def scheduled_available(self,route,at):
        from shuttle_timetable import service_day
        if route['provider_id']=='41916':return any(service_day(at-d*86400) for d in (0,1))
        return service_day(at)

    def scheduled_arrivals(self,route,index,ready):
        value=self.timetable.arrival(route,index,ready)
        return [value] if value else []

    def ready_arrivals(self,route,index,ready):
        # BUSIN observes an approach/parked area, not a departure or free seats.
        # All student shuttles therefore use the published clock + queue model.
        base=self.timetable._schedule_arrival(route,index,ready)
        if not base:return []
        # Only a moving, fresh approach to an intermediate stop can condition
        # the service clock. A terminal arrival is never a departure signal.
        if self.can_condition_clock(route,index):
            values=self.lines[route['provider_id']].arrivals(route['stops'][index],ready)
            values=[{**a,'clock_conditioning_verified':True} for a in values if a.get('arrival_source')=='live_shuttle' and not a.get('observed_at_stop') and
                    a.get('earliest_departure_at',a['departure_at'])>=ready and a['departure_at']<=base.get('last_scheduled_departure_at',float('inf'))]
            if values:return values
        return self.scheduled_arrivals(route,index,ready)

    def can_condition_clock(self,route,index):
        terminal=route['stops'][index]['id'] in ('snu-410','snu-2401','snu-2501','snu-3101','snu-3201') or index==0 or route['provider_id']=='41946' and route['stops'][index]['id']=='snu-901'
        return not terminal and self.lines[route['provider_id']].route.get('routing_live_compatible',True)

    def load_cached_positions(self,route_ids=None):
        """Read the shared last observations; never poll BUSIN or Seoul here."""
        shared=getattr(self.transit,'shared',None);now=time.time()
        if not shared or not callable(getattr(shared,'read',None)) or now-self.last_cache_load<15:return
        # A selective read must not mark the other lines as freshly loaded.
        if route_ids is None:self.last_cache_load=now
        def load(line):
            rid=line.route['id']
            if now-self.cache_load_times.get(rid,0)<15:return
            self.cache_load_times[rid]=now
            if not line.status()['stale']:return
            try:
                value=shared.read('cache-shuttle-v2-'+line.route['id'])[0].get('value')
                if value and isinstance(value.get('vehicles'),list):line.state=value
            except Exception:pass
        lines=[line for line in self.lines.values() if route_ids is None or line.route['id'] in route_ids]
        with ThreadPoolExecutor(max_workers=5) as pool:list(pool.map(load,lines))
