"""Exercise the actual reader offline; no capacity scenario or provider calls."""
import json
import sys
from pathlib import Path
from datetime import datetime

WORK=Path(__file__).resolve().parent;APP=WORK.parent/'app'
BASE=WORK.parent/'weekday_operations_app_2026-11-10/integration_qa'
sys.path.insert(0,str(APP))
from calculation_context import calculation_context
from queue_model_sync import LatestQueueModel,FEED
from queue_release import encode,digest,release_time
from prepare_v7_overlay import build

def main():
    v8=BASE/'candidate-payload.json';v7=BASE/'baseline-payload.json'
    assert digest(v8.read_bytes())=='6bada3eec9fa0c89386e3cbac2e3e7e90adfa2ce10f0c969c54cafd43c53fe8d'
    old_manifest=json.loads((BASE/'baseline-manifest.json').read_bytes());old_raw=v7.read_bytes()
    now=datetime.now(release_time('261110002926').tzinfo)
    clock=[now.timestamp()];state=[old_manifest,old_raw];calls=[]
    def fetch(url,*args):
        calls.append(url)
        return encode(state[0]) if url==FEED else state[1]
    warm=LatestQueueModel(None,v8,remote=True,clock=lambda:clock[0],fetch=fetch)
    rejected=warm.info()
    assert rejected['model_id']=='261110002926' and rejected['sync']['last_error']=='older_release'
    assert len(calls)==1,'the older payload is rejected before download'
    cold=LatestQueueModel(None,APP/'data/auto_queue_inputs.json',remote=True,clock=lambda:clock[0],fetch=fetch)
    accepted=cold.info()
    assert accepted['model_id']=='261109173153' and accepted['sync']['last_error'] is None
    manifest,raw=build('261110002926',now);state[:]=[manifest,raw];clock[0]+=61
    restored=warm.info()
    assert restored['model_id']==manifest['model_id'] and restored['sync']['last_error'] is None
    assert restored['sync']['payload_sha256']==manifest['sha256'] and not restored['city_operations']['available']
    # A response already computing with v8 stays pinned; the next response uses
    # the restored model, so one route comparison never mixes releases.
    pinned=LatestQueueModel(None,v8,remote=True,clock=lambda:clock[0],fetch=fetch)
    pinned._next_check=clock[0]+60
    with calculation_context():
        assert pinned.config['id']=='261110002926'
        clock[0]+=61
        assert pinned.config['id']=='261110002926'
    assert pinned.config['id']==manifest['model_id'] and not pinned.operations.info()['available']
    report={'status':'PASS','kind':'offline_reader_review_not_operational_rollback',
        'warm_old_pointer':{'active_model':rejected['model_id'],'error':rejected['sync']['last_error']},
        'cold_old_pointer':{'active_model':accepted['model_id'],'error':accepted['sync']['last_error']},
        'metadata_only_v7_reissue':{'test_model_id':manifest['model_id'],'sha256':manifest['sha256'],
            'content_sha256':manifest['content_sha256'],'algorithm':restored['algorithm_id'],
            'reader_accepts':True,'v8_operations_disabled':True,'new_requests_use_restored_model':True},
        'request_local_pinning_preserved':True,'source_payload_sha256':digest(old_raw),
        'app_modified':False,'public_latest_modified':False,'deployments_modified':False,
        'provider_calls':0,'full_capacity_simulations_run':0}
    (WORK/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
