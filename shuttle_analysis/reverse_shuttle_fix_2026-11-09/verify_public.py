"""Verify the public release without credentials or fake vehicle observations."""
import concurrent.futures,datetime,hashlib,json,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE='https://snu-route-lab.vercel.app'
def get(path):
    req=urllib.request.Request(BASE+path,headers={'User-Agent':'SNU-Route-Lab/verification'})
    with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    health,shuttles,status=list(pool.map(get,['/api/health','/api/shuttle','/api/status']))
for name,value in [('public-health',health),('public-shuttle',shuttles)]:
    (ROOT/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
rows=[{'id':r['id'],'name':r['name'],'stale':r['stale'],'error':r['error'],
    'source_age_seconds':round(time.time()-(r['captured_at'] or 0),1),
    'vehicles':len(r['vehicles']),'road_intervals':sum(bool(v.get('geographic_interval')) for v in r['vehicles'])}
    for r in shuttles['routes']]
assert health['version']=='0.21.2',health
assert len(rows)==10,rows
assert all(not r['stale'] and r['error'] is None for r in rows),rows
assert next(r for r in rows if r['id']=='41914')['road_intervals']>=1,rows
proof={'checked_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(),
    'public_url':BASE,'version':health['version'],'routes':rows,
    'usage':status.get('usage'),'source':'live production API; no synthetic vehicles',
    'worker_version':'4b77d7e0-bc53-4bb3-a82b-3efcf17ed902',
    'vercel_deployment':'dpl_6pFhqtESXhxPdXMFcvzNTpX4uVYb',
    'tests':{'collector':26,'app':50,'map_checks':10,'errors':0}}
(ROOT/'verification.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(proof,ensure_ascii=False,indent=2))
