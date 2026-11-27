"""Record the user's promotion and keep original calibration evidence intact."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,re
import gate_access_calibration as trial


def main():
    public=trial.ROOT/'public';before=trial.WORK/'ui_before/public'
    manifest=trial.read(public/'routing-model/latest.json')
    assert manifest['source_simulation']=='capacity_v7'
    summary=trial.read(before/'gate-access-summary.json')
    summary.update(default_dataset='capacity_v7',default_routing_release=manifest['model_id'],
                   promotion_status='active_default_user_authorized',
                   prior_default_dataset='capacity_v5',prior_default_routing_release='261109152540')
    trial.save(public/'gate-access-summary.json',summary)
    banner=f"사용자 요청에 따라 기본 지도와 경로 추천의 대기모델에 적용했습니다. 지도 입력 모형은 {summary['model_id']}, 경로 대기 릴리스는 {manifest['model_id']}입니다. 실측 3건을 참고한 보정이며 다른 날짜의 독립 검증은 아직 전입니다."
    old='기존 v5·v6 자료와 운영 경로 추천의 기본 대기모델은 보존했습니다.'
    new='기존 v5·v6 자료를 보존하고 기본 지도와 경로 추천을 정문 도보 접근 보정 모형으로 전환했습니다.'
    md=(before/'gate-access-methodology.md').read_text(encoding='utf-8')
    md=md.replace('# 정문 도보 접근 보정 후보','# 정문 도보 접근 보정 모형',1)
    first,rest=md.split('\n',1);md=first+'\n\n'+banner+'\n'+rest
    md=md.replace(old,new).replace('[보정 후보 지도]','[현재 기본 지도]').replace('[기존 v5 지도](./)','[기존 v5 지도](./?dataset=baseline_v5)')
    md=md.replace('[보정 후보 지도](?dataset=gate_access_v1)','[현재 기본 지도](./)').replace('[현재 기본 지도](?dataset=gate_access_v1)','[현재 기본 지도](./)')
    (public/'gate-access-methodology.md').write_text(md,encoding='utf-8')
    page=(before/'gate-access-methodology.html').read_text(encoding='utf-8')
    page=page.replace('정문 도보 접근 보정 후보','정문 도보 접근 보정 모형').replace('정문 도보 보정 후보 ·','정문 도보 보정 모형 ·')
    page=re.sub(r'(</h1>)',lambda m:m.group(1)+'<p><strong>'+banner+'</strong></p>',page,count=1)
    page=page.replace(old,new).replace('>보정 후보 지도<','>현재 기본 지도<').replace('href="./"','href="./?dataset=baseline_v5"')
    (public/'gate-access-methodology.html').write_text(page,encoding='utf-8')
    prior=trial.read(trial.WORK/'protected_source_hashes.json');original_count=0
    for relative,digest in prior.items():
        if relative=='public/routing-model/latest.json':continue
        assert trial.base.sha(trial.ROOT/relative)==digest,relative;original_count+=1
    receipt={'status':'prepared_for_deployment','source_model_id':summary['model_id'],
             'routing_model_id':manifest['model_id'],'routing_sha256':manifest['sha256'],
             'compatibility_sha256':manifest['compatibility_sha256'],
             'user_authorized_default_promotion':True,'default_dataset':'capacity_v7',
             'previous_default_dataset':'capacity_v5','previous_routing_model_id':'261109152540',
             'original_immutable_artifacts_unchanged':original_count,
             'intentional_mutable_pointer_change':'public/routing-model/latest.json',
             'independent_empirical_validation':False,
             'created_at_kst':datetime.now(timezone(timedelta(hours=9))).isoformat()}
    trial.save(trial.WORK/'promotion_preparation.json',receipt)
    (trial.WORK/'README.md').write_text(md,encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':main()
