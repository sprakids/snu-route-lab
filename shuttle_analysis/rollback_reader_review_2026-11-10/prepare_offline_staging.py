"""Copy the preserved v7 static snapshot and overlay ONLY two rollback files."""
import hashlib
import json
import shutil
from pathlib import Path
from datetime import datetime,timezone,timedelta

WORK=Path(__file__).resolve().parent
SIM=WORK.parent/'simulation_viewer_2026-11-07'
DEPLOY=SIM/'deployment'
SOURCE=DEPLOY/'realtime_autoplay_261109175408'
TARGET=DEPLOY/'rollback_v7_261110005327_staging'
DRAFT=WORK/'drafts/261110005327'
EXPECTED_SOURCE='e9dde3d712ff208f9bfe8a41c79de04da7e1cfc430ca549845182ee97f254865'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def inventory(root):
    return {p.relative_to(root).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size}
        for p in sorted(root.rglob('*')) if p.is_file()}

def main():
    assert TARGET.resolve().parent==DEPLOY.resolve()
    assert SOURCE.resolve().parent==DEPLOY.resolve() and TARGET.resolve()!=SOURCE.resolve()
    assert SOURCE.is_dir() and not TARGET.exists(),'preserve an existing stage; never overwrite it'
    old=inventory(SOURCE)
    assert not any(Path(n).name.startswith('.env') or n.endswith('.dpapi') for n in old)
    manifest=json.loads((DRAFT/'routing-model/latest.json').read_bytes())
    assert manifest['model_id']=='261110005327' and manifest['source_simulation']=='capacity_v7'
    assert manifest['content_sha256']=='57cc1bc6822b804598155fe91b78f59cd591cb6e0c0e2341366c3255409a4d06'
    assert sha(SOURCE/'public/routing-model/releases/261109173153.json')==EXPECTED_SOURCE
    # These are the mutable public source/publisher files. Only read their hashes.
    protected={str(p):sha(p) for p in (SIM/'public/routing-model/latest.json',DEPLOY/'queue_source.json')}
    app=WORK.parent/'app'
    app_baseline=json.loads((WORK.parent/'weekday_operations_app_2026-11-10/deployment/source-files-priority.json').read_bytes())
    assert all(sha(app/name)==digest for name,digest in app_baseline.items())
    shutil.copytree(SOURCE,TARGET)
    changed='public/routing-model/latest.json'
    added='public'+manifest['payload_path']
    assert added not in old
    for relative,source in ((changed,DRAFT/'routing-model/latest.json'),(added,DRAFT/manifest['payload_path'].lstrip('/'))):
        destination=TARGET/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
    new=inventory(TARGET)
    modified=[name for name in old if new.get(name)!=old[name]]
    additions=sorted(set(new)-set(old));removed=sorted(set(old)-set(new))
    assert modified==[changed] and additions==[added] and not removed
    assert inventory(SOURCE)==old,'original snapshot changed'
    assert all(sha(Path(path))==digest for path,digest in protected.items())
    assert all(sha(app/name)==digest for name,digest in app_baseline.items())
    config=json.loads((TARGET/'vercel.json').read_bytes())
    assert config['outputDirectory']=='public' and config['buildCommand']==''
    assert config['installCommand']==''
    link=json.loads((TARGET/'.vercel/project.json').read_bytes())
    assert link=={'projectId':'prj_EZEIl5YWei929wYAdurHkdWOwndM','orgId':'team_BKZDs09pK9fVgNkBOC2oU7RL','projectName':'snu-shuttle-simulation'}
    script=(TARGET/'public/viewer-v5.js').read_text(encoding='utf-8')
    assert "||'capacity_v7'" in script and 'capacity_v8' not in script
    assert not (TARGET/'public/data/capacity_v8').exists()
    actual=(TARGET/'public'/manifest['payload_path'].lstrip('/')).read_bytes()
    assert hashlib.sha256(actual).hexdigest()==manifest['sha256'] and len(actual)==manifest['bytes']
    for folder in (TARGET/'public/data').iterdir():
        if folder.is_dir():assert (folder/'common.json.br').exists() or folder.name=='half_hour_v1'
    report={'status':'PASS','kind':'offline_staging_only_not_deployed',
        'prepared_at':datetime.now(timezone(timedelta(hours=9))).isoformat(),
        'source':str(SOURCE),'staging':str(TARGET),'source_files':len(old),'staging_files':len(new),
        'source_bytes':sum(x['bytes'] for x in old.values()),'staging_bytes':sum(x['bytes'] for x in new.values()),
        'unchanged_original_files':len(old)-len(modified),'modified':modified,'added':additions,'removed':removed,
        'model_id':manifest['model_id'],'restored_from_model_id':'261109173153','model_sha256':manifest['sha256'],
        'model_content_sha256':manifest['content_sha256'],'default_dataset':'capacity_v7',
        'old_snapshot_preserved':True,'public_source_latest_unchanged':True,'queue_source_unchanged':True,
        'app_source_files_unchanged':len(app_baseline),'new_deployment':False,'alias_modified':False,
        'provider_calls':0,'capacity_pilot_runs':0,'requires_decision_before_deployment':True}
    (WORK/'offline-source-snapshot-files.json').write_text(json.dumps(old,indent=2),encoding='utf-8')
    (WORK/'offline-staging-files.json').write_text(json.dumps(new,indent=2),encoding='utf-8')
    (WORK/'offline-staging-receipt.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
