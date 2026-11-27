"""Check model adoption in the public app and actual route-calculation output."""
import datetime,json,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
APP='https://snu-route-lab.vercel.app'
EXPECTED='261109173153'
def request(url,body=None):
    req=urllib.request.Request(url,data=json.dumps(body).encode() if body else None,
        headers={'User-Agent':'SNU-Route-Lab/verification','Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=60) as response:return json.load(response)
manifest=request('https://snu-shuttle-simulation.vercel.app/routing-model/latest.json')
info=request(APP+'/api/queue-model')
body={'origin_id':'snu-410','destination_id':'snu-station','departure_at':time.time(),
    'preset':'fast','mode':'live','include_shuttle':True}
started=time.perf_counter();plan=request(APP+'/api/plan',body);elapsed=time.perf_counter()-started
for name,value in [('manifest',manifest),('queue-model',info),('request',body),('plan',plan)]:
    (ROOT/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
legs=[l for c in plan['candidates'] for l in c['legs']]
queue=[l['automatic_queue'] for l in legs if l.get('automatic_queue')]
city=[l['city_wait'] for l in legs if l.get('city_wait')]
assert manifest['model_id']==EXPECTED and info['sync']['active_model_id']==EXPECTED
assert info['sync']['payload_sha256']==manifest['sha256']
assert info['sync']['last_error'] is None
assert plan['prediction_model']['queue_model']==EXPECTED
assert plan['prediction_model']['queue_release']['sync']['active_model_id']==EXPECTED
assert plan['prediction_model']['queue_release']['latest_simulation']['source_simulation']=='capacity_v7'
assert queue,'actual route candidates must use the queue model, not just metadata'
assert all(q['model_id']==EXPECTED for q in queue)
assert city and all(q['model_id']==EXPECTED for q in city)
summary={'checked_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(),
    'app_version':'0.21.2','active_model_id':info['sync']['active_model_id'],
    'payload_sha256':info['sync']['payload_sha256'],'source_simulation':info['release']['source_simulation'],
    'candidate_count':len(plan['candidates']),'shuttle_queue_legs':len(queue),'city_wait_legs':len(city),
    'actual_shuttle_queue_model_ids':sorted(set(q['model_id'] for q in queue)),
    'actual_city_wait_model_ids':sorted(set(q['model_id'] for q in city)),
    'automatic_queue_applied':plan['automatic_queue_applied'],'city_wait_model_applied':plan['city_wait_model_applied'],
    'elapsed_seconds':round(elapsed,3),'app_redeployment_required':False,
    'observed_queue':info['observed_queue'],'independent_empirical_validation':info['latest_simulation']['gate_access_calibration']['independent_empirical_validation']}
(ROOT/'verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=True,indent=2))
