"""Paired model-only comparison using one read-only frozen observation bundle."""
import concurrent.futures,copy,datetime,hashlib,json,sys,time,urllib.request
from pathlib import Path
from unittest.mock import patch

OUT=Path(__file__).resolve().parent
BASE=OUT.parent
APP=BASE/'app'
sys.path.insert(0,str(APP));sys.path.insert(0,str(BASE/'collector'))
import server
from export_history import credentials
from collector_client import CollectorState
from automatic_queue import AutomaticQueue
from queue_release import validate,compatibility

MODELS={'old':'261109152540','new':'261109173153'}
KST=datetime.timezone(datetime.timedelta(hours=9))
def save(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()

class FrozenCollector(CollectorState):
    def __init__(self,bundle):
        self.bundle=bundle;self.available=True;self.position_updates_paused=False;self.message=''
    def request(self,*args,**kwargs):raise AssertionError('Frozen comparison cannot make a network request')
    def snapshot(self):return copy.deepcopy(self.bundle['snapshot'])
    def history(self,when):return copy.deepcopy(self.bundle['history'])
    def read(self,key):return {'value':copy.deepcopy(self.bundle['cache'].get(key.removeprefix('cache-')))},None
    def used(self,day,service):
        s=self.bundle['snapshot'];return s['position_calls_today'] if service=='seoul_position' else s['service_calls'].get(service,0)
    def budget(self,*args):raise AssertionError('Provider collection is forbidden in a paired comparison')
    def cached(self,*args):raise AssertionError('Provider collection is forbidden in a paired comparison')
    def observations(self,*args):return []
    def info(self):return {'available':True,'observations_available':False,'mode':'frozen_read_only_replay'}

def application(bundle,model):
    server.SHARED=FrozenCollector(bundle)
    server.RUNTIME=OUT/'runtime';server.RUNTIME.mkdir(exist_ok=True)
    app=server.Application();app.walker.key='';app.transit.key=''
    app.transit.automatic_queue=AutomaticQueue(app.historical,data=model)
    app.transit.prefetch=lambda pairs:None
    for key,value in bundle['cache'].items():
        if key.startswith('arrivals-') and value:
            rid,seq=key.removeprefix('arrivals-').rsplit('-',1)
            app.transit.cache[(rid,int(seq))]=copy.deepcopy(value)
    return app

def row(c):
    rides=[l for l in c['legs'] if l['type']=='bus']
    return {'id':c['id'],'strategy':c['strategy'],'route_names':c['route_names'],
        'total_seconds':c['total_seconds'],'walk_seconds':c['walk_seconds'],
        'wait_seconds':c['wait_seconds'],'ride_seconds':c['ride_seconds'],
        'boarding_seconds':c['boarding_seconds'],'walk_m':c['walk_m'],'score':c['score'],
        'boardings':[{'route_id':l['route_id'],'name':l['route_name'],'stop':l['from_name'],'stop_id':l['station_id'],
            'to':l['to_name'],'departure_at':l['departure_at'],'ready_at':l['ready_at'],
            'arrival_source':l['arrival_source'],'queue':l.get('automatic_queue'),'city_wait':l.get('city_wait')} for l in rides]}

def summarize(plan):
    by_strategy={}
    for c in plan['candidates']:
        key=c['strategy']
        if key not in by_strategy or c['total_seconds']<by_strategy[key]['total_seconds']:by_strategy[key]=c
    return {'model_id':plan['prediction_model']['queue_model'],
        'recommended':row(plan['candidates'][0]),'fastest':row(min(plan['candidates'],key=lambda c:c['total_seconds'])),
        'strategies':{k:row(v) for k,v in by_strategy.items()},'candidate_count':len(plan['candidates'])}

def calculate(bundle,model,departure,mode='live'):
    app=application(bundle,model)
    body={'origin_id':'snu-410','destination_id':'snu-station','departure_at':departure,
        'preset':'fast','mode':mode,'include_shuttle':True}
    with patch('time.time',return_value=departure),patch('urllib.request.urlopen',side_effect=AssertionError('No network during replay')):
        result=app.plan(body)
    for c in result['candidates']:
        assert abs(c['total_seconds']-sum(l['seconds'] for l in c['legs']))<=1,(c['id'],'time sum')
        assert abs(c['total_seconds']-sum(c[k] for k in ['walk_seconds','wait_seconds','ride_seconds','boarding_seconds']))<=1
    return result

def main():
    model_data={};file_sha={}
    for label,mid in MODELS.items():
        path=BASE/'simulation_viewer_2026-11-07/public/routing-model/releases'/(mid+'.json')
        raw=path.read_bytes();data=json.loads(raw);validate(data,compatibility(data),check_profiles=True)
        assert data['model']['id']==mid
        model_data[label]=data;file_sha[label]=hashlib.sha256(raw).hexdigest()
    settings=lambda d:{k:v for k,v in d['model'].items() if k!='id'}
    assert settings(model_data['old'])==settings(model_data['new']),'More than model inputs changed'
    creds=credentials();shared=CollectorState(creds['url'],creds['token'])
    before=time.time()
    snapshot=shared.request('/snapshot');history=shared.history(before)
    bundle={'snapshot':snapshot,'history':history,'cache':{}}
    app=application(bundle,model_data['old'])
    origin=next(o for o in app.origins if o['id']=='snu-410');dest=next(d for d in app.destinations if d['id']=='snu-station')
    patterns=app.planner.patterns((origin['lat'],origin['lon']),(dest['lat'],dest['lon']),True,before,unpruned=True)
    pairs=[]
    for p in patterns:
        for n,(rid,i,j) in enumerate(p['rides']):
            route=app.planner.by_id[rid]
            if route.get('kind')=='shuttle':continue
            if n==0 and not app.transit.in_service(route,before+p['first_walk']['seconds']+20):continue
            extra=[x for x in [(rid,i),(rid,j)] if x not in pairs]
            if len(pairs)+len(extra)<=16:pairs.extend(extra)
    keys=['shuttle-v2-'+r['provider_id'] for r in app.transit.shuttle.routes]
    keys+=['arrivals-'+rid+'-'+str(app.planner.by_id[rid]['stops'][i]['seq']) for rid,i in pairs]
    def read(key):return key,shared.read('cache-'+key)[0].get('value')
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:bundle['cache']=dict(pool.map(read,keys))
    departure=int(time.time())
    bundle.update(asof=departure,capture_started_at=before,capture_completed_at=departure)
    save('frozen-inputs.json',bundle)
    plans={label:calculate(bundle,data,departure) for label,data in model_data.items()}
    assert digest(bundle)==digest(json.loads((OUT/'frozen-inputs.json').read_text(encoding='utf-8'))),'Inputs mutated'
    result={label:summarize(plan) for label,plan in plans.items()}
    # A second old-model run must reproduce the same comparisons exactly.
    assert summarize(calculate(bundle,model_data['old'],departure))==result['old'],'Replay is not deterministic'
    for label,plan in plans.items():save(label+'-plan.json',plan)
    notes={'departure_kst':datetime.datetime.fromtimestamp(departure,KST).isoformat(),
        'origin':'행정관 셔틀승차장','destination':'서울대입구역 2번 출구 앞 대표 정류소','preset':'fast',
        'weights':server.PRESETS['fast'],'walking_kmh':4.8,'observation_bundle_sha256':digest(bundle),
        'model_payload_sha256':file_sha,'model_settings_equal_excluding_id':True,
        'seoul_position_calls_triggered':0,'provider_calls_triggered':0,
        'frozen_position_vehicle_records':len(snapshot.get('vehicles',[])),
        'arrival_cache_entries_read':len(pairs),'arrival_cache_entries_found':sum(bool(bundle['cache'].get(key)) for key in keys if key.startswith('arrivals-')),
        'source_age_seconds':departure-(snapshot.get('captured_at') or departure),
        'repeat_old_model_exact':True,'results':result}
    save('comparison.json',notes)
    compact={k:v for k,v in notes.items() if k!='results'}
    compact['results']={label:{**value,'strategies':{k:{kk:vv for kk,vv in v.items() if kk!='boardings'} for k,v in value['strategies'].items()},
        'recommended':{k:v for k,v in value['recommended'].items() if k!='boardings'},
        'fastest':{k:v for k,v in value['fastest'].items() if k!='boardings'}} for label,value in result.items()}
    print(json.dumps(compact,ensure_ascii=True,indent=2))

if __name__=='__main__':main()
