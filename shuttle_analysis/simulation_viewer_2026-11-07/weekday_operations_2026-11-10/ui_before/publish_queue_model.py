"""Export verified aggregate queue inputs before static staging. No raw audits."""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT.parent/'app'
sys.path.insert(0,str(APP))
from queue_release import SCHEMA,ALGORITHM,compatibility,content_digest,digest,encode,release_time,stamp_model,validate

def publish(*,at=None):
    selection=json.loads((ROOT/'deployment/queue_source.json').read_text(encoding='utf-8'))
    source=(ROOT/selection['model_directory']).resolve()
    if not source.is_relative_to(ROOT) or selection['adapter']!='audited_v5_fifo':raise ValueError('unsupported_source')
    public=ROOT/'public';export=public/'routing-model';export.mkdir(exist_ok=True)
    latest=export/'latest.json'
    seed=APP/'data/auto_queue_inputs.json'
    expected=compatibility(json.loads(seed.read_bytes()))
    inputs=[source/'prepared.json.gz',source/'independent_verification.json']
    inputs += [source/f'audit-regular-{day}.json.gz' for day in ('mon','tue','wed','thu','fri')]
    inputs += [APP/name for name in ('prepare_latest_queue.py','prepare_shuttle_queue.py','prepare_city_queue.py','queue_release.py',
        'data/shuttle_model_extension.json','data/simulation_time_inputs.json')]
    inputs += [ROOT/'deployment/queue_source.json',Path(__file__),public/'data'/selection['simulation_version']/'common.json']
    generation=digest(encode({'compatibility':expected,'inputs':[digest(p.read_bytes()) for p in inputs]}))
    if latest.exists():
        old=json.loads(latest.read_bytes())
        if old.get('generation_sha256')==generation:
            raw=(public/old['payload_path'].lstrip('/')).read_bytes()
            if digest(raw)!=old['sha256']:raise ValueError('existing_release_modified')
            return old
    with tempfile.TemporaryDirectory(prefix='snu-queue-export-') as temp:
        target=Path(temp)/'inputs.json';shutil.copy2(seed,target)
        from prepare_latest_queue import build
        data=build(target=target,source=source,write_features=False)
    replay=json.loads((public/'data'/selection['simulation_version']/'common.json').read_bytes())
    if replay.get('gate_access_calibration'):
        calibration={**replay['gate_access_calibration'],'status':'active_default_user_authorized',
                     'independent_empirical_validation':False,'observations_used_for_selection':3}
        data['calibration_provenance']=calibration
        data['latest_simulation']['source_simulation']=selection['simulation_version']
        data['latest_simulation']['gate_access_calibration']=calibration
        data['provenance']='정문 초기 도보 접근을 보정한 전체 가중 흐름의 승차준비 유입·모형 승하차OD·FIFO. 실측 줄·고유 학생 수 아님.'
        data['limitations']+=['정문 도보 접근은 사용자 보고3건을 참고한 보정이며 같은3건으로 독립 검증하지 않음',
                              '관측시각은 분내 균등 가정·정문33~39명 구간 유지·다른 날짜/요일 일반화 미검증']
    stamp_model(data,at)
    # The city extension has its own data-only contract. Preserve shuttle
    # topology while deliberately publishing the expanded compatibility hash.
    seed_data=json.loads(seed.read_bytes())
    if compatibility({k:v for k,v in data.items() if k!='city_wait'})!=compatibility({k:v for k,v in seed_data.items() if k!='city_wait'}):raise ValueError('shuttle_contract_changed')
    expected=compatibility(data)
    validate(data,expected,check_profiles=True)
    replay=json.loads((public/'data'/selection['simulation_version']/'common.json').read_bytes())
    if replay.get('city_speed_revision')!=data['latest_simulation']['revision']:raise ValueError('replay_source_mismatch')
    content=content_digest(data)
    if latest.exists():
        old=json.loads(latest.read_bytes())
        if old['content_sha256']==content and old['compatibility_sha256']==expected:
            path=public/old['payload_path'].lstrip('/')
            raw=path.read_bytes()
            if digest(raw)!=old['sha256']:raise ValueError('existing_release_modified')
            old['generation_sha256']=generation
            temporary=export/'latest.pending';temporary.write_bytes(encode(old));temporary.replace(latest)
            return old
        if data['model']['id']<=old['model_id']:raise ValueError('release_clock_collision')
    name=data['model']['id'];published=release_time(name).isoformat()
    data['release']={'model_id':name,'published_at':published,'algorithm_id':ALGORITHM,
        'compatibility_sha256':expected,'content_sha256':content,'source_simulation':selection['simulation_version']}
    raw=encode(data)
    manifest={'schema':SCHEMA,**data['release'],'sha256':digest(raw),'bytes':len(raw),
        'generation_sha256':generation,
        'payload_path':'/routing-model/releases/'+name+'.json'}
    target=public/manifest['payload_path'].lstrip('/');target.parent.mkdir(exist_ok=True)
    if target.exists():raise ValueError('immutable_release_exists')
    target.write_bytes(raw)
    temporary=export/'latest.pending';temporary.write_bytes(encode(manifest));temporary.replace(latest)
    return manifest

if __name__=='__main__':print(json.dumps(publish(),ensure_ascii=False))
