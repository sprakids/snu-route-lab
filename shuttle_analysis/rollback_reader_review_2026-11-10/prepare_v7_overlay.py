"""Prepare a LOCAL v7 rollback overlay. Never changes app/public/deployments."""
import copy
import json
import sys
from pathlib import Path
from datetime import datetime

WORK=Path(__file__).resolve().parent
APP=WORK.parent/'app'
BASE=WORK.parent/'weekday_operations_app_2026-11-10/integration_qa'
sys.path.insert(0,str(APP))
from queue_release import SCHEMA,encode,digest,compatibility,content_digest,release_name,release_time,stamp_model,validate

V7_SHA='e9dde3d712ff208f9bfe8a41c79de04da7e1cfc430ca549845182ee97f254865'

def build(active_id,at=None):
    release_time(active_id)
    raw=(BASE/'baseline-payload.json').read_bytes()
    assert digest(raw)==V7_SHA
    original=json.loads(raw);old_manifest=json.loads((BASE/'baseline-manifest.json').read_bytes())
    assert original['model']['id']=='261109173153'
    at=at or datetime.now(release_time(active_id).tzinfo)
    name=release_name(at)
    if name<=active_id:raise ValueError('rollback_release_must_be_newer_than_all_active_ids')
    restored=stamp_model(copy.deepcopy(original),at)
    assert content_digest(restored)==content_digest(original)==old_manifest['content_sha256']
    assert compatibility(restored)==compatibility(original)==old_manifest['compatibility_sha256']
    restored['release']={**original['release'],'model_id':name,'published_at':release_time(name).isoformat()}
    validate(restored,compatibility(original))
    encoded=encode(restored)
    manifest={**old_manifest,**restored['release'],'schema':SCHEMA,'bytes':len(encoded),
        'sha256':digest(encoded),'payload_path':'/routing-model/releases/'+name+'.json',
        'generation_sha256':digest(encode({'kind':'v7_rollback_metadata_only','original_payload_sha256':V7_SHA,
            'restores_model_id':original['model']['id'],'replaces_model_id':active_id,'release_id':name}))}
    # These are the only altered values in the model payload.
    normalized=copy.deepcopy(restored);normalized['model']['id']=original['model']['id'];normalized['release']=original['release']
    assert normalized==original
    return manifest,encoded

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--active-id',required=True);a=p.parse_args()
    manifest,raw=build(a.active_id)
    target=WORK/'drafts'/manifest['model_id']
    payload=target/manifest['payload_path'].lstrip('/');payload.parent.mkdir(parents=True,exist_ok=True)
    pointer=target/'routing-model/latest.json'
    for path,value in ((payload,raw),(pointer,encode(manifest))):
        if path.exists():assert path.read_bytes()==value,'immutable draft collision'
        else:path.write_bytes(value)
    print(json.dumps({'draft_only':True,'model_id':manifest['model_id'],'sha256':manifest['sha256'],
        'bytes':manifest['bytes'],'content_sha256':manifest['content_sha256'],
        'restores_model_id':'261109173153','valid_only_while_active_id_is_less_than':manifest['model_id'],
        'path':str(target),'app_modified':False,'public_latest_modified':False,'deployed':False}))

if __name__=='__main__':main()
