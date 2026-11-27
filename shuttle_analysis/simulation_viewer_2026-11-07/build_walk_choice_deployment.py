"""Preserve the existing 99MB archive while serving new immutable model data separately."""
from pathlib import Path
from datetime import datetime
import argparse,json,shutil,subprocess,hashlib,re
from prepare_walk_choices import ROOT,read
from selected_walk_choice import selected_work

NODE='C:/Program Files/nodejs/node.exe'
BASELINE=ROOT/'deployment/loading_perf_v7_261110'
UI_ASSETS=['viewer-v5.js','graphs-v5.js','json-loader.js','index.html','city.html','viewer-v5.css',
           'walk-choice-methodology.html','walk-choice-methodology.md','walk-choice-review.js',
           'rollback-report.html','rollback-report.md','rollback-status.json']

def cached_data():
    work=selected_work();cache=work/'brotli-cache'
    tasks=[]
    for dataset,names in [('capacity_v9',['common','charts',*[f'{s}-{d}' for s in ('peak','regular') for d in ('mon','tue','wed','thu','fri')]]),
                          ('half_hour_v1',['capacity_v9']),('walk_review_v1',['report'])]:
        for name in names:
            source=ROOT/'public/data'/dataset/f'{name}.json';target=cache/'data'/dataset/f'{name}.json.br';target.parent.mkdir(parents=True,exist_ok=True)
            raw=source.read_bytes();json.loads(raw)
            assert not re.search(rb'C:[\\/]|(?:api|service)[_-]?key=|BEGIN [A-Z ]*PRIVATE KEY',raw,re.I),str(source)
            tasks.append([str(source),str(target)])
    taskfile=work/'brotli-data-tasks.json';taskfile.write_text(json.dumps(tasks),encoding='utf8')
    compressor="""const fs=require('fs'),z=require('zlib'),u=require('util'),a=require('assert/strict');const tasks=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));const pack=u.promisify(z.brotliCompress);let i=0;async function worker(){while(i<tasks.length){const [src,dst]=tasks[i++],raw=fs.readFileSync(src);if(fs.existsSync(dst)){a.deepEqual(z.brotliDecompressSync(fs.readFileSync(dst)),raw);continue;}const br=await pack(raw,{params:{[z.constants.BROTLI_PARAM_QUALITY]:11}});a.deepEqual(z.brotliDecompressSync(br),raw);fs.writeFileSync(dst,br);console.log(src.split(/[\\/]/).slice(-2).join('/')+' '+raw.length+' -> '+br.length);}}Promise.all([worker(),worker()]).catch(e=>{console.error(e);process.exitCode=1});"""
    subprocess.run([NODE,'-e',compressor,str(taskfile)],check=True)
    return cache

def data_stage():
    work=selected_work();manifest=read(ROOT/'public/routing-model/latest.json');assert manifest['source_simulation']=='capacity_v9'
    cache=cached_data()
    stage=ROOT/'deployment'/f"walk_choices_data_{manifest['model_id']}";assert not stage.exists()
    public=stage/'public';shutil.copytree(cache,public)
    release=public/manifest['payload_path'].lstrip('/');release.parent.mkdir(parents=True);shutil.copy2(ROOT/'public'/manifest['payload_path'].lstrip('/'),release)
    shutil.copy2(ROOT/'public/walk-choice-waits.csv',public/'walk-choice-waits.csv')
    (public/'index.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><title>하교길 실험실 공개 모형자료</title><p>검증된 시뮬레이션의 공개 집계·표시 자료입니다. 실제 개인의 이동 기록이 아닙니다.</p><a href="https://snu-shuttle-simulation.vercel.app/">하교길 실험실</a></html>',encoding='utf8')
    config={'$schema':'https://openapi.vercel.sh/vercel.json','framework':None,'installCommand':'','buildCommand':'','outputDirectory':'public',
            'headers':[{'source':'/(.*)','headers':[{'key':'X-Content-Type-Options','value':'nosniff'},{'key':'Cache-Control','value':'public, max-age=31536000, immutable'}]},
                       {'source':'/data/:dataset/:file.json','headers':[{'key':'Content-Type','value':'application/json; charset=utf-8'},{'key':'Content-Encoding','value':'br'}]}],
            'rewrites':[{'source':'/data/:dataset/:file.json','destination':'/data/:dataset/:file.json.br'}]}
    (stage/'vercel.json').write_text(json.dumps(config,indent=2),encoding='utf8');(stage/'.vercelignore').write_text('.vercel\n.env*\n.git\n',encoding='utf8')
    size=sum(p.stat().st_size for p in public.rglob('*') if p.is_file());assert size<100_000_000
    receipt={'directory':str(stage.relative_to(ROOT)),'public_bytes':size,'routing_model_id':manifest['model_id'],'data_only':True}
    (work/'data-stage.json').write_text(json.dumps(receipt,indent=2),encoding='utf8');print(json.dumps(receipt),flush=True)

def ui_stage():
    work=selected_work();manifest=read(ROOT/'public/routing-model/latest.json');remote=read(ROOT/'deployment/walk_choice_data_host.json')['url'].rstrip('/')
    stage=ROOT/'deployment'/f"walk_choices_ui_{manifest['model_id']}_{datetime.now().strftime('%H%M%S')}";assert not stage.exists()
    shutil.copytree(BASELINE,stage);public=stage/'public'
    for name in UI_ASSETS:
        source=ROOT/'public'/name
        if source.exists():shutil.copy2(source,public/name)
    shutil.copy2(ROOT/'public/routing-model/latest.json',public/'routing-model/latest.json')
    config=read(stage/'vercel.json')
    external=[{'source':'/data/capacity_v9/:file.json','destination':remote+'/data/capacity_v9/:file.json'},
              {'source':'/data/half_hour_v1/capacity_v9.json','destination':remote+'/data/half_hour_v1/capacity_v9.json'},
              {'source':'/data/walk_review_v1/:file.json','destination':remote+'/data/walk_review_v1/:file.json'},
              {'source':manifest['payload_path'],'destination':remote+manifest['payload_path']},
              {'source':'/walk-choice-waits.csv','destination':remote+'/walk-choice-waits.csv'}]
    config['rewrites']=external+config['rewrites'];(stage/'vercel.json').write_text(json.dumps(config,indent=2),encoding='utf8')
    # Old datasets/releases stay byte-identical; only the mutable latest pointer changes.
    count=0
    for folder in ('data','routing-model/releases'):
        for source in (BASELINE/'public'/folder).rglob('*'):
            if source.is_file():
                target=public/source.relative_to(BASELINE/'public');assert target.read_bytes()==source.read_bytes();count+=1
    size=sum(p.stat().st_size for p in public.rglob('*') if p.is_file());assert size<99_980_000,size
    receipt={'directory':str(stage.relative_to(ROOT)),'public_bytes':size,'routing_model_id':manifest['model_id'],'retained_immutable_files':count,
             'external_data_host':remote,'existing_archive_unchanged':True}
    (work/'ui-stage.json').write_text(json.dumps(receipt,indent=2),encoding='utf8');print(json.dumps(receipt),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('kind',choices=['cache','data','ui']);args=parser.parse_args()
    if args.kind=='cache':cached_data()
    elif args.kind=='data':data_stage()
    else:ui_stage()
