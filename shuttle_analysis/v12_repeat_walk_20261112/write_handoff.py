"""Publish local review artifacts to the existing implementation peer, never production."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):assert not p.exists(),p;p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve()
    check=read(w/'artifact_verification_final.json');assert check['status']=='PASS_RECONCILED_PRIVATE_CANDIDATE'
    r=read(w/'release_recommendation_final.json');live=read(w/'final_verification.json');assert live['status']=='PASS'
    files=['RESULTS_FINAL.md','release_recommendation_final.json','artifact_verification_final.json','final_verification.json',
      'grid-validation.json','grid-diagnostics.json','grid-probability-validation.json','probability-law.csv','grid-walking-by-change-count.csv',
      'grid-field-comparison.csv','grid-all-stops.csv','grid-half-hour-waits.csv','grid-journey-comparison.csv','class-end-journey-comparison.csv',
      'mean-physical-components.csv','grid-trace-and-costs.json','OBSERVATION_USAGE.md','observation_usage_ledger.json','pilot-assessment.json',
      'future_evaluation_plan.json','boundary-tests.log','config.json','USER_DIRECTIVE.md']
    assert sha(w/'RESULTS_FINAL.md')==r['report_sha256']
    folder=ROOT.parent/'collaboration'/f'v12_repeat_walk_{w.name}';folder.mkdir(exist_ok=False)
    peer=ROOT.parent/'collaboration'/f'v12_repeat_walk_review_{w.name}'
    save(folder/'handoff.json',{'status':'PRIVATE_USER_REQUESTED_SCENARIO_COMPLETE','release_id':w.name,'parent':r['parent'],
      'created_at':datetime.now(timezone.utc).isoformat(),'candidate':str(w),'result':r,'artifact_checks':check,
      'files':{str(w/name):sha(w/name) for name in files},'peer_static_review':{str(peer/name):sha(peer/name) for name in ('READ_ONLY_REVIEW.md','evidence.json')},'production_model_preserved':live['production_model_id'],
      'authorized_receiver_thread':'01a1a1e8-54cf-7243-9ad9-0a31e6f31a06','production_writes':False})
    lines=[f'# 목적지 도보확률 증가 후보 {w.name}','',
      f"직전{r['parent']}에 사용자가 요청한 완료 경로 변경 횟수 효과를 추가했습니다. `p(n)=1-(1-p_ref)^(2^n)`이며, 같은 맥락의 기준10%라면0..4회에서10%,19%,34.39%,56.95%,81.47%입니다. 증가율2는 실측 추정값이 아닌 시나리오입니다.",'',
      '목적지까지 걷는 대안에만 적용하며 다른 정류장으로 가서 버스를 타는 대안은 직접 증폭하지 않습니다. n=0 선택·기본 비용·거리 선호·재검토 시계0.3^n·무제한 변경·수요·공급·정원·수업 후 출발 배율1.125·접근 수요 예측은 계승했습니다.1회 이상 목적지 도보의 사전 비용 가지치기 생략과 참조 비용의 횟수 증가분 중립화는 명세에 공개했습니다.','',
      f"89개 시험,10조건 원장 감사,확률 로그{r['recorded_probability_checks']}건 검산을 완료했습니다. 전체 기록 최대 연속대기{r['maximum_all_recorded_continuous_wait_min']:.6f}분,20분 초과 가중치{r['over20_episode_weight']},미완료{r['unserved_trip_weight']}입니다.",'',
      f"평균 총시간 감소{r['mean_total_improved']}/10,p99 감소{r['p99_total_improved']}/10,최장 감소{r['max_total_improved']}/10입니다. p99 변화{r['p99_delta_range'][0]:+.3f}~{r['p99_delta_range'][1]:+.3f}분,전체 최장 총시간{r['parent_maximum_total_journey_min']:.3f}→{r['maximum_total_journey_min']:.3f}분입니다. 악화 조건도 원표에 포함했고 전반 개선이나 실제 정확도로 확대하지 않습니다.",'',
      f"기존 방향확인3점 손실{r['primary_loss_before']:.6f}→{r['primary_loss_after']:.6f},네 보고의 오차 감소{r['old_field_errors_improved']}건/증가{r['old_field_errors_worse']}건입니다. 반복 사용한 비교값이며 새 날짜 검증이 아닙니다.",'',
      '실측 반영 장부에53항목·39스냅샷·7동결 입력·14사용 역할을 추적했습니다.11/10 시내버스 통과간격·구간시간·순서형 혼잡을 계승했고11/11은 이미 탐색한 진단입니다. 화요일 최종67명/44명/두 대 중 두 번째/줄189초+탑승 후30초를 보존했습니다. 전역 개인 대기 오차·정확한 도착시각·셔틀 GPS/실배차분포·교외 숫자 재차인원·관악02 혼잡등급은 식별 불가를 유지했습니다. 새 날짜 정답은 열지 않았습니다.','',
      '**V11·운영 경로계산·실험실 기본값·공개 latest는 그대로 유지합니다. 사용자 명시 승인 전에 교체하거나 배포하지 마세요.** 이번 결과는 비운영 시나리오이며 실제 학생 개개인의 경로/도보확률을 추정한 자료가 아닙니다.','',
      f'[최종 보고서](../../{w.name}/RESULTS_FINAL.md), [실측 사용 장부](../../{w.name}/OBSERVATION_USAGE.md), [전체 파일 해시](handoff.json).','']
    (folder/'README.md').write_text('\n'.join(lines),encoding='utf8')
    provenance={'release_id':w.name,'analysis_scripts':{str(f):sha(f) for f in ROOT.glob('*.py')},
      'handoff':{str(f):sha(f) for f in folder.glob('*') if f.is_file()},'final_documents':{str(w/name):sha(w/name) for name in files},
      'runtime_integrity':live['status'],'production_writes':False,'new_outcomes_opened':False}
    save(w/'analysis_provenance_final.json',provenance);print('HANDOFF_WRITTEN',folder,flush=True)
if __name__=='__main__':main()
