"""Signed, snapshot-pinned R comparisons. Never selects a public recommendation.

The browser starts a separate request after V11 has rendered. Exact location and
walk geometry are transient ticket inputs only and are never written to storage.
"""
import base64, copy, hashlib, hmac, importlib.util, json, math, threading, time, types, uuid, zlib
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from calculation_context import calculation_context, calculation_now

ROOT=Path(__file__).resolve().parent
MANIFEST=json.loads((ROOT/'shadow_transport/manifest.json').read_text(encoding='utf-8'))
MODEL=MANIFEST['shadow_model']
MAX_TICKET=1500000
MAX_RAW=10000000
TTL=180
_RUN_LOCK=threading.Lock()

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()

def shuttle_provider(body,authorization,shared):
    """Collector-only regional network bridge. The DO reserves calls first."""
    from shuttle_live import CATALOG,ENDPOINT
    from concurrent.futures import ThreadPoolExecutor
    import urllib.request
    if not shared or not shared.token or not hmac.compare_digest(authorization or '', 'Bearer '+shared.token):
        return {'error':'Unauthorized'},401
    routes=body.get('routes');known={r['id'] for r in CATALOG['routes']}
    if not isinstance(routes,list) or not 1<=len(routes)<=10 or len(set(routes))!=len(routes) or any(r not in known for r in routes):
        return {'error':'invalid_routes'},400
    def fetch(rid):
        req=urllib.request.Request(ENDPOINT,data=json.dumps({'data':',F,'+rid+',snu_1'}).encode(),
            headers={'Content-Type':'application/json; charset=utf-8','User-Agent':'SNU-Route-Lab/shuttle-archive-1'})
        try:
            with urllib.request.urlopen(req,timeout=6) as response:raw=response.read(200001)
            if len(raw)>200000:raise ValueError('too_large')
            value=json.loads(raw)
            if not isinstance(value.get('d'),str):raise ValueError('bad_envelope')
            return rid,{'d':value['d']}
        except Exception:return rid,{'error':'shuttle_provider_unavailable'}
    with ThreadPoolExecutor(max_workers=5) as pool:values=dict(pool.map(fetch,routes))
    return {'routes':values,'regional_proxy':True},200

def encode_ticket(payload,key):
    raw=canonical(payload)
    if len(raw)>MAX_RAW:raise ValueError('shadow_input_too_large')
    data=zlib.compress(raw,6)
    if len(data)>MAX_TICKET//2:raise ValueError('shadow_ticket_too_large')
    return base64.urlsafe_b64encode(data).decode()+'.'+hmac.new(key.encode(),data,hashlib.sha256).hexdigest()

def decode_ticket(ticket,key,now=None):
    if not isinstance(ticket,str) or len(ticket)>MAX_TICKET:raise ValueError('invalid_shadow_ticket')
    encoded,signature=ticket.rsplit('.',1)
    data=base64.b64decode(encoded,altchars=b'-_',validate=True)
    if not hmac.compare_digest(hmac.new(key.encode(),data,hashlib.sha256).hexdigest(),signature):raise ValueError('shadow_signature')
    inflater=zlib.decompressobj();raw=inflater.decompress(data,MAX_RAW+1)
    if len(raw)>MAX_RAW or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:raise ValueError('shadow_input_limit')
    value=json.loads(raw);now=time.time() if now is None else now
    if not isinstance(value.get('issued_at'),(int,float)) or not 0<=now-value['issued_at']<=TTL:raise ValueError('shadow_ticket_expired')
    if value.get('candidate')!=MODEL:raise ValueError('shadow_version_mismatch')
    return value

@contextmanager
def capture_walks(planner):
    values={};old=getattr(planner,'walk_observer',None)
    planner.walk_observer=lambda key,value:values.setdefault(key,value)
    try:yield values
    finally:planner.walk_observer=old

def summarize(result):
    rows=[]
    for rank,c in enumerate(result.get('candidates',[])[:40],1):
        buses=[l for l in c.get('legs',[]) if l.get('type')=='bus']
        route=[{'route_id':b.get('route_id'),'from_seq':b.get('from_seq'),'to_seq':b.get('to_seq'),
                'station_id':b.get('station_id'),'ready_at':b.get('ready_at'),'departure_at':b.get('departure_at'),
                'wait_seconds':max(0,b.get('departure_at',0)-b.get('ready_at',0)),
                'ride_seconds':b.get('seconds'),'crowd_estimate':b.get('crowd_estimate'),
                'crowd_risk':b.get('crowd_risk'),'arrival_source':b.get('arrival_source'),
                'ride_source':b.get('ride_model',{}).get('source'),
                'queue_at_arrival':(b.get('automatic_queue') or {}).get('queue_at_arrival')} for b in buses]
        identity={'kind':'common_gate' if c.get('common_gate_service') else 'route',
                  'walk_seconds':c.get('walk_seconds'),
                  'rides':sorted(c['common_gate_service']['eligible_route_ids']) if c.get('common_gate_service') else
                          [(b.get('route_id'),b.get('from_seq'),b.get('to_seq')) for b in buses]}
        rows.append({'candidate_id':c.get('id'),'comparison_key':hashlib.sha256(canonical(identity)).hexdigest()[:24],
                     'rank':rank,'route_ids':[b.get('route_id') for b in buses],
                     'total_seconds':c.get('total_seconds'),'walk_seconds':c.get('walk_seconds'),
                     'wait_seconds':c.get('wait_seconds'),'ride_seconds':sum(b.get('seconds',0) for b in buses),
                     'score':c.get('score'),'legs':route})
    return {'model_id':result.get('prediction_model',{}).get('queue_model'),'candidates':rows,
            'recommended_candidate_id':(result.get('strategy_comparison') or {}).get('recommended_candidate_id'),
            'calculation_ms':result.get('performance',{}).get('total_ms')}

def make_frame(app,body,result,point,dest,departure,weights,report,context,walks):
    transit=app.transit;selected=transit.automatic_queue.current()
    mixed=hasattr(transit.automatic_queue.operations,'profile') or any((leg.get('automatic_queue') or {}).get('source')=='terminal_wait_v12' or
              (leg.get('vehicle_supply') or {}).get('basis')=='v12_terminal_dispatch_schedule'
              for c in result['candidates'] for leg in c['legs'])
    frame={'id':uuid.uuid4().hex,'issued_at':time.time(),'candidate':MODEL,'asof':calculation_now(),
            'queue_id':selected.config['id'],'queue_sha256':getattr(selected,'payload_sha256',None),
            'snapshot':transit.snapshot,'plan_snapshot':getattr(transit,'plan_snapshot',{}),
            'history_snapshot':getattr(transit,'history_snapshot',{}),
            'arrivals':[[list(k),v] for k,v in transit.cache.items() if calculation_now()-v.get('fetched_at',0)<=600],
            'shuttles':{rid:line.state for rid,line in transit.shuttle.lines.items()},
            'walks':[[list(k),v] for k,v in walks.items()],
            'point':point,'destination':dest,'destination_id':body['destination_id'],'departure':departure,'weights':weights,'mode':body.get('mode'),
            'include_shuttle':bool(body.get('include_shuttle',True)),'report':report,'context':context,
            'baseline':None if mixed else summarize(result),'public_result_changed':False}
    return copy.deepcopy(frame)

@lru_cache(maxsize=2)
def private_clock_module(name):
    # A private module object, so pinning a clock cannot mutate V11's globals.
    spec=importlib.util.spec_from_file_location('_shadow_'+name,ROOT/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.time=types.SimpleNamespace(time=calculation_now)
    return module

class FrozenWalker:
    def __init__(self,rows):self.values={tuple(k):v for k,v in rows};self.missing=0
    def walk(self,start,end):
        key=tuple(round(x,6) for x in (*start,*end))
        if key not in self.values:self.missing+=1;return None
        return self.values[key]

def run_candidate(app,frame,shuttle_profile=None):
    from server import Transit
    from routing import Planner
    from shadow_transport.review_runtime import load_review_model
    from shadow_transport.candidate_runtime import install_candidate,common_gate_adapter
    from gate_service import add_common_gate
    from strategies import compare_strategies
    from shadow_shuttle import ShadowQueue,ShuttleTravel
    # Never deepcopy a live lock or share mutable V11 caches with this planner.
    selected=app.transit.automatic_queue.current()
    if selected.config['id']!=frame['queue_id'] or getattr(selected,'payload_sha256',None)!=frame['queue_sha256']:
        raise ValueError('pinned_V11_release_unavailable')
    class FrozenTransit(Transit):
        def prefetch(self,pairs):return None
        def fetch_arrivals(self,pair):raise RuntimeError('shadow_provider_request_forbidden')
        def refresh(self):return self.snapshot
        def budget(self,*args):return False
        def arrivals(self,route,index):
            if route.get('kind')=='shuttle':return self.shuttle.arrivals(route,index)
            item=self.cache.get((route['id'],route['stops'][index]['seq']))
            if not item or self.now()-item['fetched_at']>150:return []
            return [v for v in item['values'] if v.get('provided_at') and -5<=self.now()-v['provided_at']<=150]
    transit=copy.copy(app.transit);transit.__class__=FrozenTransit;transit.shared=None;transit.key=None
    transit.snapshot=frame['snapshot'];transit.plan_snapshot=frame['plan_snapshot'];transit.history_snapshot=frame['history_snapshot']
    transit.cache={tuple(k):v for k,v in frame['arrivals']};transit.messages=[]
    transit.continuity=app.transit.continuity.__class__()
    transit.crowd_model=app.transit.crowd_model.__class__()
    historical=copy.copy(app.historical);historical.references=copy.deepcopy(app.historical.references)
    from automatic_queue import AutomaticQueue
    transit.automatic_queue=AutomaticQueue(historical,data=selected.data) if frame['baseline'] is None else selected
    transit.shuttle=private_clock_module('shuttle_live').ShuttleService(app.network,transit)
    transit.shuttle.refresh=lambda:None;transit.shuttle.load_cached_positions=lambda *args:None
    for rid,line in transit.shuttle.lines.items():line.state=frame['shuttles'].get(rid,line.state)
    walker=FrozenWalker(frame['walks']);planner=Planner(app.routing_network,walker,transit)
    planner.travel=private_clock_module('travel_time').TravelTime(geometry=transit.geometry)
    planner.travel.operations=lambda:transit.automatic_queue.operations
    def calculate():
        with calculation_context(frame['asof']):
            plan=planner.plan(tuple(frame['point']),tuple(frame['destination']),frame['departure'],frame['mode'],
                              frame['weights'],frame['include_shuttle'],frame['report'],frame['context'])
            historical.attach(plan,planner)
            plan['strategy_comparison']=compare_strategies(plan,frame['destination_id']=='snu-station')
        plan['prediction_model']={'queue_model':frame['queue_id']}
        return plan
    # The archive compares V11 and R on the same inputs even when the public
    # route used V12 at the terminal. Replay V11 only for those mixed plans.
    baseline=frame['baseline'] or summarize(calculate())
    transit.automatic_queue=ShadowQueue(historical,data=selected.data,profile=shuttle_profile or {},asof=frame['asof'])
    profile=load_review_model();enabled={'headway','ride','gate'}|({'crowd'} if 'crowd' in profile.accepted else set())
    network_hash=hashlib.sha256((ROOT/'data/network.json').read_bytes()).hexdigest()
    install_candidate(planner,profile,enabled,network_hash,patch_gate=False)
    planner.common_gate_service=common_gate_adapter(add_common_gate,profile,enabled)
    planner.travel=ShuttleTravel(planner.travel,shuttle_profile or {},frame['asof'])
    started=time.perf_counter()
    result=calculate()
    result['performance']={'total_ms':round((time.perf_counter()-started)*1000,1)}
    if walker.missing:raise ValueError('pinned_walk_candidate_set_incomplete')
    candidate=summarize(result)
    def key(c):return c['comparison_key']
    left={key(c):c for c in baseline['candidates']};right={key(c):c for c in candidate['candidates']}
    changes=[]
    for k in left.keys()&right.keys():
        a,b=left[k],right[k];changes.append({'V11_candidate_id':a['candidate_id'],'R_candidate_id':b['candidate_id'],'comparison_key':k,
            **{name:round((b.get(name) or 0)-(a.get(name) or 0),3) for name in ('total_seconds','wait_seconds','ride_seconds','rank')}})
    return {'status':'complete','comparison_id':frame['id'],'created_at':time.time(),'asof':frame['asof'],
            'departure_at':frame['departure'],'mode':frame['mode'],'operating_model':'V11','operating_queue_id':frame['queue_id'],
            'candidate_model':MODEL,'transport_source_model':MANIFEST['source_model'],'automatic_promotion':False,
            'same_observation_snapshot':True,'new_provider_requests':0,'baseline':baseline,'candidate':candidate,
            'matched_candidate_deltas':changes,'unmatched_V11':len(left.keys()-right.keys()),'unmatched_R':len(right.keys()-left.keys()),
            'shuttle_profile_before_date':(shuttle_profile or {}).get('before_date'),
            'shuttle_corrections':transit.automatic_queue.corrections,
            'accuracy_validation':False,'comparison_kind':'paired_predictions_not_independent_actual_outcomes'}

def shadow_request(app,body,shared):
    frame=decode_ticket(body.get('ticket'),shared.token)
    if not _RUN_LOCK.acquire(blocking=False):return {'saved':False,'reason':'shadow_worker_busy'}
    try:return _shadow_request_locked(app,frame,shared)
    finally:_RUN_LOCK.release()

def _shadow_request_locked(app,frame,shared):
    claim=shared.request('/shadow/claim',{'id':frame['id']})
    if not claim.get('allowed'):return {'saved':False,'reason':'duplicate_or_daily_storage_limit'}
    try:
        from shadow_shuttle import wanted_pairs
        profile=shared.request('/shuttle/profile',{'when':frame['departure'],'asof':frame['asof'],
                                                'pairs':wanted_pairs(app,frame)})
        if profile.get('catalog_source_sha256')!=hashlib.sha256((ROOT/'data/shuttle_network.json').read_bytes()).hexdigest():
            profile={'before_date':profile.get('before_date'),'routes':{},'catalogue_mismatch':True}
        value=run_candidate(app,frame,profile)
    except Exception as error:
        # No exception string: it could accidentally include transient input.
        value={'status':'failed','comparison_id':frame['id'],'candidate_model':MODEL,'operating_model':'V11',
               'automatic_promotion':False,'reason':str(error) if isinstance(error,ValueError) and str(error) in
               ('pinned_V11_release_unavailable','pinned_walk_candidate_set_incomplete') else 'shadow_calculation_failed'}
    saved=shared.request('/shadow/record',{'id':frame['id'],'comparison':value})
    return {'saved':bool(saved.get('saved')),'status':value['status'],'candidate_model':MODEL,'operating_model':'V11'}
