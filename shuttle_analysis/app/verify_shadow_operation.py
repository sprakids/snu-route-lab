"""End-to-end transport integration on real campus paths, with no provider polls.

The V11 input is the immutable public release. Empty/frozen observations below
are integration fixtures; the resulting comparison is not field validation.
"""
from pathlib import Path
import copy,hashlib,json,sys,time,urllib.request
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent
OUT=ROOT.parent/'shadow_operation_261116'
from automatic_queue import AutomaticQueue
from queue_model_sync import LatestQueueModel
from calculation_context import calculation_context
from collector_client import CollectorState
import server
from shadow_runtime import decode_ticket,run_candidate,summarize

def main():
    public=OUT/'V11_261110162302.json'
    if not public.exists():
        with urllib.request.urlopen('https://snu-shuttle-simulation.vercel.app/routing-model/releases/261110162302.json',timeout=30) as response:raw=response.read()
        data=json.loads(raw);assert data['model']['id']=='261110162302';public.write_bytes(raw)
    raw=public.read_bytes();app=server.Application()
    queue=LatestQueueModel(app.historical,remote=False)
    queue._active=AutomaticQueue(app.historical,data=json.loads(raw));queue._sha256=hashlib.sha256(raw).hexdigest();queue._active.payload_sha256=queue._sha256
    app.transit.automatic_queue=queue
    class FixtureStore(CollectorState):
        def __init__(self):super().__init__('https://fixture.invalid','fixture-only-not-a-real-secret');self.available=True
        def snapshot(self):return {'captured_at':None,'vehicles':[],'routes':[],'errors':[],'travel_history':{},'traffic':{}}
        def history(self,when):return {}
        def observations(self,*args,**kwargs):return []
        def budget(self,*args,**kwargs):raise AssertionError('Provider budget must never be consumed in this fixture')
        def info(self):return {'observations_available':True}
    shared=FixtureStore();app.transit.shared=shared;app.transit.refresh=lambda:None;app.transit.prefetch=lambda *a:None;app.walker.key=None
    app.transit.shuttle.load_cached_positions=lambda *args:None
    app.transit.snapshot=shared.snapshot()
    import gate_service
    original_gate=gate_service.add_common_gate
    at=time.time();rows=[]
    for origin,delay in [('snu-410',0),('120000174',0),('120000197',0),('snu-410',86400)]:
        body={'origin_id':origin,'destination_id':'snu-station','departure_at':at+delay,'mode':'estimate' if delay else 'live','preset':'fast','include_shuttle':True}
        with patch.object(server,'SHARED',shared),patch('time.time',return_value=at),patch('urllib.request.urlopen',side_effect=AssertionError('Unexpected provider/network request')):
            before=app.plan(body);assert before.get('shadow'),origin
            frame=decode_ticket(before['shadow']['ticket'],shared.token,at)
            before_digest=hashlib.sha256(json.dumps(summarize(before),sort_keys=True).encode()).hexdigest()
            start=time.perf_counter();value=run_candidate(app,frame,{});elapsed=time.perf_counter()-start
            learned=None
            if origin=='snu-410' and not delay:
                from datetime import datetime
                from shuttle_timetable import KST
                sample_hour=datetime.fromtimestamp(at,KST).hour
                samples=[{'lo':270,'hi':330,'seconds':300,'day':day,
                    'known_at':datetime.fromisoformat(day+f'T{sample_hour:02d}:00:00').replace(tzinfo=KST).timestamp(),
                    'at':datetime.fromisoformat(day+f'T{sample_hour:02d}:00:00').replace(tzinfo=KST).timestamp()} for day in ['2026-11-10','2026-11-11'] for _ in range(4)]
                profile={'before_date':'2026-11-16','routes':{'shuttle-41841':{'rides':{'4:8':samples},
                    'headways':{'departure:4:towards_station':samples}}}}
                learned=run_candidate(app,frame,profile)
                assert learned['shuttle_corrections'],'Supported historical shuttle data were not applied to R'
            assert value['status']=='complete';assert gate_service.add_common_gate is original_gate
            after=app.plan(body)
            a,b=summarize(before),summarize(after);a.pop('calculation_ms',None);b.pop('calculation_ms',None)
            assert a==b,'R changed V11 recommendations'
            assert queue._active.config['id']=='261110162302'
            text=json.dumps(value)
            for name in ['"lat"','"lon"','"geometry"','"point"','"ticket"']:assert name not in text,name
            assert value['new_provider_requests']==0
            rows.append({'origin_id':origin,'mode':body['mode'],'V11_candidates':len(before['candidates']),'R_candidates':len(value['candidate']['candidates']),
                         'matched':len(value['matched_candidate_deltas']),'R_elapsed_seconds':round(elapsed,3),
                         'ticket_bytes':len(before['shadow']['ticket']),'V11_unchanged':True,'provider_polls':0,
                         'comparison':value,'synthetic_shuttle_support_check':learned})
    result={'passed':True,'scope':'real campus walk/road integration; frozen empty observation fixture, not field accuracy',
            'V11_sha256':hashlib.sha256(raw).hexdigest(),'cases':rows}
    (OUT/'integration_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'cases':[{k:v for k,v in r.items() if k not in ('comparison','synthetic_shuttle_support_check')} for r in rows]}))

if __name__=='__main__':main()
