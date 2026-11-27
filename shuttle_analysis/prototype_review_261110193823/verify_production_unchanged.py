"""Read public V11 endpoints and current mobile assets. No deploy or model writes."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib,json,urllib.request
ROOT=Path(__file__).resolve().parent
SIM=ROOT.parent/'simulation_viewer_2026-11-07'
MODEL='261110162302'
PAYLOAD='f39be2fbe61185f198ac27da9b8b57565cccfb80824e0a4f8f65f68915cbd130'
MANIFEST='ca0b1b487879586a6ca5ed79511e9bd3128f423a95eb18f471d06b4885d55dbc'
def digest(data):return hashlib.sha256(data).hexdigest()
def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'SNU-prototype-readonly-verification/1.0','Accept-Encoding':'identity'})
    with urllib.request.urlopen(req,timeout=25) as response:return response.status,response.read()
def main():
    target=ROOT/'production_unchanged_verification.json';assert not target.exists()
    assert digest((SIM/'public/routing-model/latest.json').read_bytes())==MANIFEST
    lab='https://snu-shuttle-simulation.vercel.app/'
    jobs=[('lab_latest',lab+'routing-model/latest.json'),('data_latest','https://snu-shuttle-v9-data.vercel.app/routing-model/latest.json'),
          ('route_api','https://snu-route-lab.vercel.app/api/queue-model')]
    jobs += [(name,lab+name) for name in ('index.html','viewer-v5.js','mobile-lab.js','mobile-lab.css')]
    result={'status':'STARTED','checked_at':datetime.now(timezone.utc).isoformat(),'expected_model_id':MODEL,
            'expected_payload_sha256':PAYLOAD,'production_writes':False,'responses':[]}
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            replies=list(pool.map(lambda pair:fetch(pair[1]),jobs))
        for (name,url),(status,body) in zip(jobs,replies):
            item={'name':name,'url':url,'status':status,'bytes':len(body),'sha256':digest(body)}
            assert status==200
            if name.endswith('_latest'):
                d=json.loads(body);assert d['model_id']==MODEL and digest(body)==MANIFEST
                item['model_id']=d['model_id']
            elif name=='route_api':
                d=json.loads(body);sync=d['sync'];assert d['model_id']==MODEL and sync['active_model_id']==MODEL
                assert sync['status']=='active' and sync['last_error'] is None and sync['payload_sha256']==PAYLOAD
                item.update(model_id=d['model_id'],sync_status=sync['status'],payload_sha256=sync['payload_sha256'])
            else:
                assert digest(body)==digest((SIM/'public'/name).read_bytes()),name
                item['local_public_asset_match']=True
            result['responses'].append(item)
        result['status']='PASS_V11_UNCHANGED_AND_MOBILE_ASSETS_MATCH'
    except Exception as exc:
        result.update(status='FAILED_READBACK',error=type(exc).__name__,message=str(exc));raise
    finally:target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(result['status'],MODEL)
if __name__=='__main__':main()
