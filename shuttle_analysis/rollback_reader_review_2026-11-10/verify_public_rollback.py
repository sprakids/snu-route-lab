"""Run only after the simulation owner confirms rollback promotion."""
import argparse
import copy
import hashlib
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone,timedelta
from pathlib import Path

WORK=Path(__file__).resolve().parent;APP=WORK.parent/'app';OUT=WORK/'public_verification'
SOURCE=WORK.parent/'simulation_viewer_2026-11-07/deployment/realtime_autoplay_261109175408'
sys.path.insert(0,str(APP))
from queue_release import content_digest,compatibility

NAME='261110005327'
SHA='6e5a1e6fbf879b0e7552f57745b47f2f38fc8d3f0834de9c101cb4050c729031'
CONTENT='57cc1bc6822b804598155fe91b78f59cd591cb6e0c0e2341366c3255409a4d06'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report-path');args=parser.parse_args()
    OUT.mkdir(exist_ok=True)
    sim='https://snu-shuttle-simulation.vercel.app';app='https://snu-route-lab.vercel.app'
    urls={'health':app+'/api/health','queue':app+'/api/queue-model','latest':sim+'/routing-model/latest.json',
        'payload':sim+'/routing-model/releases/'+NAME+'.json','viewer':sim+'/viewer-v5.js',
        'common':sim+'/data/capacity_v7/common.json','methodology':sim+'/methodology.html',
        'gate_methodology':sim+'/gate-access-methodology.html','app_js':app+'/app.js'}
    if args.report_path:
        assert args.report_path.startswith('/') and not args.report_path.startswith('//')
        urls['repair_report']=sim+args.report_path
    def fetch(item):
        name,url=item
        req=urllib.request.Request(url,headers={'Cache-Control':'no-cache','Accept-Encoding':'identity','User-Agent':'SNU-V7-Rollback-QA/1'})
        with urllib.request.urlopen(req,timeout=40) as response:raw=response.read();status=response.status;encoding=response.headers.get('Content-Encoding')
        (OUT/(name+'.response')).write_bytes(raw)
        return name,{'raw':raw,'status':status,'encoding':encoding}
    with ThreadPoolExecutor(max_workers=4) as pool:responses=dict(pool.map(fetch,urls.items()))
    assert all(v['status']==200 for v in responses.values())
    h,q,m,p=[json.loads(responses[n]['raw']) for n in ('health','queue','latest','payload')]
    assert h['version']=='0.22.1'
    assert q['model_id']==m['model_id']==p['model']['id']==NAME
    assert q['sync']['payload_sha256']==m['sha256']==hashlib.sha256(responses['payload']['raw']).hexdigest()==SHA
    assert q['sync']['last_error'] is None and q['sync']['status']=='active'
    assert q['algorithm_id']=='latest-v5-all-shuttle-clock-fifo-v3' and not q['city_operations']['available']
    assert m['source_simulation']=='capacity_v7' and 'city_operations' not in p
    old=json.loads((WORK.parent/'weekday_operations_app_2026-11-10/integration_qa/baseline-payload.json').read_bytes())
    normalized=copy.deepcopy(p);normalized['model']['id']=old['model']['id'];normalized['release']=old['release']
    assert normalized==old and content_digest(p)==content_digest(old)==CONTENT
    assert compatibility(p)==compatibility(old)==m['compatibility_sha256']
    assert "||'capacity_v7'" in responses['viewer']['raw'].decode('utf-8')
    # This preserved static deployment intentionally serves the exact Brotli file.
    assert responses['common']['encoding']=='br'
    assert responses['common']['raw']==(SOURCE/'public/data/capacity_v7/common.json.br').read_bytes()
    kst=timezone(timedelta(hours=9));now=datetime.now(kst);departure=now.replace(hour=17,minute=0,second=0,microsecond=0)
    if departure.timestamp()<now.timestamp()+60:departure+=timedelta(days=1)
    while departure.weekday()>4:departure+=timedelta(days=1)
    body={'origin_id':'snu-410','destination_id':'snu-station','mode':'estimate',
        'departure_at':departure.timestamp(),'include_shuttle':True}
    req=urllib.request.Request(app+'/api/plan',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','User-Agent':'SNU-V7-Rollback-QA/1'},method='POST')
    with urllib.request.urlopen(req,timeout=60) as response:raw=response.read();plan_status=response.status
    (OUT/'plan.response').write_bytes(raw);result=json.loads(raw)
    assert plan_status==200 and result['prediction_model']['queue_model']==NAME and result['candidates']
    assert not result['routing_model']['city_operations']['available']
    assert not result['calculation_data']['latest_positions_used']
    assert result['prediction_model']['queue_release']['sync']['last_error'] is None
    for c in result['candidates']:
        assert abs(c['total_seconds']-sum(l['seconds'] for l in c['legs']))<=1
        for leg in c['legs']:
            assert not leg.get('ride_model',{}).get('city_operations_segments')
            for key in ('city_wait','automatic_queue'):
                if leg.get(key):assert leg[key]['model_id']==NAME
    assert b'queueModel?.city_operations?.available' in responses['app_js']['raw']
    baseline=json.loads((WORK.parent/'weekday_operations_app_2026-11-10/deployment/source-files-priority.json').read_bytes())
    assert all(hashlib.sha256((APP/name).read_bytes()).hexdigest()==sha for name,sha in baseline.items())
    report={'status':'PASS','checked_at':datetime.now(kst).isoformat(),'app_version':h['version'],
        'restored_model_id':NAME,'original_model_id':'261109173153','source_simulation':'capacity_v7',
        'payload_sha256':SHA,'content_sha256':CONTENT,'original_v7_computational_content_equal':True,
        'viewer_default':'capacity_v7','v8_operations_disabled':True,'sync_error':q['sync']['last_error'],
        'cloud_plan_candidates':len(result['candidates']),'cloud_time_sums_reconciled':True,
        'specified_time_uses_latest_positions':False,'v7_brotli_common_bytes_equal':True,
        'methodology_http_status':responses['methodology']['status'],
        'gate_methodology_http_status':responses['gate_methodology']['status'],
        'v8_only_app_guide_link_hidden_by_model_state':True,
        'repair_report_http_status':responses.get('repair_report',{}).get('status'),
        'app_source_files_unchanged':len(baseline),'new_app_deployment':False,
        'this_verifier_modifies_alias_or_latest':False}
    (OUT/'receipt.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))

if __name__=='__main__':main()
