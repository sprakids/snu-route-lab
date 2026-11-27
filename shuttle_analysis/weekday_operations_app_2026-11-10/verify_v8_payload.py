"""Offline integration QA of the real release. Not predictive accuracy testing."""
import hashlib
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

WORK=Path(__file__).resolve().parent
APP=WORK.parent/'app';QA=WORK/'integration_qa'
sys.path.insert(0,str(APP))
import server
from queue_release import compatibility,content_digest,digest,validate
from queue_model_sync import LatestQueueModel,FEED
from shuttle_timetable import KST
from strategies import GATE_STOP

CANDIDATE=WORK.parent/'simulation_viewer_2026-11-07/public/routing-model/releases/261110002926.json'
EXPECTED_SHA='6bada3eec9fa0c89386e3cbac2e3e7e90adfa2ce10f0c969c54cafd43c53fe8d'

def stamp(text):return datetime.fromisoformat(text).replace(tzinfo=KST).timestamp()

def check(result,name):
    assert result['prediction_model']['queue_model']==name
    assert result['candidates']
    for candidate in result['candidates']:
        assert abs(candidate['total_seconds']-sum(l['seconds'] for l in candidate['legs']))<=1
        for leg in candidate['legs']:
            for field in ('automatic_queue','city_wait'):
                if leg.get(field):assert leg[field]['model_id']==name
            if leg.get('ride_model',{}).get('city_operations_segments'):
                assert leg['ride_model']['model_id']==name

def brief(result):
    c=result['candidates'][0]
    return {'recommended_id':c['id'],'total_seconds':c['total_seconds'],'wait_seconds':c['wait_seconds'],
        'walk_seconds':c['walk_seconds'],'ride_seconds':c['ride_seconds'],
        'routes':[l['route_name'] for l in c['legs'] if l['type']=='bus'],
        'candidates':len(result['candidates']),
        'city_operations_legs':sum(bool(l.get('ride_model',{}).get('city_operations_segments')) for c in result['candidates'] for l in c['legs']),
        'shuttle_legs':sum(l.get('mode')=='shuttle' for c in result['candidates'] for l in c['legs'])}

def main():
    QA.mkdir(exist_ok=True);raw=CANDIDATE.read_bytes();assert digest(raw)==EXPECTED_SHA
    data=json.loads(raw);base=QA/'baseline-payload.json';baseline=json.loads(base.read_bytes())
    validate(data,compatibility(baseline),check_profiles=True)
    assert content_digest(data)==data['release']['content_sha256']
    manifest={'schema':'snu_queue_release_v1',**data['release'],'bytes':len(raw),'sha256':EXPECTED_SHA,
        'payload_path':f'/routing-model/releases/{data["model"]["id"]}.json'}
    copied=QA/'candidate-payload.json'
    if copied.exists():assert copied.read_bytes()==raw
    else:copied.write_bytes(raw)
    sync=LatestQueueModel(None,base,remote=True,clock=lambda:stamp('2026-11-10T17:00:00'),
        fetch=lambda url,*args:json.dumps(manifest).encode() if url==FEED else raw)
    assert sync.info()['model_id']==data['model']['id']
    dates=['2026-11-10','2026-11-11','2026-11-12','2026-11-13','2026-11-16']
    rows=[];now=[stamp('2026-11-10T11:20:00')]
    with tempfile.TemporaryDirectory(prefix='snu-v8-qa-') as runtime,patch.object(server,'RUNTIME',Path(runtime)),patch.object(server,'secret',return_value=''),patch.object(server,'saved_bus_key',return_value=None),patch('time.time',side_effect=lambda:now[0]),patch('urllib.request.urlopen',side_effect=AssertionError('No provider access in model QA')) as network:
        app=server.Application();t=app.transit;t.shared=None;t.refresh=lambda:None;t.prefetch=lambda pairs:None
        t.arrivals=lambda r,i:[];t.snapshot={};t.plan_snapshot={};t.history_snapshot={};app.walker.key=''
        t.shuttle.load_cached_positions=lambda *args:None
        models={}
        for label,path in ([] if '--live-only' in sys.argv else [('old',base),('v8',copied)]):
            t.automatic_queue=LatestQueueModel(app.historical,path,remote=False);name=t.automatic_queue.config['id']
            for date in dates:
                for origin in ('snu-410','120000174'):
                    for destination in app.destinations:
                        body={'origin_id':origin,'destination_id':destination['id'],'departure_at':stamp(date+'T17:00:00'),
                            'mode':'estimate','include_shuttle':True}
                        result=app.plan(body);check(result,name)
                        assert result['calculation_data']['latest_positions_used'] is False
                        key=(date,origin,destination['id']);models[label,key]=brief(result)
            print(label+' 40 scheduled plans PASS',flush=True)
        for key in sorted(k[1] for k in models if k[0]=='old'):
            old,new=models['old',key],models['v8',key]
            rows.append({'date':key[0],'origin':key[1],'destination':key[2],'old':old,'v8':new,
                'delta_total_seconds':new['total_seconds']-old['total_seconds'],
                'delta_wait_seconds':new['wait_seconds']-old['wait_seconds']})
        if rows:(QA/'scheduled-plan-comparison.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
        t.automatic_queue=LatestQueueModel(app.historical,copied,remote=False);now[0]=stamp('2026-11-10T17:00:00')
        point=next(s for route in app.network['routes'] for s in route['stops'] if s['id']==GATE_STOP)
        def arrivals(route,index):
            if route['stops'][index]['id']!=GATE_STOP:return []
            return [{'departure_at':now[0]+300,'provided_at':now[0],'vehicle_id':'qa-observed-'+route['id'],
                'arrival_source':'live','full':False,'crowd_cost':0,'crowd_label':'여유'}]
        t.arrivals=arrivals
        result=app.plan({'origin':point,'destination_id':'snu-station','departure_at':now[0],
            'mode':'live','include_shuttle':False})
        check(result,data['model']['id']);live_legs=[]
        for candidate in result['candidates']:
            for leg in candidate['legs']:
                if leg.get('station_id')!=GATE_STOP or not leg.get('city_wait'):continue
                # A later transfer may have missed this real bus; its fallback
                # is then expected to use the operations clock instead.
                if leg['ready_at']>now[0]+300:continue
                c=leg['city_wait'];assert abs(c['base_departure_at']-(now[0]+300))<1e-6,(leg['route_id'],leg['ready_at']-now[0],c['base_departure_at']-now[0])
                if c['extra_wait_seconds']==0:assert leg['vehicle_id']=='qa-observed-'+leg['route_id']
                live_legs.append({'route_id':leg['route_id'],'base_eta_seconds':300,'extra_wait_seconds':c['extra_wait_seconds']})
        assert live_legs
        assert network.call_count==0
    report={'status':'PASS','kind':'real_payload_offline_integration_not_out_of_sample_accuracy',
        'candidate_id':data['model']['id'],'sha256':EXPECTED_SHA,'bytes':len(raw),
        'baseline_id':baseline['model']['id'],'scheduled_plans':80 if rows else 0,'distinct_weekdays':5 if rows else 0,
        'origins':2,'destinations':4,'live_eta_base_preserved_legs':live_legs,'rows':rows,
        'provider_calls':0,'production_changed':False,'latest_public_pointer_changed':False}
    output='v8-live-verification.json' if '--live-only' in sys.argv else 'v8-integration-verification.json'
    (QA/output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','live_eta_base_preserved_legs')}))

if __name__=='__main__':main()
