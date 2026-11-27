"""Check the public route contract for all returned transit options and save compact evidence."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
from pathlib import Path
import time
from check_endpoints import request_plan, RELEASE

CASES = [
    ('terminal','snu-410','snu-station','2026-12-01T15:23:00','shuttle-41841'),
    ('town','snu-410','daehak-town','2026-12-01T15:18:00','shuttle-41843'),
    ('sparse','snu-410','snu-station','2026-12-04T15:48:00','shuttle-41841'),
    ('night','snu-410','snu-station','2026-12-01T21:09:00','shuttle-41915'),
    ('weekend','snu-901','snu-station','2026-11-28T15:23:00',None),
    ('morning','snu-3101','snu-station','2026-12-01T09:00:00','shuttle-41868'),
    ('live','snu-410','snu-station',None,None),
]


def check(url,cli,case):
    name,origin,dest,clock,required = case
    at = datetime.fromisoformat(clock+'+09:00').timestamp() if clock else time.time()
    body={'origin_id':origin,'destination_id':dest,'departure_at':at,'mode':'estimate' if clock else 'live'}
    plan=request_plan(url,json.dumps(body).encode(),cli)
    assert plan['prediction_model']['queue_model']==RELEASE and plan['routing_model']['model_id']==RELEASE
    assert plan['live_predictions_used']==(clock is None)
    rows={}
    for c in plan['candidates']:
        assert c['total_seconds']==sum(l['seconds'] for l in c['legs'])
        for leg in c['legs']:
            if leg['type']!='bus':continue
            rid=leg['route_id']
            q=leg.get('automatic_queue') or leg['city_wait']
            assert q['model_id']==RELEASE and leg['arrival_forecast']['model_id']==RELEASE
            assert leg['departure_at']>=leg['ready_at'] and leg['arrival_at']>=leg['departure_at']
            item={'route':rid,'release':q['model_id'],'basis':q.get('basis') or q.get('source') or q['simulation']['basis']}
            if q.get('join_at')==at:item.update(outside=q['join_to_board_seconds'],dwell=q['onboard_before_departure_seconds'],mass=q.get('boarded_mass'))
            if rid not in rows or 'outside' in item:rows[rid]=item
    assert rows and (required is None or required in rows)
    if name=='terminal':assert (rows[required]['outside'],rows[required]['dwell'])==(158,68)
    if name=='town':assert (rows[required]['outside'],rows[required]['dwell'])==(22,383)
    if name=='sparse':assert 0<rows[required]['mass']<1
    if name=='weekend':assert not any(r.startswith('shuttle') for r in rows)
    return dict(case=name,request=body,candidates=len(plan['candidates']),routes=rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('url');parser.add_argument('output',type=Path);parser.add_argument('--cli')
    args=parser.parse_args()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda c:check(args.url,args.cli,c),CASES))
    args.output.write_text(json.dumps({'url':args.url,'release':RELEASE,'cases':results},ensure_ascii=False,indent=2),encoding='utf8')
    print([(x['case'],x['candidates'],len(x['routes'])) for x in results])
