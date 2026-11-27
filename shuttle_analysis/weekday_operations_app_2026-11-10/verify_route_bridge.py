"""Offline end-to-end bridge checks with explicitly synthetic v4 clock fixtures."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

WORK=Path(__file__).resolve().parent
sys.path.insert(0,str(WORK/'app_candidate'))
sys.path.insert(0,str(WORK.parent/'bus_api_2026-11-04'))
import server
from automatic_queue import AutomaticQueue
from test_city_operations import fixture,release_data,at
from strategies import GATE_STOP
from queue_release import digest,encode

def main():
    spec,network,_=fixture()
    for route in network['routes']:
        r=spec['routes'][route['id']];r['stops']=[{k:s[k] for k in ('id','seq')} for s in route['stops']]
        n=len(r['stops'])-1
        r['segment_profiles']={str(d):[[0,61200,[60]*n],[61200,172800,[120]*n]] for d in range(5)}
    data=release_data(spec)
    data['city_wait']['profiles']={key:[] for key in data['city_wait']['profiles']}
    now=at('2026-11-10T17:00:00');app=server.Application();transit=app.transit
    transit.automatic_queue._active=AutomaticQueue(app.historical,data=data)
    transit.automatic_queue._active.payload_sha256=digest(encode(data))
    transit.automatic_queue._remote=False
    transit.prefetch=lambda pairs:None;transit.refresh=lambda:None
    transit.snapshot={};transit.plan_snapshot={};transit.history_snapshot={}
    point=next(s for r in network['routes'] for s in r['stops'] if s['id']==GATE_STOP)
    request={'origin':point,'destination_id':'snu-station','departure_at':now,'mode':'estimate','include_shuttle':False}
    with patch('time.time',return_value=now),patch('urllib.request.urlopen',side_effect=AssertionError('No upstream calls')):
        estimated=app.plan(request)
        common=next(c for c in estimated['candidates'] if c.get('common_gate_service'))
        assert common['common_gate_service']['kind']=='first_modeled_boardable_bus'
        assert estimated['routing_model']['city_operations']['model_id']==data['model']['id']
        modeled=[l for c in estimated['candidates'] for l in c['legs'] if l.get('ride_model',{}).get('city_operations_segments')]
        assert modeled
        assert all(l['ride_model']['model_id']==data['model']['id'] for l in modeled)
        def arrivals(route,index):
            if route['stops'][index]['id']!=GATE_STOP:return []
            return [{'departure_at':now+300,'provided_at':now,'vehicle_id':'fixture-observed-'+route['id'],
                'arrival_source':'live','crowd_cost':0,'crowd_label':'여유','full':False}]
        transit.arrivals=arrivals
        observed=app.plan({**request,'mode':'live'})
        live_common=next(c for c in observed['candidates'] if c.get('common_gate_service'))
        assert live_common['common_gate_service']['kind']=='first_observed_boardable_bus'
        bus=next(l for l in live_common['legs'] if l['type']=='bus')
        assert bus['departure_at']==now+300 and bus['vehicle_id'].startswith('fixture-observed-')
        for result in (estimated,observed):
            assert result['prediction_model']['queue_model']==data['model']['id']
            for candidate in result['candidates']:
                assert abs(candidate['total_seconds']-sum(l['seconds'] for l in candidate['legs']))<=1
    report={'status':'PASS','kind':'synthetic_end_to_end_not_observed_accuracy','model_id':data['model']['id'],
        'checks':['estimated_common_gate_preserves_irregular_clock','live_eta_keeps_vehicle_and_departure',
            'travel_and_queue_share_release','walk_wait_ride_boarding_reconcile'],
        'estimated_candidates':len(estimated['candidates']),'live_candidates':len(observed['candidates']),
        'upstream_calls':0,'production_changed':False}
    (WORK/'route-bridge-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
