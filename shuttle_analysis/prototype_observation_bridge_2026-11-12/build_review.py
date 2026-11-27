"""Technical review of the observation bridge and its finite private pilots."""
from pathlib import Path
from datetime import datetime,timezone
import csv,hashlib,json,math

ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    assert not p.exists()
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
def n(x,d=2):return '미확보' if x is None else f'{x:.{d}f}'

def main():
    target=ROOT/'RESULTS.md';assert not target.exists()
    assessment=read(ROOT/'assessment.json');reconciliation=read(ROOT/'peer_contract_reconciliation.json')
    assert assessment['model_input_connection_eligible'] and reconciliation['status']=='PASS_EXACT_ADJACENT_EXTRACTION_MATCH'
    identity=read(ROOT/'stop_identity_reconciliation.json');assert identity['status']=='PASS' and not identity['mismatches']
    candidate=Path(read(ROOT/'private_candidate.json')['directory']);pilots=read(candidate/'pilot_validation.json')
    assert pilots['cases']==2 and pilots['invariant_audits']=='PASS'
    creation=read(candidate/'creation_manifest.json')
    for file,digest in creation['parent_source_sha256'].items():assert sha(Path(creation['parent'])/file)==digest
    for file,digest in assessment['outputs'].items():assert sha(ROOT/file)==digest
    latest=ROOT.parent/'simulation_viewer_2026-11-07/public/routing-model/latest.json'
    assert sha(latest)==creation['production_latest_sha256']
    cells=list(csv.DictReader((ROOT/'segment_corrections.csv').open(encoding='utf-8-sig')))
    changed=[r for r in cells if abs(float(r['old_seconds'])-float(r['candidate_seconds']))>1e-9]
    assert len(changed)==assessment['changed_profile_cells']
    assert all(float(r['candidate_seconds'])>=float(r['kinematic_minimum_seconds'])-1e-5 for r in cells)
    assert all(int(r['training_interval_n'])>=5 for r in changed)
    allrow=next(r for r in assessment['comparison'] if r['route']=='ALL')
    percent=100*(1-allrow['candidate_mae_seconds']/allrow['old_mae_seconds'])
    table=[]
    for result in pilots['results']:
        r10=result['r10_reference'];scenario=result['case']['scenario']
        for scope in ('all','engineering_snu'):
            before=r10['scope'][scope];after=result['scope'][scope]
            assert abs(before['weight']-after['weight'])<1e-6
            row={'scenario':scenario,'scope':scope,'input_trip_weight':after['weight'],
                 'r10_max_stop_wait_min':r10['maximum_continuous_wait_min'],
                 'candidate_max_stop_wait_min':result['maximum_continuous_wait_min'],
                 'candidate_over20_weight':result['over20_weight'],'candidate_unserved_weight':result['unserved_trip_weight']}
            for name in ('walk_min','wait_min','ride_min','total_min','changes'):
                row['r10_'+name]=before['metrics'][name]['prototype']
                row['candidate_'+name]=after['metrics'][name]['prototype']
            table.append(row)
    p=ROOT/'pilot_comparison.csv';assert not p.exists()
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(table[0]));w.writeheader();w.writerows(table)
    issues=[
      {'issue':'시내버스 시간대별 구간시간','status':'별도 후보에 연결하고 날짜 분리 사후점검','evidence':'678개의 지원되는 구간×시간 셀만 갱신; 출발시계/정원/수요/행동 보존'},
      {'issue':'학습·점검 자료 혼용','status':'학습일과 점검일을 코드로 분리','evidence':'11/10만 학습; 11/11의 관측값 변경이 학습값에 영향을 주지 않는 검사 통과. 이미 기술적 탐색에 쓴 11/11은 최종 미사용 검증일이 아님'},
      {'issue':'셔틀 실제 배차간격·묶음 운행 빈도','status':'현 자료로 식별 불가','evidence':'BUSIN 연속 운행 이력 없음; 도식 좌표를 GPS로 해석하지 않음'},
      {'issue':'시내버스 교외 재차 인원·등급별 인원','status':'수치 보정 보류','evidence':'순서형 등급만으로 인원/여석/순수 승하차수 식별 불가'},
      {'issue':'관악02 혼잡도','status':'결측 유지','evidence':'유효 등급 부재를 0명/여유로 치환하지 않음'},
      {'issue':'반복 왕복·긴 여정·미래 정보 공유·승차 선택','status':'이번 입력 보정과 분리하여 미해결로 유지','evidence':'R10 행동 엔진과 비용식은 그대로; 시간 보정이 해결했다고 주장하지 않음'},
      {'issue':'실제 승하차 체류와 준비시간','status':'현 자료로 분리 불가','evidence':'검출간 시간에 체류가 포함될 수 있어 일괄 정차 가산 금지'},
      {'issue':'실측 줄 길이와 개인 대기 정확도','status':'NOT_EVALUABLE','evidence':'새 날짜의 정렬된 줄/개인 대기 정답 없음; 버스 검출시간 오차와 구분'}]
    summary={'created_at':datetime.now(timezone.utc).isoformat(),'candidate':str(candidate),
      'detected_interval_mae_before_seconds':allrow['old_mae_seconds'],
      'detected_interval_mae_after_seconds':allrow['candidate_mae_seconds'],'relative_reduction_percent':percent,
      'date_split_check_interval_n':assessment['mapped_check_intervals'],'unmapped_intervals':assessment['unmapped_check_intervals'],
      'changed_profile_cells':len(changed),'private_pilot_status':pilots['status'],'private_pilot_cases':pilots['cases'],
      'maximum_continuous_wait_min':pilots['maximum_continuous_wait_min'],
      'over20_episode_weight':pilots['over20_episode_weight'],'unserved_trip_weight':pilots['unserved_trip_weight'],
      'queue_empirical_accuracy':'NOT_EVALUABLE','pristine_holdout':False,'production_replacement_allowed':False,
      'issues':issues,'pilot_comparison':table,
      'source_sha256':{'assessment':sha(ROOT/'assessment.json'),'peer_contract_reconciliation':sha(ROOT/'peer_contract_reconciliation.json'),
         'pilot_validation':sha(candidate/'pilot_validation.json'),'operations':sha(candidate/'frozen/operations_observed_train_v1.json')},
      'production_local_latest_sha256':sha(latest),'production_model_id':read(latest)['model_id']}
    write(ROOT/'review.json',summary)
    lines=['# 실측 자료를 연결한 R 후속 후보 검토',
      f'\n작성 {summary["created_at"]}. **실측 검출시간 보정 / 수요일 두 조건의 내부 감사 / 공개 V11 교체 없음.**',
      '\n사용자 요청으로 실측 분석 중인 구현 에이전트와 문제 목록·근거를 공유하고, 자료로 확인할 수 있는 구간시간부터 별도 후보에 연결했다. 반복 왕복 등 행동 가설을 동시에 바꾸지 않아 입력 보정의 효과를 분리했다.',
      '\n## 실측 자료와 적용 범위',
      '\n11/7~11/11 저장 이력 중 현재 검출기와 집계가 일치하는 11/10·11/11을 사용했다. 11/10만으로 학습하고 11/11로 날짜 분리 사후점검했다. 11/11은 구현 에이전트가 이미 기술적으로 탐색한 날짜이므로 완전히 미사용인 최종 검증일이 아니다.',
      '\n검출 조건은 stopFlag, 정류장 GPS 반경 60m, 직전 공급자 갱신 120초 이내다. 첫 검출시각은 정확한 정류장 도착/출발시각이 아니며, 두 검출 사이 시간에는 정차·신호·공급자 시각오차가 포함된다. 순수 주행시간이나 승하차 체류라고 부르지 않고 정차시간을 또 더하지 않았다.',
      f'\n기존 R망과 순번이 맞는 인접 검출구간 **{assessment["mapped_check_intervals"]:,}개**에서 평균절대오차가 **{n(allrow["old_mae_seconds"])}초 → {n(allrow["candidate_mae_seconds"])}초**, 상대 감소는 **{n(percent,1)}%**였다. 매핑되지 않는 **{assessment["unmapped_check_intervals"]:,}개**는 억지로 연결하지 않았다. 학습이 부족해 기존값을 유지한 셀도 전체 오차 비교에 포함했다.',
      '\n|노선|점검 검출구간 수|기존 평균절대오차(초)|후보 평균절대오차(초)|',
      '|---|---:|---:|---:|']
    for r in assessment['comparison']:
        if r['route']=='ALL':continue
        lines.append(f'|{r["name"]}|{r["n"]}|{n(r["old_mae_seconds"])}|{n(r["candidate_mae_seconds"])}|')
    lines += ['\n이 수는 독립 승객·독립 차량·독립 일수의 수가 아니다. 동일 차량/회차/날짜의 상관이 남으며 통계적 신뢰구간이나 대기열 예측 정확도 개선을 주장하지 않는다.',
      '\n[날짜 분리 비교 원표](day_split_time_comparison.csv) · [셀별 보정과 fallback](segment_corrections.csv) · [원본·코드 해시](assessment.json) · [추출 계약 대조](peer_contract_reconciliation.json) · [279개 정류장 ID·진행순번 일치 검산](stop_identity_reconciliation.json).',
      '\n## R 후보에 실제로 연결한 내용',
      f'\n구간×시간 {len(cells):,}셀 중 지원되는 **{len(changed):,}셀**만 학습 중앙값으로 바꿨다. 학습 관측 5개 미만은 기존값을 유지했고, 교내 40km/h 등을 반영한 기존 물리 최소시간을 지켰다. 다섯 요일에 같은 학습표를 전이한 것은 시나리오이며 요일 효과를 추정한 결과가 아니다.',
      '\n차량 출발그리드·셔틀 배차·정원·입력 통행·목적지·경로 선택 비용과 변경 위험률은 R10과 같다. 변경 횟수는 무제한이고, 기본 0.3^n 감소와 만차/대기 스트레스는 그대로다. 새 관측 통과간격을 차고지 출발간격으로 바꾸지 않았다. 시내버스 배차 분포는 기존 월요일 시나리오가 남아 있음을 입력 메타데이터에 분리했다.',
      f'\n후보: `../{candidate.name}`. [후보 계획](../{candidate.name}/PLAN.md) · [실행 조건](../{candidate.name}/experiment_lock.json) · [새 운행 입력](../{candidate.name}/frozen/operations_observed_train_v1.json).',
      '\n## 수요일 일반·피크 내부 검사',
      f'\n검사 범위는 수요일 regular/peak, seed0의 두 조건이다. **판정 {pilots["status"]}**, 최대 연속 정류장 대기 {n(pilots["maximum_continuous_wait_min"],5)}분, 20분 초과 가중 방문 {n(pilots["over20_episode_weight"],6)}, 미완료 통행 {n(pilots["unserved_trip_weight"],6)}이다. 전체 평일과 모든 난수를 검증한 것은 아니다.',
      '\n|공급|범위|입력 가중 통행|누적 대기 R10→후보(분)|도보 R10→후보(분)|총시간 R10→후보(분)|',
      '|---|---|---:|---:|---:|---:|']
    for r in table:lines.append(f'|{r["scenario"]}|{r["scope"]}|{n(r["input_trip_weight"])}|{n(r["r10_wait_min"])}→{n(r["candidate_wait_min"])}|{n(r["r10_walk_min"])}→{n(r["candidate_walk_min"])}|{n(r["r10_total_min"])}→{n(r["candidate_total_min"])}|')
    lines += ['\nall은 같은 전체 입력 통행, engineering_snu는 301·302동 출발→서울대입구역 목적지의 같은 부모 통행이다. 가중 통행을 실제 고유 학생수로 해석하지 않는다. 총시간의 종점은 모형 거점이며 개인 집까지의 시간이 아니다.',
      '\n|공급|최대 연속 대기 R10→후보(분)|누적 대기 p99 R10→후보(분)|총시간 최대 R10→후보(분)|',
      '|---|---:|---:|---:|']
    for result in pilots['results']:
        ref=result['r10_reference'];before=ref['extended_diagnostics']['finished_trip_quantiles'];after=result['extended_diagnostics']['finished_trip_quantiles']
        lines.append(f'|{result["case"]["scenario"]}|{n(ref["maximum_continuous_wait_min"])}→{n(result["maximum_continuous_wait_min"])}|{n(before["cumulative_wait_min"]["p99"])}→{n(after["cumulative_wait_min"]["p99"])}|{n(before["total_min"]["maximum"])}→{n(after["total_min"]["maximum"])}|')
    lines += ['\n한 정류장 연속 대기는 11:20~23:10에 겹친 방문이며 도보 이탈도 포함한다. 누적 대기·전체 여정 꼬리는 전체 기록을 따로 검사했다. 같은 줄의 시계를 초기화하거나 20분에 강제로 이탈시키지 않았다. 수지·정원·호환 FIFO·차량시계·대기열을 감사 원장에서 별도 재구성했다.',
      f'\n[두 조건 전체 감사](../{candidate.name}/pilot_validation.json) · [R10 대조 원표](pilot_comparison.csv) · [35개 기존 경계·통합 검사](../{candidate.name}/boundary-and-integration-tests.log). 입력 학습/결측/방향/물리 최소시간/시간 경계 검사는 별도 5개를 통과했다.',
      '\n## 해결한 항목과 남은 항목',
      '\n|문제|이번 처리|근거·남은 범위|','|---|---|---|']
    for r in issues:lines.append(f'|{r["issue"]}|{r["status"]}|{r["evidence"]}|')
    lines += ['\n구현 에이전트가 정제한 [계약 원문](../collected_data_review_2026-11-12/calibration_contract.json), [통과간격·혼잡 전이 후보](../collected_data_review_2026-11-12/calibration_candidates.json), [안정된 두 날짜의 통과간격 표본](../collected_data_review_2026-11-12/headway_samples_stable_dates.json)을 함께 공유했다. 혼잡등급 증감을 정류장별 순수 승하차 인원으로 변환하지 않는다.',
      '\n셔틀 장기 기록은 최신 BUSIN 캐시만으로 복원할 수 없다. 관악02 두 노선의 혼잡등급 결측은 빈 버스로 바꾸지 않는다. 새로운 날짜의 정렬된 대기열·개인 승차·거점 도착 자료가 없으므로 대기열 정확도는 NOT_EVALUABLE이다.',
      '\n운영 V11/latest와 경로 앱 활성 모델은 이번 작업에서 바꾸지 않았다. 이 후보는 사용자 새 명시 승인 전 운영으로 승격하지 않는다. 이전 R10·실패 실험·수집 원자료는 보존했다.']
    target.write_text('\n'.join(lines)+'\n',encoding='utf8')
    write(ROOT/'review_verification.json',{'status':'PASS_SOURCE_AND_SCOPE_RECONCILIATION','report_sha256':sha(target),
         'review_sha256':sha(ROOT/'review.json'),'candidate':str(candidate),'private_cases':2,
         'profile_cells':len(cells),'changed_profile_cells':len(changed),'production_writes':False})
    print('BRIDGE_REVIEW_CREATED',pilots['status'],target,flush=True)

if __name__=='__main__':main()
