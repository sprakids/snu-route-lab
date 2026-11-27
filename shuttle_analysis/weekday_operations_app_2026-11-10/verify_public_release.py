"""Verify the promoted immutable app build and the published v8 model."""
import hashlib
import json
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone,timedelta
from pathlib import Path

WORK=Path(__file__).resolve().parent;OUT=WORK/'deployment';APP=WORK.parent/'app'
NAME='261110002926';SHA='6bada3eec9fa0c89386e3cbac2e3e7e90adfa2ce10f0c969c54cafd43c53fe8d'

def main():
    urls={'health':'https://snu-route-lab.vercel.app/api/health',
        'queue':'https://snu-route-lab.vercel.app/api/queue-model',
        'latest':'https://snu-shuttle-simulation.vercel.app/routing-model/latest.json',
        'methodology':'https://snu-shuttle-simulation.vercel.app/weekday-operations-methodology.html',
        'payload':'https://snu-shuttle-simulation.vercel.app/routing-model/releases/'+NAME+'.json',
        'plan':'https://snu-route-lab.vercel.app/api/plan','app':'https://snu-route-lab.vercel.app/app.js'}
    def fetch(item):
        name,url=item;body=(OUT/'stage-plan-request.json').read_bytes() if name=='plan' else None
        req=urllib.request.Request(url,data=body,headers={'Content-Type':'application/json','Accept-Encoding':'identity',
            'Cache-Control':'no-cache','User-Agent':'SNU-V8-Final-QA/1'})
        with urllib.request.urlopen(req,timeout=60) as response:raw=response.read();status=response.status
        extension='.html' if name=='methodology' else '.js' if name=='app' else '.json'
        (OUT/('final-public-'+name+extension)).write_bytes(raw)
        return name,(status,raw)
    with ThreadPoolExecutor(max_workers=4) as pool:responses=dict(pool.map(fetch,urls.items()))
    assert all(code==200 for code,raw in responses.values())
    health,queue,latest,plan=[json.loads(responses[key][1]) for key in ('health','queue','latest','plan')]
    assert health['version']=='0.22.1'
    assert queue['model_id']==latest['model_id']==plan['prediction_model']['queue_model']==NAME
    assert queue['sync']['payload_sha256']==latest['sha256']==SHA
    assert hashlib.sha256(responses['payload'][1]).hexdigest()==SHA
    assert queue['city_operations']['available'] and queue['sync']['last_error'] is None
    assert plan['prediction_model']['queue_release']['sync']['last_error'] is None
    assert not plan['calculation_data']['latest_positions_used']
    assert plan['routing_model']['city_operations']['model_id']==NAME
    legs=[l for c in plan['candidates'] for l in c['legs'] if l['type']=='bus']
    operation_legs=[l for l in legs if l.get('ride_model',{}).get('city_operations_segments')]
    assert operation_legs and all(l['ride_model']['model_id']==NAME for l in operation_legs)
    for candidate in plan['candidates']:
        assert abs(candidate['total_seconds']-sum(l['seconds'] for l in candidate['legs']))<=1
        for leg in candidate['legs']:
            for key in ('city_wait','automatic_queue'):
                if leg.get(key):assert leg[key]['model_id']==NAME
    sources=Counter(l.get('ride_model',{}).get('source') for l in legs)
    assert b'weekday-operations-methodology.html' in responses['app'][1]
    assert responses['app'][1]==(OUT/'production-app.js').read_bytes()
    protected=json.loads((OUT/'protected-assets.json').read_bytes())
    assert all(hashlib.sha256((APP/name).read_bytes()).hexdigest()==sha for name,sha in protected.items())
    receipt={'status':'PASS','checked_at':datetime.now(timezone(timedelta(hours=9))).isoformat(),
        'app_url':'https://snu-route-lab.vercel.app','simulation_url':'https://snu-shuttle-simulation.vercel.app',
        'app_deployment':'dpl_Cn7ezPkPqBjGwv6U8ZbyBdqt77Bv','previous_reader_deployment':'dpl_HpUexeWvEWnfSU3RnQavhMyWmZ1f',
        'simulation_deployment':'dpl_BQZASs4JoEzFR5PUqDQ7eeATadHC','app_version':health['version'],
        'model_id':NAME,'model_sha256':SHA,'model_bytes':len(responses['payload'][1]),'synchronized':True,
        'city_operations_available':True,'cloud_plan_candidates':len(plan['candidates']),
        'cloud_city_operations_legs':len(operation_legs),'ride_sources':dict(sources),'cloud_time_sums_reconciled':True,
        'historical_mode_uses_latest_positions':False,'methodology_http_status':200,'methodology_link_in_app':True,
        'static_bytes_match_tested_build':True,'protected_data_and_brand_files':len(protected),
        'full_python_regression_before_priority_patch':237,'priority_patch_regression_tests':61,
        'offline_real_payload_scheduled_plans':80,'target':'production','source_kind':'local_working_tree_no_commit',
        'framework':'Python API and static frontend','predictive_accuracy_on_held_out_dates_validated':False}
    (OUT/'final-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt))

if __name__=='__main__':main()
