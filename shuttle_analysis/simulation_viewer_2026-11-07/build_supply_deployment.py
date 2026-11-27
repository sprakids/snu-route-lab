"""Append v11 to the split public archive without rewriting old immutable data."""
from pathlib import Path
from datetime import datetime
import argparse,json,shutil,subprocess,re,hashlib

ROOT=Path(__file__).resolve().parent
WORK=ROOT/'peak_pair_correction_2026-11-10'
BASE_UI=ROOT/'deployment/walk_choices_ui_261110150729_150929'
BASE_DATA=ROOT/'deployment/walk_choices_data_261110150729'
REMOTE='https://snu-shuttle-v9-data.vercel.app'
NODE='C:/Program Files/nodejs/node.exe'

def read(p):return json.loads(p.read_text(encoding='utf8'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
def manifest():
    m=read(WORK/'pending_release.json')
    assert m['source_simulation']=='capacity_v11'
    pending=ROOT/m['directory']
    assert hashlib.sha256((pending/'payload.json').read_bytes()).hexdigest()==m['sha256']
    return m,pending

def clone(base,stage):
    assert not stage.exists(),stage
    stage.mkdir(parents=True);shutil.copytree(base/'public',stage/'public')
    for name in ('vercel.json','.vercelignore'):
        shutil.copy2(base/name,stage/name)
    if (base/'.vercel/project.json').exists():
        (stage/'.vercel').mkdir();shutil.copy2(base/'.vercel/project.json',stage/'.vercel/project.json')

def preserve(base,stage):
    count=0
    for folder in ('data','routing-model/releases'):
        for p in (base/'public'/folder).rglob('*'):
            if p.is_file():
                assert p.read_bytes()==(stage/'public'/p.relative_to(base/'public')).read_bytes(),str(p)
                count+=1
    return count

def data_stage():
    m,pending=manifest();stage=ROOT/'deployment'/f"supply_data_{m['model_id']}_{datetime.now():%H%M%S}"
    clone(BASE_DATA,stage);tasks=[]
    for dataset,names in [('capacity_v11',['common','charts',*[f'{s}-{d}' for s in ('regular','peak') for d in ('mon','tue','wed','thu','fri')]]),
                          ('half_hour_v1',['capacity_v11']),('capacity_review_v1',['report'])]:
        for name in names:
            src=ROOT/'public/data'/dataset/f'{name}.json';dst=stage/'public/data'/dataset/f'{name}.json.br'
            raw=src.read_bytes();json.loads(raw)
            assert not re.search(rb'C:[\\/]|(?:api|service)[_-]?key=|BEGIN [A-Z ]*PRIVATE KEY',raw,re.I),str(src)
            dst.parent.mkdir(parents=True,exist_ok=True);tasks.append([str(src),str(dst)])
    taskpath=WORK/'brotli-v11-tasks.json';save(taskpath,tasks)
    compressor="""const fs=require('fs'),z=require('zlib'),u=require('util'),assert=require('assert/strict');const tasks=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));const pack=u.promisify(z.brotliCompress);let i=0;async function worker(){while(i<tasks.length){const [src,dst]=tasks[i++],raw=fs.readFileSync(src);const br=await pack(raw,{params:{[z.constants.BROTLI_PARAM_QUALITY]:9}});assert.deepEqual(z.brotliDecompressSync(br),raw);fs.writeFileSync(dst,br);console.log(src.split(/[\\/]/).slice(-2).join('/')+' '+br.length);}}Promise.all([worker(),worker()]).catch(e=>{console.error(e);process.exitCode=1});"""
    subprocess.run([NODE,'-e',compressor,str(taskpath)],check=True)
    release=stage/'public'/m['payload_path'].lstrip('/');release.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(pending/'payload.json',release)
    shutil.copy2(ROOT/'public/capacity-correction-waits.csv',stage/'public/capacity-correction-waits.csv')
    count=preserve(BASE_DATA,stage);size=sum(p.stat().st_size for p in (stage/'public').rglob('*') if p.is_file());assert size<100_000_000,size
    receipt={'directory':str(stage.relative_to(ROOT)),'public_bytes':size,'routing_model_id':m['model_id'],'retained_immutable_files':count,'new_json_files':len(tasks),'data_only':True}
    save(WORK/'data-stage.json',receipt);print(json.dumps(receipt),flush=True)

def ui_stage():
    m,pending=manifest();stage=ROOT/'deployment'/f"supply_ui_{m['model_id']}_{datetime.now():%H%M%S}"
    clone(BASE_UI,stage);public=stage/'public'
    for name in ('index.html','viewer-v5.js','graphs-v5.js','mobile-lab.js','mobile-lab.css',
                 'capacity-correction.html','capacity-correction.md','capacity-correction-review.js'):
        if name.startswith('mobile-lab.') and not (ROOT/'public'/name).exists():continue
        shutil.copy2(ROOT/'public'/name,public/name)
    shutil.copy2(pending/'latest.json',public/'routing-model/latest.json')
    config=read(stage/'vercel.json')
    paths=['/data/capacity_v11/:file.json','/data/half_hour_v1/capacity_v11.json','/data/capacity_review_v1/:file.json',
           '/capacity-correction-waits.csv',m['payload_path']]
    config['rewrites']=[{'source':p,'destination':REMOTE+p} for p in paths]+config['rewrites'];save(stage/'vercel.json',config)
    count=preserve(BASE_UI,stage);size=sum(p.stat().st_size for p in public.rglob('*') if p.is_file());assert size<99_980_000,size
    receipt={'directory':str(stage.relative_to(ROOT)),'public_bytes':size,'routing_model_id':m['model_id'],'retained_immutable_files':count,
             'external_data_host':REMOTE,'existing_archive_unchanged':True,'prototype_algorithm_included':False}
    save(WORK/'ui-stage.json',receipt);print(json.dumps(receipt),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('kind',choices=['data','ui']);a=parser.parse_args()
    if a.kind=='data':data_stage()
    else:ui_stage()
