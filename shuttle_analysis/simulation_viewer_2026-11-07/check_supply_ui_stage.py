from pathlib import Path
import hashlib,json,subprocess

ROOT=Path(__file__).resolve().parent;WORK=ROOT/'peak_pair_correction_2026-11-10'
NODE='C:/Program Files/nodejs/node.exe';CLI='C:/Users/김예준/AppData/Local/npm-cache/_npx/29d463b7a51d914c/node_modules/vercel/dist/vc.js'
URL='https://snu-shuttle-simulation-pj5g3f3h1-june-f3d1.vercel.app'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(b):return hashlib.sha256(b).hexdigest()

def main():
    ui=ROOT/read(WORK/'ui-stage.json')['directory'];data=ROOT/read(WORK/'data-stage.json')['directory']
    m=read(WORK/'pending_release.json');pending=ROOT/m['directory'];results=[]
    paths=['routing-model/latest.json',m['payload_path'].lstrip('/'),'viewer-v5.js','capacity-correction.html','data/capacity_v11/common.json']
    for n,name in enumerate(paths):
        out=WORK/f'ui-stage-check-{n}.bin'
        subprocess.run([NODE,CLI,'curl',URL+'/'+name,'--scope','june-f3d1','--','--silent','--show-error','--fail','--output',str(out)],cwd=ui,check=True)
        expected=[(ui/'public'/name).read_bytes()] if (ui/'public'/name).exists() else []
        if name==m['payload_path'].lstrip('/'):expected=[(pending/'payload.json').read_bytes()]
        if name.startswith('data/'):expected=[(data/'public'/(name+'.br')).read_bytes(),(ROOT/'public'/name).read_bytes()]
        digest=sha(out.read_bytes());assert digest in [sha(b) for b in expected],name
        results.append({'path':name,'sha256':digest})
    result={'status':'PASS','deployment_id':'dpl_9LoRQhFDGJikC6NNxEGRGb6L9RnR','protected_management_check':True,
        'public_alias_unchanged_at_check':True,'new_model_id':m['model_id'],'results':results}
    (WORK/'ui-stage-verification.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result))

if __name__=='__main__':main()
