"""Local/Vercel backend. Secrets are supplied by server environment or Windows DPAPI."""
import argparse
import csv
import io
import hashlib
import json
import math
import os
import sqlite3
import sys
import threading
import tempfile
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from routing import WalkingGraph, Planner, PRESETS, CROWD_COST
from shuttle_live import ShuttleService
from historical_forecast import HistoricalForecast
from road_geometry import RoadGeometry
from prediction import crowd_evidence
from crowd_model import CrowdModel
from collector_client import CollectorState

ROOT=Path(__file__).resolve().parent
RUNTIME=Path(tempfile.gettempdir())/'snu-route-lab' if os.environ.get('VERCEL') else ROOT/'runtime'
RUNTIME.mkdir(exist_ok=True)
KST=timezone(timedelta(hours=9))
APP_VERSION='0.6.1'
from service_state import StoragePausedState, PersistenceUnavailable
# Blob is deliberately disconnected from the runtime, including status reads.
# Keep existing store contents and credentials intact for a later explicit migration.
SHARED=CollectorState() if os.environ.get('SNU_COLLECTOR_URL') and os.environ.get('SNU_COLLECTOR_TOKEN') else StoragePausedState() if os.environ.get('VERCEL') else None
if os.name=='nt':
    sys.path.insert(0,str(ROOT.parent/'bus_api_2026-11-04'))
    from credential_store import load_key as saved_bus_key, crypt
else:
    def saved_bus_key():return None
    def crypt(*args,**kwargs):raise RuntimeError('Windows credential provisioning is not available in cloud runtime.')

# Developer-side configuration only. No key-entry form or secret POST endpoint.
env_file=ROOT/'.env'
if env_file.exists():
    for line in env_file.read_text(encoding='utf-8-sig').splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            name,value=line.split('=',1);name=name.strip()
            if name in ('SEOUL_BUS_SERVICE_KEY','KAKAO_REST_API_KEY','KAKAO_JAVASCRIPT_KEY'):
                os.environ.setdefault(name,value.strip().strip('"').strip("'"))

def secret(name):
    value=os.environ.get(name,'').strip()
    if value:return value
    # Optional developer-provisioned DPAPI payload, never an end-user key form.
    base=os.environ.get('LOCALAPPDATA')
    path=Path(base)/'SnuTransit/credentials/route_lab_settings.dpapi' if base else None
    if path and path.exists():
        try:return str(json.loads(crypt(path.read_bytes(),decrypt=True).decode()).get(name,'')).strip()
        except Exception:return ''
    return ''

@contextmanager
def db_connection():
    c=sqlite3.connect(RUNTIME/'state.sqlite3',timeout=15)
    c.execute('CREATE TABLE IF NOT EXISTS calls(day TEXT, service TEXT, created REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY, created TEXT, candidate TEXT, planned_seconds REAL, actual_seconds REAL, satisfaction INTEGER, seated TEXT, is_test INTEGER DEFAULT 0)')
    try:
        with c:
            yield c
    finally:
        c.close()

class Transit:
    def __init__(self,network):
        self.network=network;self.shared=SHARED
        self.geometry=RoadGeometry()
        self.crowd_model=CrowdModel()
        self.lock=threading.Lock();self.refresh_lock=threading.Lock()
        self.cache={};self.last_refresh=0;self.messages=[]
        self.snapshot={'captured_at':None,'vehicles':[],'routes':[],'source':'서울시 버스위치정보 OpenAPI','errors':[]}
        self.key=urllib.parse.unquote(secret('SEOUL_BUS_SERVICE_KEY') or saved_bus_key() or '')
        state=RUNTIME/'positions.json'
        if state.exists():
            try:self.snapshot=json.loads(state.read_text(encoding='utf-8'))
            except (ValueError,OSError):pass

    @staticmethod
    def now():return time.time()

    def budget(self,service,limit):
        day=datetime.now(KST).date().isoformat()
        if self.shared:return self.shared.budget(day,service,limit)
        with self.lock,db_connection() as c:
            c.execute('BEGIN IMMEDIATE')
            count=c.execute('SELECT COUNT(*) FROM calls WHERE day=? AND service=?',(day,service)).fetchone()[0]
            if count>=limit:return False
            c.execute('INSERT INTO calls VALUES(?,?,?)',(day,service,time.time()))
        return True

    def used(self,service):
        if self.shared:return self.shared.used(datetime.now(KST).date().isoformat(),service)
        with db_connection() as c:return c.execute('SELECT COUNT(*) FROM calls WHERE day=? AND service=?',(datetime.now(KST).date().isoformat(),service)).fetchone()[0]

    def position(self,route):
        return [],'위치 조회는 공용 예약 수집기가 담당합니다.'

    def refresh(self):
        return self.status()

    def fetch_arrivals(self,pair):
        if self.shared:
            route,index=pair;key=(route['id'],route['stops'][index]['seq'])
            def produce():
                self._fetch_arrivals_direct(pair)
                return self.cache.get(key,{'fetched_at':time.time(),'values':[],'error':'도착 조회 대기'})
            value=self.shared.cached('arrivals-'+route['id']+'-'+str(key[1]),60,produce)
            if value:self.cache[key]=value
            return
        return self._fetch_arrivals_direct(pair)

    def _fetch_arrivals_direct(self,pair):
        route,index=pair;stop=route['stops'][index];key=(route['id'],stop['seq'])
        current=self.cache.get(key)
        if current and time.time()-current['fetched_at']<60:return
        if not self.budget('public_arrivals',1200):
            self.cache[key]={'fetched_at':time.time(),'values':[],'error':'도착 조회 보호 한도'};return
        request=urllib.request.Request('http://m.bus.go.kr/mBus/bus/getArrInfoByRoute.bms',
            data=urllib.parse.urlencode({'stId':stop['id'],'busRouteId':route['id'],'ord':stop['seq']}).encode(),
            headers={'Content-Type':'application/x-www-form-urlencoded','User-Agent':'SNU-Route-Lab/0.1'})
        values=[];error=None
        try:
            with urllib.request.urlopen(request,timeout=4) as response:data=json.load(response)
            if str(data.get('error',{}).get('errorCode'))!='0000':raise ValueError()
            for item in data.get('resultList') or []:
                if str(item.get('busRouteId'))!=route['id'] or str(item.get('stId'))!=stop['id'] or str(item.get('staOrd'))!=str(stop['seq']):continue
                source=datetime.fromisoformat(item['mkTm']).replace(tzinfo=KST).timestamp()
                if not -5<=time.time()-source<=150:
                    error='도착예정 기준시각이 오래됐습니다.';continue
                for n in ('1','2'):
                    veh=str(item.get('vehId'+n,''));eta=int(item.get('traTime'+n) or 0)
                    if veh in ('','0') or eta<0:continue
                    division=str(item.get('rerdie_Div'+n));code=str(item.get('reride_Num'+n))
                    values.append({'departure_at':source+eta,'vehicle_id':veh,'provided_at':source,
                        'crowd_cost':CROWD_COST.get(code) if division=='4' and code in ('3','4','5') else None,
                        'crowd_label':{'3':'여유','4':'보통','5':'혼잡'}.get(code,'정보 없음') if division=='4' else '정보 없음',
                        'full':str(item.get('full'+n))=='1','message':item.get('arrmsg'+n,'')})
        except Exception:error='도착정보를 받지 못해 운행간격 시나리오를 사용합니다.'
        self.cache[key]={'fetched_at':time.time(),'values':values,'error':error}

    def prefetch(self,pairs):
        # Bounded on-demand requests, with global 60-second cache. No background polling.
        with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(self.fetch_arrivals,pairs[:24]))

    def arrivals(self,route,index):
        if route.get('kind')=='shuttle':return self.shuttle.arrivals(route,index)
        item=self.cache.get((route['id'],route['stops'][index]['seq']))
        if not item or time.time()-item['fetched_at']>150:return []
        return item['values']

    def arrival_preview(self,targets):
        if not isinstance(targets,list) or len(targets)>4:raise ValueError('조회 정류소 수를 확인해 주세요.')
        result=[]
        for target in targets:
            if not isinstance(target,dict) or not str(target.get('seq','')).isdigit():raise ValueError('정류소 순서를 확인해 주세요.')
            route=next((r for r in self.network['routes']+self.shuttle.routes if r['id']==target.get('route_id')),None)
            if route is None:raise ValueError('노선을 확인해 주세요.')
            index=next((i for i,s in enumerate(route['stops']) if s['seq']==int(target['seq'])),None)
            if index is None:raise ValueError('정류소 순서를 확인해 주세요.')
            if route.get('kind')=='shuttle':
                self.shuttle.lines[route['provider_id']].refresh();values=self.shuttle.ready_arrivals(route,index,time.time()+20);error=None
            else:
                self.fetch_arrivals((route,index));entry=self.cache.get((route['id'],route['stops'][index]['seq']),{})
                values=self.arrivals(route,index);error=entry.get('error')
            result.append({'route_id':route['id'],'seq':route['stops'][index]['seq'],'values':values[:2],'error':error})
        return {'server_time':time.time(),'stops':result,'observed_ttl_seconds':150,'position_calls_triggered':0}

    @staticmethod
    def interval(route,when):
        # Separate weekend values exist; holidays remain an explicit limitation.
        weekday=datetime.fromtimestamp(when,KST).weekday()
        if weekday>=5:
            import re
            found=re.search(r'(\d+)분\('+('토요일' if weekday==5 else '공휴일')+r'\)',route.get('interval_text',''))
            if found:return int(found.group(1))
        return route['interval_minutes']

    @staticmethod
    def in_service(route,when):
        date=datetime.fromtimestamp(when,KST)
        minutes=date.hour*60+date.minute
        first=route.get('first_time','050000');last=route.get('last_time','235900')
        start=int(first[:2])*60+int(first[2:4]);end=int(last[:2])*60+int(last[2:4])
        return start<=minutes<=end if start<=end else minutes>=start or minutes<=end

    def notes(self):
        notes=['도착예정은 서울시 공식 웹 조회 응답입니다. 별도 OpenAPI 활용승인 범위와 구분합니다.',
               '공휴일·임시 운행변경은 별도 확인이 필요합니다.']
        if any(x.get('error') for x in self.cache.values()):notes.append('일부 도착정보가 없거나 오래돼 해당 구간은 시나리오로 표시합니다.')
        if getattr(self.shared,'position_updates_paused',False):notes.append(self.shared.message)
        return notes

    def crowd_for(self,route,index,selected):
        evidence=dict(selected or {})
        if selected and route.get('kind')!='shuttle':
            if isinstance(self.shared,CollectorState):self.snapshot=self.shared.snapshot()
            v=next((v for v in self.snapshot.get('vehicles',[]) if v['route_id']==route['id'] and v['id']==selected.get('vehicle_id')),None)
            if v and (v.get('provided_at') or 0)>(evidence.get('provided_at') or 0) and str(v.get('crowd_code')) in CROWD_COST:
                evidence={k:v.get(k) for k in ('provided_at','crowd_code')}
        result=crowd_evidence(evidence,self.now())
        if result['crowd_source']!='observed' and route.get('kind')!='shuttle':
            estimate=self.crowd_model.predict(route['id'],str(route['stops'][index]['seq']),self.now(),
                result['crowd_estimate'],result['age_seconds'])
            if estimate:return estimate
        return result

    def status(self):
        if isinstance(self.shared,CollectorState):self.snapshot=self.shared.snapshot()
        result=dict(self.snapshot)
        paused=getattr(self.shared,'position_updates_paused',False)
        if paused:result.update(captured_at=None,vehicles=[],routes=[],errors=[self.shared.message])
        result.update(server_time=time.time(),position_calls_today=self.used('seoul_position'),
                      arrival_calls_today=self.used('public_arrivals'),position_app_daily_limit=result.get('position_app_daily_limit',950),
                      refresh_after_seconds=15,
                      bus_backend_configured=bool(self.key))
        result['position_updates_paused']=paused
        result['storage']=self.shared.info() if self.shared else {'mode':'sqlite','persistent':True,'observations_available':True}
        result['vehicles']=[{**v,**crowd_evidence(raw,time.time())} for raw in result.get('vehicles',[]) if (v:=self.geometry.match_vehicle(raw,time.time()))]
        result['position_calls_remaining']=max(0,result['position_app_daily_limit']-result['position_calls_today']) if result['position_calls_today'] is not None else None
        return result

class KakaoWalker:
    """Backend-only REST key. If unavailable, explicitly sourced OSM graph is used."""
    def __init__(self,fallback,transit):self.fallback=fallback;self.transit=transit;self.key=secret('KAKAO_REST_API_KEY');self.cache={}
    def walk(self,start,end):
        key=tuple(round(x,6) for x in (*start,*end))
        if key in self.cache:return self.cache[key]
        if len(self.cache)>2000:self.cache.clear()
        if self.key and start!=end and self.transit.budget('kakao_walk',800):
            params=urllib.parse.urlencode({'start_x':start[1],'start_y':start[0],'end_x':end[1],'end_y':end[0]})
            request=urllib.request.Request('https://dapi.kakao.com/v2/routing/walk?'+params,headers={'Authorization':'KakaoAK '+self.key})
            try:
                with urllib.request.urlopen(request,timeout=5) as response:data=json.load(response)
                if data.get('status')!='OK':raise ValueError()
                route=data['route'];points=[]
                for leg in route.get('legs',[]):
                    for step in leg.get('steps',[]):points.extend([[p[1],p[0]] for p in step.get('path',{}).get('points',[])])
                result={'seconds':route['properties']['totalTime'],'meters':route['properties']['totalDistance'],
                        'steps_m':0,'steps_known':False,'geometry':points,'connectors_m':0,'source':'카카오 도보 경로 API'}
                if not points:raise ValueError()
                self.cache[key]=result;return result
            except Exception:pass
        result=self.fallback.walk(start,end)
        if result and self.key:result={**result,'source':result['source']+' · 카카오 응답 실패 시 대체'}
        self.cache[key]=result;return result

class Application:
    def __init__(self):
        self.network=json.loads((ROOT/'data/network.json').read_text(encoding='utf-8'))
        self.historical=HistoricalForecast()
        self.osm_source=json.loads((ROOT/'data/walking_source.json').read_text(encoding='utf-8'))
        access=ROOT/'data/building_access.json'
        self.graph=WalkingGraph(json.loads((ROOT/'data/walking_osm.json').read_text(encoding='utf-8')),json.loads(access.read_text(encoding='utf-8')) if access.exists() else None)
        self.transit=Transit(self.network);self.transit.shuttle=ShuttleService(self.network,self.transit)
        self.walker=KakaoWalker(self.graph,self.transit)
        self.routing_network={**self.network,'routes':self.network['routes']+self.transit.shuttle.routes}
        for route in self.routing_network['routes']:
            spec=self.transit.geometry.routes.get(route['id'],{})
            route.update(geometry_segments=[s['geometry'] for s in spec.get('segments',[]) if s],geometry_source=spec.get('source'),geometry_version=self.transit.geometry.version)
        self.planner=Planner(self.routing_network,self.walker,self.transit);self.plan_lock=threading.Lock()
        self.stops={s['id']:s for r in self.network['routes'] for s in r['stops']}
        names=[('120000174','제1공학관 · 301동 앞'),('120000173','제2공학관 · 302동 앞'),
               ('120000678','행정관 정류소'),('120000192','자연대·행정관입구'),('120000190','공대입구'),
               ('120000184','관악사삼거리'),('120000186','공동기기원'),('120000197','서울대 정문')]
        self.origins=[{'id':i,'label':n,'lat':self.stops[i]['lat'],'lon':self.stops[i]['lon'],'kind':'정류소 기준'} for i,n in names if i in self.stops]
        shuttle_stops={s['id']:s for route in self.transit.shuttle.routes for s in route['stops']}
        for code,label in [('snu-410','행정관 셔틀승차장'),('snu-1001','301동 교내 셔틀정류소'),('snu-901','302동 교내 셔틀정류소'),('snu-101','정문 교내 셔틀정류소')]:
            stop=shuttle_stops[code];self.origins.append({'id':code,'label':label,'lat':stop['lat'],'lon':stop['lon'],'kind':'학교 공개 셔틀 정류소'})
        buildings=ROOT/'data/buildings_osm.json'
        if buildings.exists():
            items=json.loads(buildings.read_text(encoding='utf-8')).get('elements',[])
            building_origins=[]
            for name,label in [('제1공학관','제1공학관 · 301동'),('제2공학관','제2공학관 · 302동'),('중앙도서관','중앙도서관'),('관정도서관','관정도서관'),('행정관','행정관')]:
                found=next((b for b in items if b.get('tags',{}).get('name')==name and b.get('center')),None)
                if found:building_origins.append({'id':'building-'+str(found['id']),'label':label,
                    'lat':found['center']['lat'],'lon':found['center']['lon'],'kind':'OSM 건물 대표점 · 출입구 확인 전'})
            self.origins=building_origins+self.origins
        self.destinations=[{'id':'snu-station','label':'서울대입구역','detail':'2번 출구 앞 대표 정류소','lat':self.stops['120000150']['lat'],'lon':self.stops['120000150']['lon']},
                           {'id':'nakseongdae','label':'낙성대역','detail':'마을버스 정류소 기준','lat':self.stops['120900119']['lat'],'lon':self.stops['120900119']['lon']}]

    def bootstrap(self):
        return {'title':'서울대 하교길','version':APP_VERSION,'origins':self.origins,'destinations':self.destinations,
                'historical_prediction':self.historical.info(),
                'presets':PRESETS,'routes':self.routing_network['routes'],'status':self.transit.status(),
                'map':{'provider':'kakao' if secret('KAKAO_JAVASCRIPT_KEY') else 'osm',
                       'javascript_key':secret('KAKAO_JAVASCRIPT_KEY') or None},
                'walking':{'provider':'kakao' if self.walker.key else 'osm','source':self.osm_source,
                           'graph_nodes':len(self.graph.nodes)},
                'scope':{'routes':5,'shuttle_routes':3,'max_transfers':1,'shuttle_routing':True,
                         'shuttle_note':'행정관·교내 순환·역순환을 각각 조회합니다. 운영사 노선도 위치와 학교 정류소 좌표로 구간을 표시하며, 도착시간은 별도 추정입니다. 통과 지점은 승차 후보에서 제외합니다.'},
                'shuttle':self.transit.shuttle.status()}

    def plan(self,body):
        if body.get('origin_id'):
            origin=next((x for x in self.origins if x['id']==body['origin_id']),None)
            if not origin:raise ValueError('출발지를 선택해 주세요.')
        else:origin=body.get('origin') or {}
        point=(float(origin.get('lat',0)),float(origin.get('lon',0)))
        if not(37.438<=point[0]<=37.486 and 126.936<=point[1]<=126.970):raise ValueError('관악캠퍼스와 두 역 주변에서 출발지를 골라 주세요.')
        dest=next((x for x in self.destinations if x['id']==body.get('destination_id')),None)
        if not dest:raise ValueError('목적지를 선택해 주세요.')
        departure=float(body.get('departure_at') or time.time())
        if not math.isfinite(departure) or not time.time()-120<=departure<=time.time()+7*86400:raise ValueError('출발 시각은 현재부터 7일 이내로 선택해 주세요.')
        weights=body.get('weights') or PRESETS.get(body.get('preset','fast'),PRESETS['fast'])
        # Validate weights before doing external API work.
        rank_candidates([],weights)
        with self.plan_lock:
            historical_mode=body.get('mode')!='live' or abs(departure-time.time())>90
            if historical_mode:
                self.transit.history_snapshot=self.transit.shared.history(departure) if isinstance(self.transit.shared,CollectorState) else {}
            else:
                self.transit.history_snapshot={};self.transit.refresh()
            result=self.planner.plan(point,(dest['lat'],dest['lon']),departure,
                                    'live' if body.get('mode')=='live' else 'estimate',weights,bool(body.get('include_shuttle',True)))
            self.historical.attach(result,self.planner)
            result['calculation_data']={'mode':'historical_and_timetable' if historical_mode else 'live_with_historical_fallback',
                'latest_positions_used':not historical_mode,'history_before_date':getattr(self.transit,'history_snapshot',{}).get('before_date'),
                'note':'시간 지정은 저장된 과거 기록·공식 시간표·명시된 보완 가정으로 계산합니다.' if historical_mode else None}
            if self.graph.endpoint(point) is None:
                result['access_message']='이 지점에서 통행 가능한 보행로 연결을 확인하지 못했습니다. 건물 출입구 밖의 보행로를 출발지로 선택해 주세요.'
            result['prediction_model']={'active':self.transit.crowd_model.data.get('model_id') if self.transit.crowd_model.active else 'persistence-age-v1',
                'calibrated':self.transit.crowd_model.active,'validation_pending':None if self.transit.crowd_model.active else '28일 수집 후 날짜를 분리하여 검증합니다.'}
        from validation import error_summary
        for candidate in result['candidates']:
                context={'origin':body.get('origin_id','custom'),'destination':dest['id'],
                         'walk_50m':round(candidate['walk_m']/50),
                         'rides':[(leg['route_id'],leg['from_seq'],leg['to_seq']) for leg in candidate['legs'] if leg['type']=='bus']}
                candidate['observation_key']=hashlib.sha256(json.dumps(context,sort_keys=True).encode()).hexdigest()[:24]
        observations=SHARED.observations([c['observation_key'] for c in result['candidates']]) if isinstance(SHARED,CollectorState) else self.observations(include_test=False)
        for candidate in result['candidates']:
            errors=[row['actual_seconds']-row['planned_seconds'] for row in observations if not row.get('is_test') and row['candidate']==candidate['observation_key']]
            candidate['validation']=error_summary(errors,candidate['total_seconds'])
            if SHARED and not SHARED.info().get('observations_available'):candidate['validation']={'available':False,'n':None}
        return result

    def observations(self,include_test=False):
        if SHARED:rows=SHARED.observations()
        else:
            with db_connection() as c:
                names=('id','created','candidate','planned_seconds','actual_seconds','satisfaction','seated','is_test')
                rows=[dict(zip(names,row)) for row in c.execute('SELECT '+','.join(names)+' FROM observations ORDER BY id').fetchall()]
        return [row for row in rows if include_test or not row.get('is_test')]

    def add_observation(self,record):
        if SHARED:return SHARED.add_observation(record)
        with db_connection() as c:
            names=('created','candidate','planned_seconds','actual_seconds','satisfaction','seated','is_test')
            cur=c.execute('INSERT INTO observations('+','.join(names)+') VALUES(?,?,?,?,?,?,?)',tuple(record[key] for key in names))
            return cur.lastrowid

from routing import rank_candidates

def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version='SNU-Route-Lab'
        def log_message(self,fmt,*args):
            # Do not log query strings, request bodies, URLs containing credentials.
            print(datetime.now(KST).strftime('%H:%M:%S'),self.command,urlsplit(self.path).path,flush=True)
        def send_json(self,status,data):
            raw=json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
            public_snapshot=self.command=='GET' and urlsplit(self.path).path in ('/api/bootstrap','/api/status','/api/shuttle') and status==200
            self.send_header('Cache-Control','public, max-age=0, s-maxage=10, stale-while-revalidate=10' if public_snapshot else 'no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def allowed(self):
            hostname=self.headers.get('Host','').split(':')[0].lower()
            allowed={'localhost','127.0.0.1'}
            if os.environ.get('VERCEL'):
                allowed.update(value.lower() for value in (os.environ.get('VERCEL_URL',''),os.environ.get('VERCEL_PROJECT_PRODUCTION_URL','')) if value)
                allowed.update(value.strip().lower() for value in os.environ.get('SNU_PUBLIC_HOSTS','').split(',') if value.strip())
            return hostname in allowed
        def do_GET(self):
            if not self.allowed():return self.send_json(403,{'error':'Local host only'})
            path=urlsplit(self.path).path
            if path=='/api/bootstrap':return self.send_json(200,app.bootstrap())
            if path=='/api/status':return self.send_json(200,app.transit.status())
            if path=='/api/shuttle':return self.send_json(200,app.transit.shuttle.refresh())
            if path=='/api/forecast':
                query=urllib.parse.parse_qs(urlsplit(self.path).query)
                if not query.get('route_id'):return self.send_json(200,app.historical.info())
                try:
                    value=app.historical.point(query['route_id'][0],int(query['from_seq'][0]),
                        query['from_stop_id'][0],query['to_stop_id'][0],float(query.get('at',[time.time()])[0]))
                    return self.send_json(200,value)
                except (KeyError,ValueError,OverflowError,OSError):return self.send_json(400,{'error':'노선·정류장 순서·구간·시각을 확인해 주세요.'})
            if path=='/api/health':return self.send_json(200,{'ok':True,'app':'snu-route-lab','version':APP_VERSION,
                'historical_prediction':app.historical.info(),
                'storage':SHARED.info() if SHARED else {'mode':'sqlite','persistent':True}})
            if path=='/api/observations':
                rows=app.observations()[-100:][::-1]
                return self.send_json(200,{'records':[{k:v for k,v in row.items() if k!='is_test'} for row in rows],
                    'available':SHARED.info().get('observations_available') if SHARED else True,
                    'message':SHARED.message if SHARED else None})
            rel='index.html' if path=='/' else urllib.parse.unquote(path).lstrip('/')
            target=(ROOT/'static'/rel).resolve()
            if not target.is_relative_to((ROOT/'static').resolve()) or not target.is_file():return self.send_json(404,{'error':'Not found'})
            mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.png':'image/png','.svg':'image/svg+xml','.ico':'image/x-icon','.pdf':'application/pdf'}.get(target.suffix,'application/octet-stream')
            raw=target.read_bytes();self.send_response(200);self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(raw)));self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','strict-origin-when-cross-origin');self.end_headers();self.wfile.write(raw)
        def do_POST(self):
            if not self.allowed():return self.send_json(403,{'error':'Local host only'})
            origin=self.headers.get('Origin')
            schemes=('https://',) if os.environ.get('VERCEL') else ('http://',)
            if origin and origin not in tuple(scheme+self.headers['Host'] for scheme in schemes):return self.send_json(403,{'error':'Origin not allowed'})
            try:
                length=int(self.headers.get('Content-Length',0))
                if not 0<length<=20000:raise ValueError('요청 크기를 확인해 주세요.')
                body=json.loads(self.rfile.read(length))
                path=urlsplit(self.path).path
                if path=='/api/plan':return self.send_json(200,app.plan(body))
                if path=='/api/refresh':return self.send_json(200,app.transit.refresh())
                if path=='/api/arrivals':return self.send_json(200,app.transit.arrival_preview(body.get('targets')))
                if path=='/api/observations':
                    planned=float(body.get('planned_seconds',0));actual=float(body.get('actual_minutes',0))*60
                    satisfaction=int(body.get('satisfaction',3));seated=body.get('seated','unknown')
                    if not all(math.isfinite(x) for x in (planned,actual)) or not (0<planned<=10800 and 0<actual<=14400) or not 1<=satisfaction<=5 or seated not in ('yes','no','unknown'):
                        raise ValueError('이동시간·만족도 입력값을 확인해 주세요.')
                    name=str(body.get('candidate',''))[:120]
                    record_id=app.add_observation({'created':datetime.now(KST).isoformat(),'candidate':name,'planned_seconds':planned,
                        'actual_seconds':actual,'satisfaction':satisfaction,'seated':seated,'is_test':int(bool(body.get('is_test')))})
                    return self.send_json(201,{'saved':True,'id':record_id,'time_error_seconds':actual-planned})
                return self.send_json(404,{'error':'Not found'})
            except PersistenceUnavailable as error:return self.send_json(503,{'error':str(error),'saved':False})
            except (ValueError,TypeError,KeyError):return self.send_json(400,{'error':'입력값을 확인해 주세요. 출발지·목적지·시각과 가중치 합계를 확인해 주세요.'})
            except Exception:return self.send_json(500,{'error':'계산 중 문제가 발생했습니다. 데이터 연결 상태를 확인해 주세요.'})
    return Handler

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8840);args=parser.parse_args()
    app=Application()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),make_handler(app))
    print('SNU Route Lab: http://localhost:'+str(args.port),flush=True)
    server.serve_forever()

if __name__=='__main__':main()
