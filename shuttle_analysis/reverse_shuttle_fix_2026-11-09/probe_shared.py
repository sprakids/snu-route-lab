"""Read-only diagnosis; never print credentials or reserve provider calls."""
import json,sys,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'collector'))
from export_history import credentials
c=credentials()
def read(path,body=None):
    req=urllib.request.Request(c['url']+path,data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization':'Bearer '+c['token'],'Content-Type':'application/json','User-Agent':'SNU-Route-Lab/0.4'})
    try:
        with urllib.request.urlopen(req,timeout=15) as response:return json.load(response)
    except urllib.error.HTTPError as error:
        body=error.read().decode(errors='replace')
        try:body=json.loads(body)
        except ValueError:body=body[:200]
        return {'http_status':error.code,'body':body}
snapshot=read('/snapshot')
print(json.dumps({'budget_zero_probe':read('/budget',{'service':'busin_live','limit':0}),
    'usage':snapshot.get('usage'),'service_calls':snapshot.get('service_calls')},ensure_ascii=False))
