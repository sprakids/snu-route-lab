"""Publish local review documents, never publish the model or change V11."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,csv,hashlib,json
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,s):
    assert not p.exists(),p
    p.write_text(s,encoding='utf8')
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve()
    v=read(w/'grid-validation.json');check=read(w/'grid-final-verification.json');r=read(w/'grid-recommendation.json');b=read(w/'grid-behavior-validation.json')
    assert check['status']=='PASS' and b['status']=='PASS_STUDENT_BEHAVIOR_GATES' and len(v['results'])==10
    source='''# 가정·자료·출처 — 학생 하교 행동 수정

이번 변경의 행동 근거는 사용자가 설명한 서울대 학생의 하교 과정입니다. 실제 개인별 이동·선호를 새로 조사한 결과로 해석하지 않습니다.

|항목|사용 자료·이유|확인 범위와 가정|
|---|---|---|
|수업 종료·수강인원·건물|[기존 수업표 추출](frozen/class_endings_source_20261106.json), [가중 수요](frozen/prepared_capacity44_pair.json.gz)|분반/수강인원 기반 모의 수요. 수강인원을 고유 통학생이나 실제 목적지 조사로 바꾸어 해석하지 않음|
|기숙사·설입·낙성대·대학동 및 도서관 경유|계승한 가중 수요의 목적지·출발시각 시나리오|전체56개 동결 입력 불변. 실제 개인별 집 주소나 도서관 퇴실시각을 확보한 것이 아님|
|초기 수단 선호|기존 수요 계획의 첫 서비스|실제 설문 대리값. 먼 설입 직접도보는 시내버스로 전환하는 예외 공개|
|셔틀/시내버스의 기다림 한계|사용자의 약20분 설명|중앙값20분, 로그표준편차0.25. 같은 개인은 이동 후에도 다시 추첨하지 않음. 시내버스에도 같은 중앙값을 둔 미측정 가정|
|만차 두 번 후 재검토|실제로 못 탄 호환 버스와 앞으로 더 보내야 하는 예측|두 대+두 대 기준은 사용자 설명을 수치화한 시나리오. 현재 정보로 예측하며 미래 실현 승객 수를 미리 읽지 않음|
|시내버스 운행/시간/혼잡 맥락|[11월10일 관측 기반 운행 입력](frozen/operations_v12_empirical.json), [실측 대리정보](frozen/empirical_evidence.json)|출입 지점 탐지로 추정한 구간시간·통과 간격. 공식 초단위 배차나 순수 주행속도와 동일하지 않음. 혼잡등급은 사람 수가 아님|
|셔틀 정원·공급|[정원 보정](capacity44_amendment.json), [두 대 편성 시나리오](pair_amendment.json)|계승한 행정관-설입 낮44명/대,15~19시 두 대 편성 가정. 모든 편성이 실제로 그러하다는 관측은 없음. 기존 야간60명 등 미측정 가정 유지|
|도보 중 승차|사용자 설명+기존 지도 경로 접합|기존 prefix/suffix 경로만 사용. 추가80m/횡방향30m/30초 창은 가정. 정류장 도착·준비·정원·FIFO를 거침|
|도보 거리와 반복 변경|기존 거리 선호·기하급수적 목적지 도보 규칙|0~500m 평탄,1km 이후 급감 계승. 변경횟수 상한 없음. 같은 노선의 뒤 정류장 이동 가중치0.08 계승|
|정류장 재방문·정문 최종 대안|사용자 설명|떠난 승차지와 현재 떠날 승차지를 후속 환승에서도 금지. 설입 목적의 정식 정문 밖 대안은5511/5513/5515/5528/6515를 기다림|
|대학동 목적5516 최종승차 방향|동결 공식 노선별 정류장 direction metadata|직접 마지막5516은 대학동고시촌입구 방향만 허용. 노량진 방향으로 먼저 타서 대학동으로 돌아오는82분 차내 사례 교정. 중간환승은 허용|

버스 정원과 사건별 승차/대기/경로 적응을 연결하는 구조에는 [Patzner & Müller-Hannemann,2024, Dynamic Traffic Assignment for Public Transport with Vehicle Capacities](https://drops.dagstuhl.de/storage/01oasics/oasics-vol123-atmos2024/OASIcs.ATMOS.2024.18/OASIcs.ATMOS.2024.18.pdf)의 초록·서론·모델 개요를 참고했습니다. 이 논문은 서울대의20분, 개인차0.25, 두 대,30초 등을 실측한 근거가 아닙니다.

과거 줄 관측은 월요일으로 추정한16:53 행정관53명,16:55 문화관5명(방향 불확실),17:03 정문 밖21128의33~39명, 화요일15:23 행정관 줄 합류67명(본인 포함)입니다. 분 안의 초는 균등 비교하며00초로 고정하지 않았습니다. 화요일은44명/대,동행 두 대 중 두 번째 승차,순수대기189초+승차 후30초라는 수정값을 계승합니다. 두 사진은 한 관측이며 정확한 버스 도착시각은 없습니다. 네 점 모두 이전 보정·후보 비교에서 사용했으므로 독립 검증이 아닙니다.

11월10일 버스 자료는 학습 입력,11월11일은 이미 탐색한 자료입니다. 이번 작업은 새 날짜의 실측 정답을 열지 않았습니다. 교외에서 이미 타고 들어오는 실제 승객 수, 혼잡등급별 사람 수, 학생 개인별 경로 기록은 새로 확보하지 않았습니다. 과거 만차 후 여석 기억도 모형 가정입니다. 자세한 출처별 소비 위치는 [기존 사용 장부](../261112220847/OBSERVATION_USAGE.md), 변경 과정은 [명세](../v12_student_strategy_20261115/SPEC.md), 동결 증거는 [계획](future_evaluation_plan.json)과 [입력 명세](repair_manifest.json)를 참고합니다.

이 후보는 행동 구현·물리 원장 검사까지 검증했습니다. 새 실측에 대한 정확도, 사이트 데이터 연결, 브라우저 성능, 운영 배포 준비를 확인했다는 뜻은 아닙니다. 도보 중 승차도 모든 경로를 지원하거나 항상 도보보다 빠른 총도착을 보장하지는 않습니다.
'''
    put(w/'ASSUMPTIONS_AND_SOURCES.md',source)
    lines=[f'# 학생 하교 행동 반영 후보 {w.name}','',
      f"사용자 지시에 따라 수정하고 평일5일×기본/피크 배차10조건을 검증했습니다. 코드 검사{check['unit_tests']['total']}개(새 행동 활성{check['unit_tests']['enabled_strategy_and_enroute']}개·기존 구성요소{check['unit_tests']['legacy_components_strategy_disabled']}개), 인원·정원·FIFO·시간 및 행동 원장 검사10/10을 통과했습니다. 운영 모델은{check['production_model_id']}로 유지했습니다.",'',
      '## 무엇이 달라졌나요','',
      '1. 셔틀 선호자는 개인별 예상 기다림 한계 전까지 셔틀을 유지합니다. 약20분은 중앙값이며 강제 이탈 시각이 아닙니다.',
      '2. 시내버스 선호자는 걸어가는 시간과 실제 탈 수 있을 때까지의 예측 대기를 합쳐 가장 빨리 승차할 정류장을 고릅니다.',
      '3. 두 대가 만차로 지나가고 추가 대기도 길 것으로 예상되거나 개인 인내를 넘으면 다른 노선·셔틀·가까운 목적지 도보를 재검토합니다.',
      '4. 한 번 떠난 승차 정류장으로 되돌아가는 후속 계획을 금지합니다. 경로 변경 횟수 상한은 두지 않습니다.',
      '5. 기숙사 등 가까운 목적지는 도보 귀가를 고려하고, 걷는 중 실제 정류장에서 호환 버스를 타는 기회를 둡니다. 못 타면 원래 도보를 이어갑니다.',
      '6. 먼 서울대입구역 목적지는 장거리 직접 도보 대신 정문 밖21128을 마지막 버스 대안으로 둡니다. 정식 최종 대안에 도착하면 교내로 다시 올라가지 않습니다.','',
      '7. 대학동 목적의 마지막5516은 대학동 방향만 허용하여, 노량진 방향으로 타고 한참 돌아오던 사례를 제거했습니다.',
      '**운영 교체는 권고하지 않습니다.** 기존 관측과의 차이가 남고,20분 초과도 있습니다. 행동 구현 결과를 확인하는 비공개 후보로 보존합니다.','',
      '## 결과 해석','',
      f"전체 기록의 최대 연속대기는 **{r['max_all_recorded_wait_min']:.2f}분**입니다.20분 초과 대기 구간 가중치 합은{r['over20_episode_weight']:.3f},미완료 여정 가중치 합은{r['unserved_weight']:.3f}입니다. 구간 가중치는 고유 학생 수가 아닙니다. 20분을 넘는 기록도 모두 보존했습니다. 기존 엄격한 모든 대기20분 이하 기준은 {'충족했습니다' if r['old_strict_twenty_minute_gate_passed'] else '충족하지 못했습니다'}.",'',
      '비교 기준은 운영V11이 아니라 이전 비공개 후보261112220847입니다. 셔틀 선호와 장거리 설입 도보 제한이 추가되므로 대기나 총시간이 늘어날 수 있습니다. 이는 실제 교통 운영을 개선한 효과가 아니라 행동 가정을 바꾼 모의 결과입니다. 평균/p99/최장과 관측 오차를 함께 공개했습니다. 실제 학생 행동에 더 정확해졌는지는 새 관측으로 확인해야 합니다.','',
      '- [요일별 결과·검증·과거 관측 비교](grid-RESULTS.md)',
      '- [모든 정류장 전체 기록 대기 표](grid-all-recorded-stops.csv)',
      '- [전체 기록 정류장·진입시각30분별 대기 표](grid-all-recorded-half-hour-waits.csv)',
      '- [정문 밖 유입·탑승 진단](gate-flow-diagnosis-v2.json)',
      '- [잘못된 방향 사례 수정 전후](direction-repair-diagnosis.json)',
      '- [승차 방향 검사 범위와 실패한 검사 보존](DIRECTION_AUDIT_SCOPE.md)',
      '- [수업 종료부터 귀가까지 비교](class-end-journey-comparison.csv)',
      '- [개인 한계를 넘긴 대기 원표](grid-wait-threshold-diagnosis.json)',
      '- [가정과 자료·출처](ASSUMPTIONS_AND_SOURCES.md)',
      '- [최종 검산과 운영 보존 확인](grid-final-verification.json)',
      '- [결과표 수치 검산](export-reconciliation.json)','',
      f"완료 원장 재사용은{check['reused_equivalent_completed_runs']}조건입니다. 실행 코드가 바뀐 최종 방향 수정 후보의10조건은 각각 한 번 새로 계산했습니다. 초기 실패와 모든 중간 후보, 원래 STARTED와 결과를 보존했습니다. 과거 네 줄 관측은 재사용 실측 비교로 분리합니다.",'',
      '현재 공개 지도·경로 추천·활성latest는 변경하지 않았습니다. 후보 원장과 문서를 구현 담당자에게 전달하는 단계이며, 운영 교체나 사이트 연결이 완료된 것으로 표시하지 않습니다.','']
    put(w/'START_HERE.md','\n'.join(lines))
    scripts={p.name:sha(p) for p in ROOT.glob('*.py')}
    docs={n:sha(w/n) for n in ['START_HERE.md','ASSUMPTIONS_AND_SOURCES.md','grid-RESULTS.md','grid-final-verification.json','export-reconciliation.json']}
    put(w/'handoff-manifest.json',json.dumps({'release_id':w.name,'created_at':datetime.now(timezone.utc).isoformat(),'analysis_scripts_sha256':scripts,'documents_sha256':docs,'runtime_code_sha256':v['source_sha256'],'production_writes':False,'new_field_accuracy':'NOT_EVALUATED'},ensure_ascii=False,indent=2))
    print('HANDOFF_DOCUMENTS_READY',w.name,flush=True)
if __name__=='__main__':main()
