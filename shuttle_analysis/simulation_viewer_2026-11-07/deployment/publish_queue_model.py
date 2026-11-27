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
    if selection['simulation_version']=='capacity_v11':
        # Reuse the reviewed supply-aware release. The legacy scalar-capacity
        # publisher below must not rebuild it against the old seed contract.
        pointer=json.loads((source/'pending_release.json').read_bytes())
        verification=json.loads((source/'independent_verification.json').read_bytes())
        if verification['status']!='PASS' or verification['simulation_runs']!=10:raise ValueError('supply_review_required')
        if digest((source/'prepared.json.gz').read_bytes())!=verification['prepared_sha256']:raise ValueError('supply_source_changed')
        if digest((source/'engine.py').read_bytes())!=verification['model_sha256']:raise ValueError('supply_engine_changed')
        latest=json.loads((ROOT/'public/routing-model/latest.json').read_bytes())
        raw=(ROOT/'public'/latest['payload_path'].lstrip('/')).read_bytes()
        if latest['model_id']!=pointer['model_id'] or digest(raw)!=pointer['sha256']:raise ValueError('validated_supply_release_required')
        validate(json.loads(raw),pointer['compatibility_sha256'],check_profiles=True)
        return latest
    public=ROOT/'public';export=public/'routing-model';export.mkdir(exist_ok=True)
    latest=export/'latest.json'
    seed=APP/'data/auto_queue_inputs.json'
    expected=compatibility(json.loads(seed.read_bytes()))
    inputs=[source/'prepared.json.gz',source/'independent_verification.json']
    inputs += [source/f'audit-regular-{day}.json.gz' for day in ('mon','tue','wed','thu','fri')]
    inputs += [APP/name for name in ('prepare_latest_queue.py','prepare_shuttle_queue.py','prepare_city_queue.py','queue_readiness.py','queue_release.py',
        'data/shuttle_model_extension.json','data/simulation_time_inputs.json')]
    inputs += [ROOT/'deployment/queue_source.json',Path(__file__),public/'data'/selection['simulation_version']/'common.json']
    if (source/'city_operations.json').exists():
        inputs += [source/'city_operations.json',APP/'city_operations.py']
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
    if replay.get('city_operations'):
        operations=replay['city_operations']
        if data.get('city_operations')!=operations:raise ValueError('published_operations_differ_from_replay')
        data['latest_simulation']['source_simulation']=selection['simulation_version']
        data['latest_simulation']['weekday_operations']={k:operations[k] for k in ('revision','source_dates','weekdays','transfer_estimate')}
        data['provenance']='보존한 가중 수요·정문 접근 규칙에 월요일 관측 기반 시내 배차·시간대별 구간시간을 월~금 전이한 모형의 FIFO. 실측 줄·고유 학생 수 아님.'
        data['limitations']+=['시내 운행 보정은 월요일 한 날의 평일 전이 추정·요일별 실제 예측 정확도 검증 전',
                              '피크15~19시 배차분포 보정·그 밖 배차는 대표계획 유지·셔틀 직접 이력 없음',
                              '구간 총시간에는 정차가 포함됨·추가 정차 재가산 없음·등급→인원 환산 없음']
    if replay.get('walk_choice_behavior'):
        chosen=json.loads((ROOT/'crowding_walk_choices_2026-11-10/selected_candidate.json').read_bytes())
        verified=json.loads((source/'independent_verification.json').read_bytes())
        if chosen['status']!='VERIFIED' or (ROOT/chosen['directory']).resolve()!=source:raise ValueError('unselected_walk_choice_candidate')
        if digest((source/'prepared.json.gz').read_bytes())!=chosen['prepared_sha256']:raise ValueError('walk_choice_source_changed')
        if verified.get('status')!='PASS' or verified.get('simulation_runs')!=10 or not verified.get('all_stop_quality',{}).get('all_cases_pass'):raise ValueError('walk_choice_all_stop_review_required')
        behavior={**replay['walk_choice_behavior'],'internal_verification':'PASS',
                  'independent_empirical_validation':False,'source_simulation':selection['simulation_version']}
        data['walk_choice_behavior']=behavior
        data['latest_simulation']['source_simulation']=selection['simulation_version']
        data['latest_simulation']['walk_choice_behavior']=behavior
        data['latest_simulation']['population_note']='v9 기준집단 보행 분포 유지 · 개인4.8km/h 도착시각에서 줄을 조회'
        data['provenance']='동일한 수강 기반 가중 이동의 혼잡·본인 만차·대기시간·보행거리 기반 확률적 경로 변경 시나리오. 변경 횟수 상한 없음. 모든 평일/배차의 내부 정원·FIFO·연속대기 검산 완료. 실측 인원·독립 예측 정확도 검증 아님.'
        data['limitations']+=['행동 확률은 사용자 가설을 반영한 잠정 시나리오·실측 보행/경로변경 비율 아님',
                              '20분은 이상 사례 검토 기준·개인별 탑승 보장 또는 대기시간 보장이 아님',
                              '약40명은 서울대정문·법대사회대입구에 대한 사용자 기억 참고값·실측 상한 아님',
                              '같은3건의 분내 시각 미상 관측으로 후보를 선택·보정했으므로 독립 검증 아님']
    stamp_model(data,at)
    # The city extension has its own data-only contract. Preserve shuttle
    # topology while deliberately publishing the expanded compatibility hash.
    seed_data=json.loads(seed.read_bytes())
    if compatibility({k:v for k,v in data.items() if k!='city_wait'})!=compatibility({k:v for k,v in seed_data.items() if k!='city_wait'}):raise ValueError('shuttle_contract_changed')
    expected=compatibility(data)
    try:
        validate(data,expected,check_profiles=True)
    except Exception as exc:
        # Preserve concrete failure evidence without publishing a bad pointer.
        evidence=source/'routing_export_failures';evidence.mkdir(exist_ok=True)
        snapshot=evidence/(data['model']['id']+'-unpublished.json')
        snapshot.write_bytes(encode(data))
        (evidence/(data['model']['id']+'-failure.json')).write_bytes(encode({'error':type(exc).__name__,'message':str(exc),'latest_pointer_updated':False}))
        raise
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
    data['release']={'model_id':name,'published_at':published,'algorithm_id':data['model']['algorithm_id'],
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
