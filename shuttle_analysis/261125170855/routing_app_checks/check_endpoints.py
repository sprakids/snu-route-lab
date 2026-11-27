"""Compare identical public-planner requests and keep only aggregate route times."""
import argparse
import json
import subprocess
import tempfile
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parents[1]/'app'
RELEASE = 'V261125170855'
CASES = [
    ('snu-410','snu-station','2026-12-01T15:23','shuttle-41841'),
    ('snu-410','daehak-town','2026-12-01T15:18','shuttle-41843'),
    ('campus-11C0600','snu-station','2026-12-01T15:23','shuttle-41841'),
    ('snu-410','snu-station','2026-11-28T15:23','shuttle-41841'),
    ('snu-410','snu-station','2026-11-26T21:10','shuttle-41915'),
]


def request_plan(url, payload, cli):
    if cli is None:
        req=urllib.request.Request(url+'/api/plan',data=payload,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=65) as response:
            return json.load(response)
    with tempfile.TemporaryDirectory() as tmp:
        body=Path(tmp)/'body.json'
        body.write_bytes(payload)
        output=Path(tmp)/'plan.json'
        subprocess.run(['node',cli,'curl','/api/plan','--deployment',url,'--scope','june-f3d1','--',
                        '--silent','--show-error','--fail','--header','Content-Type: application/json',
                        '--data-binary','@'+str(body),'--output',str(output)],
                       cwd=APP,check=True,timeout=80)
        return json.loads(output.read_bytes())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('output',type=Path)
    parser.add_argument('--cli')
    parser.add_argument('--v12',action='store_true')
    args=parser.parse_args()
    results=[]
    for origin,dest,clock,route in CASES:
        depart=datetime.fromisoformat(clock+':00+09:00').timestamp()
        payload={'origin_id':origin,'destination_id':dest,'departure_at':depart,'mode':'estimate','preset':'fast'}
        plan=request_plan(args.url,json.dumps(payload).encode(),args.cli)
        assert not plan['live_predictions_used']
        candidates=[(c,b) for c in plan['candidates'] for b in c['legs'] if b.get('route_id')==route
                    and b.get('station_id')=='snu-410' and len(c['route_names'])==1]
        record={'request':payload,'route_id':route,'clock_kst':clock,'ranked_candidates':len(plan['candidates'])}
        if clock.startswith('2026-11-28'):
            assert not candidates
            record['service']='weekend_no_regular_shuttle'
        else:
            c,b=min(candidates,key=lambda row:row[0]['total_seconds'])
            q=b['automatic_queue']
            row={'wait_model':q['model_id'],'total_seconds':c['total_seconds'],'walk_seconds':c['walk_seconds'],
                 'ride_seconds':c['ride_seconds'],'ready_at':b['ready_at'],'depart_at':b['departure_at'],
                 'expected_wait_seconds':q['expected_wait_seconds'],'queue_mean_people':q.get('queue_at_arrival'),
                 'join_minute':q.get('join_minute'),'join_to_board_seconds':q.get('join_to_board_seconds'),
                 'onboard_before_departure_seconds':q.get('onboard_before_departure_seconds')}
            if args.v12 and route in ('shuttle-41841','shuttle-41843'):
                assert q['model_id']==RELEASE and not q['observed_queue']
                assert b['ready_at']==q['join_at']+20 and b['departure_at']==q['join_at']+q['join_to_board_seconds']+q['onboard_before_departure_seconds']
                assert b['arrival_forecast']['expected_boarding_at']==b['boarding_at']
                assert row['join_minute']==(925 if origin=='campus-11C0600' else 923 if dest=='snu-station' else 918)
                if origin=='snu-410':
                    assert (row['join_to_board_seconds'],row['onboard_before_departure_seconds'])==((158,68) if dest=='snu-station' else (22,383))
            else:
                assert q['model_id']!=RELEASE
            record.update(row)
        results.append(record)
    args.output.write_text(json.dumps({'url':args.url,'cases':results},ensure_ascii=False,indent=2),encoding='utf-8')
    print([(r['route_id'],r.get('wait_model'),r.get('join_to_board_seconds'),r.get('onboard_before_departure_seconds')) for r in results])


if __name__=='__main__':
    main()
