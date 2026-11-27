"""Reviewer-facing V12 integration record; never a promotion request or publisher."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import argparse,csv,hashlib,json,math

ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent;KST=timezone(timedelta(hours=9))
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def n(x,d=2):return '미확보' if x is None else f'{x:.{d}f}'
def csvout(p,rows):
    assert not p.exists()
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)

def main(release):
    release=Path(release).resolve();target=release/'RESULTS.md';assert not target.exists()
    v=read(release/'validation.json');e=read(release/'evidence_validation.json');inputs=read(release/'observed_input_backtest_mapped.json')
    inventory=read(release/'evidence_inventory.json');ops=read(release/'frozen/operations_v12_empirical.json');manifest=read(release/'creation_manifest.json')
    assert len(v['results'])==10 and inventory['pending_historical_source_inventory'] is False
    versions=[];engineering=[]
    for r in v['results']:
        case=r['case'];m=r['scope']['all']['metrics'];ref=r['r10_reference'];t=ref['scope']['all']['metrics']
        for scope,dest in [('all',versions),('engineering_snu',engineering)]:
            current=r['scope'][scope];before=ref['scope'][scope];assert abs(current['weight']-before['weight'])<1e-6
            dest.append({'weekday':case['day'],'scenario':case['scenario'],'scope':scope,'input_trip_weight':current['weight'],
              **{f'{model}_{key}':current['metrics'][key]['baseline'] if model=='V11' else before['metrics'][key]['prototype'] if model=='R10' else current['metrics'][key]['prototype']
                for model in ('V11','R10','V12') for key in ('walk_min','wait_min','ride_min','total_min','changes')},
              'r10_network_max_stop_wait_min':ref['maximum_continuous_wait_min'],'v12_network_max_stop_wait_min':r['maximum_continuous_wait_min'],
              'v12_over20_episode_weight':r['over20_weight'],'v12_unserved_trip_weight':r['unserved_trip_weight'],
              'v12_network_late_finished_trip_weight':r['late_finished_weight']})
    csvout(release/'weekday_comparison.csv',versions);csvout(release/'engineering_snu_comparison.csv',engineering)
    with (release/'field_queue_comparison.csv').open(encoding='utf-8-sig') as f:fields=list(csv.DictReader(f))
    primary=[];worse=0
    for event in e['events']:
        rows={r['model']:r for r in fields if r['scenario']=='regular' and r['observation_id']==event['observation_id']}
        assert len(rows)==3;primary.append((event,rows));err='expected_absolute_distance_to_count_or_interval'
        worse+=float(rows['V12'][err])>float(rows['V11'][err])+1e-7
    allsegment=next(r for r in inputs['segment_errors'] if r['route']=='ALL');hw=inputs['headway_interval_errors'];tr=inputs['ordinal_transition']
    status={}  # local classification counts, not model accuracy
    for item in inventory['items']:status[item['integration_status']]=status.get(item['integration_status'],0)+1
    rawmax=max(r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min'] for r in v['results'])
    rawover=math.fsum(r['extended_diagnostics']['all_recorded_time_over20_episode_weight'] for r in v['results'])
    late=math.fsum(r['late_finished_weight'] for r in v['results'])
    review={'release_id':v['release_id'],'version_family':'V12','created_at':datetime.now(KST).isoformat(),
      'operating_reference':'capacity_v11/261110162302','code_parent':manifest['parent'],'lineage':inventory['lineage'],
      'internal_status':v['status'],'cases':10,'maximum_continuous_wait_min':v['maximum_continuous_wait_min'],
      'over20_episode_weight':v['over20_episode_weight'],'unserved_trip_weight':v['unserved_trip_weight'],
      'all_recorded_max_continuous_wait_min':rawmax,'all_recorded_over20_episode_weight':rawover,'late_finished_weight_sum_across_conditions':late,
      'field_regular_cases_worse_than_V11':worse,'queue_empirical_accuracy':'NOT_EVALUABLE','pristine_holdout_dates':[],
      'source_classification_counts':status,'weekday_comparison':versions,'engineering_comparison':engineering,
      'ordinal_grade_people_conversion':False,'production_replacement_allowed':False,
      'validation_sha256':sha(release/'validation.json'),'evidence_validation_sha256':sha(release/'evidence_validation.json'),
      'inventory_sha256':sha(release/'evidence_inventory.json'),'observed_input_backtest_sha256':sha(release/'observed_input_backtest_mapped.json')}
    (release/'review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf8')
    lines=[f'# V12 실측 통합 후보 {v["release_id"]}',
      f'\n작성 {review["created_at"]}. **비운영 후보 / 내부 판정 {v["status"]} / 현장 대기 정확도 NOT_EVALUABLE / 공개 V11 유지.**',
      '\n## 기준과 연결 범위',
      '\n운영 기준은 V11의 같은 수강 기반 통행 수요와 44명/피크 두 차량 계약이다. 구현 계보는 R10의 분리된 보행·선호·무제한 경로 변경 → 261112104829의 실측 구간시간 후보 → 이번 V12 통합이다. V11의 행동을 그대로 복제한 버전이라는 뜻은 아니다. 릴리스 ID는 YYMMDDhhmmss이고 V12는 version_family 메타데이터다.',
      f'\n총 {len(inventory["items"])}개 인벤토리 항목을 코드·입력·검증 경로에 대응했다. [전체 인벤토리](evidence_inventory.json), [수강/수요·보존 기준](input_manifest.json), [실행 전 고정 조건](experiment_lock.json), [계보와 해시](creation_manifest.json)를 참조한다.',
      '\n|자료|이번 연결|구분해야 할 범위|','|---|---|---|',
      '|8개 시내버스 통과간격|정류장·진행순번·시간별 분포와 장단 간격을 공급/예측 참조에 연결|기준 정류장 통과시계를 역산한 조건부 공급. 차고지 출발시계로 복사하지 않음|',
      '|인접 구간 검출시간|678개 지원 구간×시간 knot 보정 및 분포·변동 진단|학습 부족 fallback과 미매핑을 보존. 순수 주행시간이나 승하차 체류가 아님|',
      '|혼잡 분포·동일 차량 전이|4개 순서형 상태 확률을 예측과 혼잡 불편 시나리오에 연결|인원·여석·승하차수로 변환하지 않음. 비용 계수는 미보정 가정|',
      '|만차표시|유효 관측 범위와 비율을 예측 진단에 연결|full=false는 여석수, full=true는 실제 승차거절 표본이 아님|',
      '|현장 줄·개인 대기|최신 수정본을 분 단위 창의 진단 제약으로 연결|53명·5명·33~39명·67명. 189초+30초는 한 사람의 한 사건|',
      '|셔틀 정원·두 차량 경험|행정관→설입만 주간44명/피크 두 차량 조건부 공급 유지|매3분마다 반드시 두 대라는 연속 실측은 없음. 타 셔틀 정원 변경 없음|',
      '|역사 승하차·T-data·교통카드|8개 자료군의 원본/추정치/보존 범위/단위를 검증 문맥에 연결|승차는 served demand. 월시간대×일총량을 날짜시간 실측으로 만들지 않음|',
      '|미확보·미식별 자료|별도 UNAVAILABLE_NOT_APPLIED 항목과 fallback 명시|셔틀 연속GPS/배차, 마을버스 등급, 교외 수치재차, 전역 승하차체류, 카드 전체교내추출|',
      '\n[런타임 실측 입력](frozen/empirical_evidence.json) · [운행 시나리오](frozen/operations_v12_empirical.json) · [과거 자료 단위·범위](frozen/historical_evidence_context.json) · [현장 관측 사용 장부](field_observation_usage_ledger.json).',
      '\n## 공급 시계와 시간대 경계 수정',
      '\n정류장 검출 간격은 해당 노선의 방향이 확인된 기준 정류장 통과 과정으로 연결했다. 그 통과시각을 구간 진입시간별 경과시간으로 거꾸로 풀어 첫 모형 정류장의 시작시각을 정했다. 공식 대표간격 fallback·관측누락에 의한 긴 간격·15초 미만/3600초 초과 절단·관측 시간 밖의 기존 시계는 구분한다. 실제 차고지 출발·보유차량 운영표를 재현했다고 주장하지 않는다.',
      '\n초기 미실행 후보 261112111414에서는 계단형 시간대 프로파일 때문에 역산 오차가 최대 약233초였다. 이 후보와 검사 기록을 보존하고, 구간 진입시각에서 시간 knot를 선형 연결했다. 각 링크 도착함수의 기울기 1+Δduration/Δtime>0을 검사해 경계에서 도착 순서가 뒤집히지 않도록 했다. 실측 knot 값과 기존 물리 최소시간은 보존한다. 이 연속 연결 자체는 계산 모형의 가정이다.',
      f'\n현재 최소 링크 도착 기울기 **{n(ops["minimum_link_arrival_derivative"],6)}**, 기준 정류장 역산 최대 오차 **{n(ops["inverse_phase_diagnostic_max_abs_seconds"],9)}초**이다. [공급 역산 원표](anchor_supply_diagnostics.csv), [시각 보간 코드](time_profiles.py), [읽기 전용 독립 검토](../collected_data_review_2026-11-12/v12_support/read_only_review_261112111627/READ_ONLY_REVIEW.md)를 참조한다.',
      '\n독립 검토는 60,975개 경계 전후 값과 5개 요일 4,635개 도시버스 여정의 시계 일치를 확인했다. 이는 구현 정합성 검사이며 현장 도착시각의 정확도 입증이 아니다. 현재는 같은 화요일 프로파일을 모든 요일에 전이한다. 향후 요일별 프로파일이 생기면 역산 함수에도 요일을 전달해야 한다.',
      '\n## 날짜를 나눈 실측 대용값 점검',
      '\n학습일은 11/10, 사후점검일은 11/11이다. 11/11은 이미 기술적으로 탐색했으므로 완전히 미사용인 최종 검증일이 아니다. 검출 간 시간에는 GPS/stopFlag/제공시각 오차와 정차가 포함될 수 있으며, 같은 차량·회차·날짜의 표본은 독립이 아니다.',
      f'\n정확한 첫 검출시각을 원본에서 다시 구성해 원래 인접 검출간격과 일치시켰다. R망에 매핑되는 **{allsegment["old"]["n"]:,}개**에서 구간 검출시간 평균절대오차는 기존 R10의 시간표 **{n(allsegment["old"]["mae_seconds"])}초 → V12 연속 모형 {n(allsegment["v12_continuous"]["mae_seconds"])}초**였다. {inputs["unmapped_segment_intervals"]:,}개 미매핑 구간은 대체하지 않았다. 앞선 계단형 구간 후보의28.96초와 이번 연속 모형을 혼동하지 않는다.',
      f'\n정류장 통과간격 {hw["training_stop_median"]["n"]:,}개에서 공식 대표간격 참조의 오차 {n(hw["official_nominal_reference"]["mae_seconds"])}초 → 학습 정류장 중앙값 {n(hw["training_stop_median"]["mae_seconds"])}초였다. 학습 부족 {hw["unsupported_intervals"]:,}개와 모형 바깥 {hw["unmapped_intervals"]:,}개는 별도다. 이는 차량 검출간격 비교이며 개인 대기시간 비교가 아니다.',
      f'\n혼잡 전이의 다범주 Brier 점수는 모형 안의 {tr["n"]:,}개 연결 기록에서 마지막 등급 유지 {n(tr["carry_previous_grade_brier"],4)} → 전이확률 {n(tr["brier"],4)}였다(낮을수록 좋음). 모형 밖 {tr["unmapped_pairs"]:,}개 연결은 분리했다. 이를 정확도 백분율이나 인원 오차로 바꾸지 않는다. [범위를 일치시킨 사후점검](observed_input_backtest_mapped.json) · [모형 밖도 포함했던 원래 등급 진단](observed_input_backtest.json).',
      '\n## 월~금 일반·피크 대기와 전체 시간',
      f'\n10조건의 전체 원장 감사를 마쳤다. **최대 연속 정류장 대기 {n(v["maximum_continuous_wait_min"],5)}분**, 20분 초과 가중 대기 방문 {n(v["over20_episode_weight"],6)}, 미완료 통행 {n(v["unserved_trip_weight"],6)}이다. 20분을 강제 이탈이나 인원 삭제로 맞추지 않았다. 대기 중 도보로 빠진 방문도 포함했다.',
      f'\n주 기준은11:20~23:10에 겹친 연속 대기다. 창 밖 초기 기록까지 포함한 최대는 {n(rawmax,5)}분,20분 초과 가중 방문은 {n(rawover,6)}이다. 종료시각 뒤 완료된 가중 통행은 조건 합계 {n(late,6)}으로 미완료와 구분했다. 여러 조건의 합을 고유 학생 수로 해석하지 않는다.',
      '\n|요일·공급|전체 평균 거점 도착 V11 / R10 / V12(분)|누적 대기 V11 / R10 / V12(분)|최대 연속 대기 R10→V12(분)|20분 초과 가중 방문|',
      '|---|---:|---:|---:|---:|']
    for r in versions:lines.append(f'|{r["weekday"]} {r["scenario"]}|'+ ' / '.join(n(r[x+'_total_min']) for x in ('V11','R10','V12'))+'|'+ ' / '.join(n(r[x+'_wait_min']) for x in ('V11','R10','V12'))+f'|{n(r["r10_network_max_stop_wait_min"])}→{n(r["v12_network_max_stop_wait_min"])}|{n(r["v12_over20_episode_weight"],6)}|')
    lines += ['\n같은 부모 통행·출발시각·목적지·질량과 셔틀 계약을 대조했다. 시내 공급·시간·혼잡 선택 문맥은 새 실측 시나리오로 달라졌으므로 이 표를 동일 공급의 행동만 바꾼 인과효과로 해석하지 않는다. 실제 고유 학생/개별 집 도착/실시간 예측도 아니다.',
      '\n[요일 원표](weekday_comparison.csv) · [301/302동→설입 같은 통행 비교](engineering_snu_comparison.csv) · [전 정류장990행](all_stops_waits.csv) · [정류장 도착30분별](half_hour_waits.csv) · [전체 감사](validation.json).',
      '\n## 극단 여정과 반복 방문',
      '\n평균 개선으로 긴 여정을 가리지 않는다. 앞선 구간보정만 연결한261112104829에서 수요일regular 최대108.40→133.97분으로 악화했고 peak180.83분이 남았던 기록도 보존한다. 다음은 같은 조건에서 이번 V12까지의 대조다.',
      '\n|요일·공급|총시간 최대 R10→V12(분)|도보 p99 R10→V12(분)|누적 대기 p99 R10→V12(분)|최대 변경횟수|',
      '|---|---:|---:|---:|---:|']
    for r in versions:
        ts={t['metric']:t for t in e['tails'] if t['weekday']==r['weekday'] and t['scenario']==r['scenario']}
        loop=next(x for x in e['route_revisits'] if x['weekday']==r['weekday'] and x['scenario']==r['scenario'])
        lines.append(f'|{r["weekday"]} {r["scenario"]}|{n(ts["total_min"]["r10_maximum"])}→{n(ts["total_min"]["v12_maximum"])}|{n(ts["walk_min"]["r10_p99"])}→{n(ts["walk_min"]["v12_p99"])}|{n(ts["cumulative_wait_min"]["r10_p99"])}→{n(ts["cumulative_wait_min"]["v12_p99"])}|{loop["maximum_changes"]}|')
    lines += ['\n변경 횟수 상한은 없다. 재방문이 모두 오류라는 뜻은 아니지만, 반복 왕복·긴 여정은 여전히 별도 품질 대상이다. 이번 실측 통합은 해당 행동 문제가 해결됐다는 선언이 아니다. 실제 운행의 미래 시계와 판단 시계가 공유되는 한계, 승차 때의 두 단계 선택과 내생적 조기하차 미구현도 남는다.',
      '\n[꼬리40행](journey_tails.csv) · [최장 경로·재방문 진단](evidence_validation.json).',
      '\n## 현장 줄 네 건과 개인 대기',
      '\n각 보고 분 안의 미상 초를 균등시점으로 놓아 줄을 시간적분했다. 문화관21297 방향은 미확정이고 날짜는 대화 맥락에서 추정했다. 33~39를 정확한36명으로 바꾸지 않았다. 기존 모델 선택에 이미 쓰인 보고이므로 새 독립 정확도 평가가 아니다.',
      '\n|보고|관측|분내 평균 V11 / R10 / V12|기대 절대오차 V11 / R10 / V12|',
      '|---|---:|---:|---:|']
    for event,rows in primary:
        label=str(event['low']) if event['low']==event['high'] else f'{event["low"]}~{event["high"]}'
        models=('V11','prototype_V8','V12')
        lines.append(f'|{event["day"]} {event["minute"]} {event["stop"]}|{label}|'+ ' / '.join(n(float(rows[m]['uniform_minute_mean'])) for m in models)+'|'+ ' / '.join(n(float(rows[m]['expected_absolute_distance_to_count_or_interval'])) for m in models)+'|')
    lines += [f'\nregular 기준 네 보고 중 {worse}건에서 V12의 줄 오차가 V11보다 컸다. peak도 [전체24행](field_queue_comparison.csv)에 함께 보존했다. 가장 잘 맞는 초나 공급 조건을 골라 판정하지 않았고 이 보고에 계수를 재적합하지 않았다.',
      '\n11/10 최신 보고는 밖의 줄에 본인 포함67명/앞66명, 한 사람의 줄 대기189초, 승차 후 출발30초다. 두 사진과67명을 독립 대기 표본으로 늘리지 않았다. 44명 두 차량은 개별 공급으로 유지한다. 전역 모형의 도착·승차·출발은 아직 한 사건 근사여서189초와30초의 분리 재현은 NOT_EVALUABLE이다. 관측 도착시각 미상과 ‘아마15:24이후’의 불확실한 회상도 그대로다.',
      '\n[최신 관측·사용 장부](field_observation_usage_ledger.json).',
      '\n## 자료 부족과 운영 경계',
      '\n셔틀은 최신 BUSIN 캐시만 있고 연속 실운행 이력이 없어 실제 배차 분포·두 대 빈도·교통량별 실주행을 학습하지 않았다. 관악02 두 노선 혼잡등급은 결측이다. 서울시 API0(정보 없음)과 정규화CSV0(API3, 여유)를 구분한다. [공식 API 항목 정의](https://www.data.go.kr/data/15000332/openapi.do). 숫자 외부 재차·여석·개별 승하차수는 순서형 등급으로 만들지 않았다.',
      '\n과거 자료는 월별시간대/일별/시간대별구간재차합/원시거래 등 단위를 보존한다. T-data 원본26일과 기존 정규화10일을 구분하고, 교통카드 ZIP 내부 확인일11/5를 파일명11/9와 혼동하지 않는다. DC/DD/DX의 전행 교내 추출은 미완료다. 참고표23개를23일치 완료 여정으로 확대하지 않는다.',
      '\n11/11 이후 새 완료 관측일은 아직 없다. 최초 후속 완료일을 점수와 무관한 사전 품질 기준으로 분리한다. 검토는11/13 00:00KST 이후 가능하다는 규칙만 보존했고 알람·작업·자동다운로드는 만들지 않았다. [평가일 보존 규칙](evidence/collected_data_review_2026-11-12/v12_support/future_holdout_rule.json).',
      '\n**V11/latest/경로 앱 활성 모델을 이번 후보로 교체·배포하지 않았다.** 사용자 새 명시 승인 전 승격하지 않는다. 내부검사와 검출시간/등급 사후점검이 개인 대기·하교 정확도나 운영 준비 완료를 입증하지 않는다. 원본·기존후보·실패·미실행후보를 모두 보존했다.']
    target.write_text('\n'.join(lines)+'\n',encoding='utf8')
    print('V12_REPORT_CREATED',v['status'],target,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--release',required=True);a=p.parse_args();main(a.release)
