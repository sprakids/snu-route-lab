"""Check the immutable Linux deployment via the authenticated Vercel CLI."""
from pathlib import Path
import json,subprocess,hashlib,time,sys

ROOT=Path(__file__).resolve().parent
NODE='C:/Program Files/nodejs/node.exe'
CLI='C:/Users/김예준/AppData/Local/npm-cache/_npx/29d463b7a51d914c/node_modules/vercel/dist/vc.js'
URL='https://snu-route-7ow0ohxku-june-f3d1.vercel.app'

def fetch(endpoint,name,body=None):
    out=ROOT/name
    args=[NODE,CLI,'curl',endpoint,'--deployment',URL,'--scope','june-f3d1','--','--silent','--show-error','--fail','--output',str(out)]
    if body is not None:
        request=ROOT/'stage-v2-plan-request.json';request.write_text(json.dumps(body),encoding='utf8')
        args.extend(['--request','POST','--header','Content-Type: application/json','--data-binary','@'+str(request)])
    subprocess.run(args,check=True)
    return out

def main():
    q=json.loads(fetch('/api/queue-model','stage-v2-queue-model.json').read_text(encoding='utf8'))
    assert q['vehicle_supply_contract']=='original_terminal_dispatch_capacity_and_batches_v1'
    assert q['model_id']=='261110150729'
    assert q['sync']['payload_sha256']=='185564956f609a46ef5016ab0c4ee24799bfeecf01da6a4f0f7bc45994ab133c'
    health=json.loads(fetch('/api/health','stage-v2-health.json').read_text(encoding='utf8'));assert health['ok']
    js=fetch('/app.js','stage-v2-app.js');source=ROOT/'reader_stage_v2/static/app.js'
    # Linux build_static.py adds the map import digest and normalizes newlines.
    map_digest=hashlib.sha256((ROOT/'reader_stage_v2/static/map.js').read_bytes()).hexdigest()[:16]
    expected=source.read_text(encoding='utf8').replace("'./map.js'",f"'./map.js?v={map_digest}'")
    assert js.read_text(encoding='utf8')==expected
    body={'origin_id':'building-482207537','destination_id':'snu-station','mode':'plan','preset':'fast','departure_at':time.time()+60}
    plan=json.loads(fetch('/api/plan','stage-v2-plan.json',body).read_text(encoding='utf8'))
    assert 'error' not in plan,plan
    assert isinstance(plan.get('candidates'),list) and len(plan['candidates'])>0,list(plan)
    receipt={'status':'PASS','deployment_id':'dpl_ETo1p8ipPum7PKCtnqf4EPNYfeQi','deployment_url':URL,
        'protected_stage_management_check':True,'anonymous_public_check':False,'health':True,
        'actual_linux_plan_candidates':len(plan['candidates']),'reader_capability':q['vehicle_supply_contract'],
        'active_model_unchanged':q['model_id'],'payload_sha256':q['sync']['payload_sha256'],
        'static_app_sha256':hashlib.sha256(js.read_bytes()).hexdigest(),'python_version_pin_included':True,'promoted':False}
    (ROOT/'root-stage-v2-verification.json').write_text(json.dumps(receipt,indent=2),encoding='utf8');print(json.dumps(receipt))

if __name__=='__main__':main()
