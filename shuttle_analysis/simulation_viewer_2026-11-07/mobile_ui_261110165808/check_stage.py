from pathlib import Path
import json,hashlib,subprocess,sys
TASK=Path(__file__).resolve().parent;ROOT=TASK.parent
NODE='C:/Program Files/nodejs/node.exe';CLI='C:/Users/김예준/AppData/Local/npm-cache/_npx/29d463b7a51d914c/node_modules/vercel/dist/vc.js'
URL=sys.argv[1] if len(sys.argv)>1 else 'https://snu-shuttle-simulation-5kf2ikk7f-june-f3d1.vercel.app'
RECEIPT=sys.argv[2] if len(sys.argv)>2 else 'root-stage-verification.json'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    stage=ROOT/json.loads((ROOT/'peak_pair_correction_2026-11-10/ui-stage.json').read_text(encoding='utf8'))['directory']
    paths=['index.html','viewer-v5.js','mobile-lab.js','mobile-lab.css','routing-model/latest.json','routing-model/releases/261110162302.json']
    result=[]
    for i,name in enumerate(paths):
        out=TASK/f'{Path(RECEIPT).stem}-response-{i}.bin'
        subprocess.run([NODE,CLI,'curl',URL+'/'+name,'--scope','june-f3d1','--','--silent','--show-error','--fail','--output',str(out)],cwd=stage,check=True)
        expected=(ROOT/'public'/name).read_bytes();assert sha(out.read_bytes())==sha(expected),name
        result.append({'path':name,'sha256':sha(expected)})
    latest=json.loads((ROOT/'public/routing-model/latest.json').read_text(encoding='utf8'))
    assert latest['model_id']=='261110162302' and latest['sha256']=='f39be2fbe61185f198ac27da9b8b57565cccfb80824e0a4f8f65f68915cbd130'
    receipt={'status':'PASS','deployment_url':URL,'protected_stage_check':True,
        'changed_assets_and_model_pointer_verified':True,'model_id':latest['model_id'],'results':result}
    (TASK/RECEIPT).write_text(json.dumps(receipt,indent=2),encoding='utf8');print(json.dumps(receipt))

if __name__=='__main__':main()
