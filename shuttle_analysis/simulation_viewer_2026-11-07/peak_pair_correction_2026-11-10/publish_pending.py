"""Build a validated private release; never updates operational latest.json."""
from pathlib import Path
import sys,json,shutil,tempfile,copy,argparse
HERE=Path(__file__).resolve().parent;SIM=HERE.parent;APP=SIM.parent/'app'
sys.path.insert(0,str(APP))
from queue_release import compatibility,accepted_compatibilities,validate,stamp_model,content_digest,encode,digest,SCHEMA,release_time

EXPECTED_PAIR='d55ae84edbee58b42c8d2d641fa50075e157a197fa159e93e10caab9aa1d0c2d'

def publish(resume=False):
    verified=json.loads((HERE/'independent_verification.json').read_bytes())
    assert verified['status']=='PASS' and verified['simulation_runs']==10
    assert digest((HERE/'prepared.json.gz').read_bytes())==verified['prepared_sha256']
    before=(SIM/'public/routing-model/latest.json').read_bytes()
    seed=APP/'data/auto_queue_inputs.json';seed_data=json.loads(seed.read_bytes())
    assert EXPECTED_PAIR in accepted_compatibilities(seed_data),'APP has not enabled this explicit supply-contract migration'
    if resume:
        data=json.loads((HERE/'unpublished_failed_input.json').read_bytes())
        assert data['source_sha256']['latest_prepared']==digest((HERE/'prepared.json.gz').read_bytes())
        assert data['source_sha256']['latest_independent_verification']==digest((HERE/'independent_verification.json').read_bytes())
        for day in ('mon','tue','wed','thu','fri'):
            assert data['source_sha256']['latest_regular_'+day]==digest((HERE/f'audit-regular-{day}.json.gz').read_bytes())
    else:
        with tempfile.TemporaryDirectory(prefix='snu-capacity44-export-') as temp:
            target=Path(temp)/'inputs.json';shutil.copy2(seed,target)
            from prepare_latest_queue import build
            data=build(target=target,source=HERE,write_features=False)
    replay=json.loads((HERE/'public_data/common.json').read_bytes())
    cap=replay['capacity_correction'];pair=replay['peak_pair_operation'];behavior=replay['walk_choice_behavior']
    data.update(capacity_correction=cap,peak_pair_operation=pair,walk_choice_behavior=behavior)
    data['latest_simulation'].update(source_simulation='capacity_v11',capacity_correction=cap,peak_pair_operation=pair,
        walk_choice_behavior=behavior,population_note='원래 가중 집단·행동계수 유지; 설입주간44명/차 및 가정한15~19시2대묶음 공급')
    data['provenance']='가중 수요·행동·속도·명목시각을 유지하고 행정관설입 주간44명/차·가정한피크2대묶음을 적용한 regular/FIFO 입력. 정확한피크경계·묶음주기·실차시간·여석은 미측정.'
    data['limitations']+=['44명은 해당노선에 대한 사용자 최종 정정·등록정원 독립확인 아님',
        '피크묶음은 반복경험·전달된공통증언 근거;15~19시는 기존모형창 가정·4분은 regular 명목시계',
        '21시이후 도서관야간60명은 보존한 미확인 참고가정·다른노선정원 일괄변경 없음',
        '차량도착·탑승·출발 단일사건 근사로189초줄대기/30초탑승후대기를 각각재현하지못함',
        '새67명사례는초미상1건 진단이며 행동계수재적합·배차위상선택·독립예측정확도판정에 쓰지않음']
    assert data['routes']['shuttle-41841']['capacity']==44
    assert data['routes']['shuttle-41841']['capacity_periods']==[{'start_second':75600,'capacity':60}]
    assert data['routes']['shuttle-41841']['dispatch_batches']==[{'start_second':54000,'end_second':68400,'vehicles':2}]
    expected=compatibility(data)
    if expected!=EXPECTED_PAIR:
        projection=lambda r:{k:r.get(k) for k in ('n','loop','offsets','anchor','capacity','capacity_periods','dispatch_batches','profile_route_id','profile_index_map','stops')}
        canonical=copy.deepcopy(seed_data);canonical['routes']['shuttle-41841'].update(capacity=44,capacity_periods=[{'start_second':75600,'capacity':60}],dispatch_batches=[{'start_second':54000,'end_second':68400,'vehicles':2}])
        diff={rid:{k:[v,projection(data['routes'][rid]).get(k)] for k,v in projection(route).items() if projection(data['routes'][rid]).get(k)!=v} for rid,route in canonical['routes'].items()}
        (HERE/'pending_contract_diagnostic.json').write_bytes(encode({'got':expected,'expected':EXPECTED_PAIR,'canonical_pair':compatibility(canonical),'primary_supply':data['routes']['shuttle-41841'],
            'route_differences':{k:v for k,v in diff.items() if v}}))
        (HERE/'unpublished_failed_input.json').write_bytes(encode(data))
        raise ValueError('unexpected_supply_contract')
    stamp_model(data);validate(data,expected,check_profiles=True)
    name=data['model']['id'];published=release_time(name).isoformat();content=content_digest(data)
    data['release']={'model_id':name,'published_at':published,'algorithm_id':data['model']['algorithm_id'],
       'compatibility_sha256':expected,'content_sha256':content,'source_simulation':'capacity_v11'}
    raw=encode(data);manifest={'schema':SCHEMA,**data['release'],'sha256':digest(raw),'bytes':len(raw),
       'payload_path':'/routing-model/releases/'+name+'.json'}
    target=HERE/'pending_releases'/name;target.mkdir(parents=True,exist_ok=False)
    (target/'payload.json').write_bytes(raw);(target/'latest.json').write_bytes(encode(manifest))
    evidence={'status':'VALIDATED_PRIVATE_NOT_PUBLISHED','manifest':manifest,'source_engine_sha256':verified['model_sha256'],
       'source_prepared_sha256':verified['prepared_sha256'],'generation_inputs':{n:digest((APP/n).read_bytes()) for n in
       ('prepare_latest_queue.py','prepare_shuttle_queue.py','prepare_city_queue.py','queue_readiness.py','shuttle_supply.py','queue_release.py','automatic_queue.py','queue_model_sync.py')},
       'public_latest_unchanged':(SIM/'public/routing-model/latest.json').read_bytes()==before,
       'resumed_after_compatibility_label_correction':resume}
    assert evidence['public_latest_unchanged']
    (target/'verification.json').write_bytes(encode(evidence));(HERE/'pending_release.json').write_bytes(encode({'directory':str(target.relative_to(SIM)),**manifest}))
    print(json.dumps({'status':evidence['status'],'model_id':name,'sha256':manifest['sha256'],'compatibility_sha256':expected,'bytes':len(raw)}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--resume-validated-input',action='store_true');a=p.parse_args();publish(a.resume_validated_input)
