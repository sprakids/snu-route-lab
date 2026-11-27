"""Source-backed comparison against the immediately preceding behavioral model."""
from pathlib import Path
import argparse,csv,json,hashlib,math
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent/'261115160710'
def read(p):return json.loads(p.read_bytes())
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,s):
    assert not p.exists(),p
    p.write_text(s,encoding='utf8')
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve()
    v=read(w/'grid-validation.json');old=read(BASE/'grid-validation.json');behavior=read(w/'grid-behavior-validation.json');diag=read(w/'grid-diagnostics.json');waits=read(w/'grid-wait-cause-ledger.json');pilot=read(w/'pilot-validation.json')
    assert len(v['results'])==10 and behavior['status']=='PASS_STUDENT_BEHAVIOR_GATES'
    before={(r['case']['day'],r['case']['scenario']):r for r in old['results']}
    before_over=sum(r['extended_diagnostics']['all_recorded_time_over20_episode_weight'] for r in old['results']);after_over=sum(r['extended_diagnostics']['all_recorded_time_over20_episode_weight'] for r in v['results'])
    old_max=max(r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min'] for r in old['results']);new_max=max(r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min'] for r in v['results'])
    fields=rows(w/'grid-field-comparison.csv');mine=[r for r in fields if r['model']==w.name];assert len(mine)==8;err='expected_absolute_distance_to_count_or_interval';pairs=[]
    for r in mine:
        b=next(x for x in fields if x['model']==BASE.name and x['scenario']==r['scenario'] and x['observation_id']==r['observation_id'])
        pairs.append((b,r))
    olderr=math.fsum(float(b[err]) for b,r in pairs);newerr=math.fsum(float(r[err]) for b,r in pairs)
    mean_delta=[];unserved=math.fsum(r['unserved_trip_weight'] for r in v['results'])
    text=[f'# 대기·정문 예측 개선 후보 {w.name}','',
      f'직전 하교 행동 모델{BASE.name}과 동일 수요·목적지·운행·정원으로 비교했습니다. 핵심 행동은 유지했습니다.20분에 사람을 강제 이탈시키거나40명에서 줄을 잘라내지 않았습니다.','',
      f'**전체 기록 최대 연속대기 {old_max:.2f}→{new_max:.2f}분,20분 초과 가중 구간 {before_over:.3f}→{after_over:.3f}({(1-after_over/before_over)*100:.1f}% 감소)**입니다. 과거4관측을regular/peak로 비교한8건의 기대 절대오차 합은{olderr:.3f}→{newerr:.3f}({(1-newerr/olderr)*100:.1f}% 감소)입니다. 이는 재사용 관측의 조건부 적합도이며 새 실측 정확도나 실제 교통 개선 효과가 아닙니다.','',
      '## 원인과 수정','',
      '1. 기존20분 초과의97.68%는 모형이 선언한 개인 인내 안이었습니다. 중앙값20분에 미측정 로그표준편차0.25를 둬 약95%가12.3~32.7분이 된 영향이 큽니다. 중앙값과 개인차는 유지하되0.1 시나리오(약95%16.4~24.3분)를 선언하고,0.25를 유지한 별도 월요일 진단과 비교했습니다. 인내는 검토 기준이며 강제 종료가 아닙니다.',
      '2. 기존 시내버스 초기 선택은 미래 통과 초를 안다는 가정으로 최소값 하나를 골랐습니다. 초기 빈줄 기본 대기를 주어진 배차 간격의 평균 잔여대기로 바꾸고, 기존 개인 판단 오차와 거리 선호를 복원했습니다. 같은 물리 정류장의 중복 경로 수는 확률을 늘리지 않도록 대표 하나를 선택했습니다. FIFO/정원 추가 지연과 후속 경로 가능성에는 기존 시각 정보가 남습니다.',
      '3. 이미 허용 상태가 풀려도 예상 대기가 낮아지면 재검토를 닫던 제약을 고쳤습니다. 최초의 셔틀 선호와 한 번 풀린 후의 대안 검토를 구분합니다. 유지 선택, 반복 변경 회피, 무제한 변경, 재방문 금지와 정문 최종 대안은 유지했습니다.',
      '4. 비정문 P 초과 일부는 재검토 시계가 멈춘 것이 아니라 대안의 예측 비용이 커서stay를 반복했습니다. 예측 여석·선택 비용·다음 검토 시각을 지정 모의 UID에 추가 기록했습니다. 과거 최소 여석30분 경계·미래 상류 수요 미반영은 추가 확인 가설이며, 과거 학습을 꺼서 맞추지 않았습니다.','',
      '[기준 원인 원장](../v12_queue_fit_20261116/baseline-cause-ledger.json), [별도 진단](../collaboration/v12_wait_diagnosis_20261116/DIAGNOSIS.md), [실험 계획](../v12_queue_fit_20261116/PROTOCOL.md), [정보·행동 검사 범위](../v12_queue_fit_20261116/PROTOCOL_SCOPE_NOTE.md).','',
      '## 요일별 결과','',
      '총시간은 모형의 출발부터 목적지 도착까지입니다. 완료 여정의 조건부 통계이며 미완료 가중치는 별도로 공개합니다. 전체 기록은11:20~23:10 표시시간 밖 초기·마감 기록도 포함합니다.','',
      '|요일|배차|최대 연속대기 전→후|20분 초과 가중 구간 전→후|평균 총시간 전→후|p99 총시간 전→후|최장 총시간 전→후|미완료|','|---|---|---:|---:|---:|---:|---:|---:|']
    for r in v['results']:
        c=r['case'];b=before[c['day'],c['scenario']];x=r['extended_diagnostics'];y=b['extended_diagnostics'];q=x['finished_trip_quantiles']['total_min'];z=y['finished_trip_quantiles']['total_min'];mean_delta.append(q['mean']-z['mean'])
        text.append(f"|{c['day']}|{c['scenario']}|{y['all_recorded_time_max_continuous_wait_min']:.2f}→{x['all_recorded_time_max_continuous_wait_min']:.2f}|{y['all_recorded_time_over20_episode_weight']:.2f}→{x['all_recorded_time_over20_episode_weight']:.2f}|{z['mean']:.2f}→{q['mean']:.2f}|{z['p99']:.2f}→{q['p99']:.2f}|{z['maximum']:.2f}→{q['maximum']:.2f}|{r['unserved_trip_weight']:.3f}|")
    text += ['',f"평균 총시간 변화는{min(mean_delta):+.3f}~{max(mean_delta):+.3f}분입니다. 대기 감소와 총시간·긴 꼬리의 변화를 함께 봐야 합니다. 가중 구간은 고유 학생 수가 아니며 같은 수요의 두 배차 대안을 더한 값입니다.",'',
      f"[전체99노드×10조건 {diag['all_recorded_stop_rows']}행](grid-all-recorded-stops.csv), [전체기록 진입시각30분 {diag['all_recorded_half_hour_rows']}행](grid-all-recorded-half-hour-waits.csv), [여정 분포](grid-journey-comparison.csv), [수업 종료부터 도착](class-end-journey-comparison.csv).",'',
      '## 과거 줄 관측 적합도','',
      '관측 분 안의 초는 균등하게 보며 기대 절대오차와 평균의 오차를 구분합니다. 문화관 방향과 월요일 날짜에는 기존 불확실성이 남습니다. 네 관측은 이미 보정·후보 선택에 썼으므로 독립 검증이 아닙니다.','',
      '|관측·조건|실측|분 평균 전→후|기대 절대오차 전→후|','|---|---:|---:|---:|']
    for b,r in pairs:
        band=r['observed_low'] if r['observed_low']==r['observed_high'] else r['observed_low']+'~'+r['observed_high']
        text.append(f"|{r['reported_minute']} {r['stop']} {r['scenario']}|{band}|{float(b['uniform_minute_mean']):.2f}→{float(r['uniform_minute_mean']):.2f}|{float(b[err]):.2f}→{float(r[err]):.2f}|")
    flow=read(w/'gate-flow-before-after.json');service=read(w/'gate-service-diagnosis.json')
    text+=['','## 정문 유입·승차의 분리','',
      '16:30~17:04의 질량 원장입니다. 두 후보에서17개 버스 통과의 시각·차량·정원이 같습니다. 유입 총량이 회복됐다는 증거는 없으며, 도착 시간 분포가 달라져 관측 분의 줄이 변했습니다. 모델 여석 기회도 줄지 않았습니다. 한 시점의 줄만으로 실제 목적지 수요 전체를 역추정할 수 없습니다.','',
      '|후보|유입 가중치|승차 가중치|17:03 평균 줄|모형 여석 기회 합|','|---|---:|---:|---:|---:|']
    for x,y in zip(flow['cases'],service['cases']):
        text.append(f"|{x['model']}|{x['flow'].get('arrivals',0):.2f}|{x['flow'].get('exit_boarded',0):.2f}|{x['minute_mean_17_03']:.2f}|{y['offered_seat_events']:.2f}|")
    text+=['','여석 기회 합은 버스 통과별 모형 내 가용공간의 합이며 고유 좌석·승객 수나 실측 외부 인원이 아닙니다. [유입 보존 검산](gate-flow-before-after.json), [같은 운행·모형 재차 비교](gate-service-diagnosis.json).','',
      '## 월요일 원인 분리 진단','',
      '두 추가 조건은 주 모델과 같은 월요일 수요·운행·시드에서 설정 하나를 바꿨습니다. 주 결과의10조건에 추가해 평균을 유리하게 만들지 않습니다.','',
      '|조건|최대 연속대기|20분 초과 가중 구간|정문17:03 평균 / 기대 오차|','|---|---:|---:|---:|']
    for r in pilot['results']:
        if r['case']['day']!='월':continue
        fs=[x for x in rows(w/'pilot-field-comparison.csv') if x['model']==w.name and x['case']==r['case']['case'] and x['reported_minute']=='17:03'];assert len(fs)==1;f=fs[0];x=r['extended_diagnostics']
        text.append(f"|{r['case']['case']}|{x['all_recorded_time_max_continuous_wait_min']:.2f}|{x['all_recorded_time_over20_episode_weight']:.2f}|{float(f['uniform_minute_mean']):.2f} / {float(f[err]):.2f}|")
    text+=['','이 조건에서는 넓은 개인차를 유지하면 긴 대기 꼬리가 다시 나타났고, 기존 초기 선택으로 되돌리면 정문 평균이 다시 약4.3명으로 내려갑니다. 초기 선택 수정에는 기대 대기·개인 오차·거리 선호·정류장 중복 제거가 함께 들어가므로 각각의 효과를 이미 분리한 것은 아닙니다.','',
      '## 개인 한계·행동 검사','',
      '개인 인내 P 초과는20분 이하 기록도 포함해 별도로 셉니다. 과거 요약의full_passes 오독은full_passes_seen으로 고쳤으며 원본은 보존했습니다. 인내는 강제 이탈 시각이 아닙니다. 정문 최종 대안은 다른 유효 대안이 없어 P를 넘어 계속 기다릴 수 있습니다.','',
      '|조건|20분 초과 원장|P 초과 전체|그중20분 이하|정류장 복귀|오목적지|금지한 최종 방향|','|---|---:|---:|---:|---:|---:|---:|']
    bywait={x['case']['case']:x for x in waits['cases']}
    for r in behavior['cases']:
        c=r['case'];x=bywait[c['case']]['counts']
        text.append(f"|{c['day']} {c['scenario']}|{x.get('over20_episode_weight',0):.3f}|{x.get('past_personal_at_any_duration_weight',0):.3f}|{x.get('past_personal_at_most20_weight',0):.3f}|{r['returned_stop_weight']:.6f}|{r['wrong_destination_weight']:.6f}|{r['wrong_terminal_service_direction_weight']:.6f}|")
    text+=['','최초 충성 해제의 경계는 [별도5검사](loyalty-invariant-check.json)와 코드 검토로 확인했습니다. 과거 원장에는 최초 허용 해제 시각이 따로 없으므로 현재 수단이 셔틀인 모든 한계 전 변경을 위반으로 합산하지 않습니다. 이미 풀린 상태의 이탈도 [행동 원장](grid-behavior-validation.json)에 그대로 공개합니다. 새5516 검사는 모든 실제 승차의planned_terminal 의도 필드를 직접 사용합니다.','',
      '## 정문·법대40명 회상 기준','',
      '40명은 사용자의 회상 기준이며 새 실측 상한이 아닙니다.11:20~23:10에서 정문/법대의네방향(ARS21269·21299·21270·21298) 중 최대 줄이 생긴 곳을 조건별로 표시합니다. 전체99노드와 시간대는 원표에 남겼습니다.','',
      '|요일·배차|최대 줄 정류장·ARS|최대 가중 인원|그곳40명 초과 합계(분)|최장 지속(분)|','|---|---|---:|---:|---:|']
    for row in diag['cases']:
        c=row['case'];x=max(row['named_stop_40_recollection_comparison'],key=lambda x:x['maximum_queue'])
        text.append(f"|{c['day']} {c['scenario']}|{x['name']} {x['ars']}|{x['maximum_queue']:.2f}|{x['minutes_above40_recollection_reference']:.2f}|{x['longest_spell_above40_minutes']:.2f}|")
    text+=['',
      '## 남은 문제와 사용 범위','',
      '- 정문 관측33~39명에 대한 과소예측이 남습니다. 초기 수단 선호는 실제 개인 설문이 아닌 기존 계획의 첫 수단 대리값입니다. 교내 순환셔틀을 접근 수단으로 쓰는 사람과 통학셔틀 선호를 완전히 식별하지 못합니다.',
      '- 외부에서 이미 타고 온 실제 사람 수, 수업 외 연구실·직원·방문자 수요, 모든 대기자의 학생 여부는 이 자료만으로 분리할 수 없습니다. 남은 차이를 맞추려고 숨은 인원을 추가하거나 노선 정원을 바꾸지 않았습니다.',
      '- 행정관16:53/15:23 예측 평균은48.56/93.28명 상당으로 거의 그대로이며 화요일 관측67명과의 차이가 남습니다. 이번 수정으로 초기 셔틀 수요·운행을 바꾸지 않았기 때문입니다. 실제 배차·승차 처리 시각과 건물 출발 지연을 한 관측만으로 구분해 식별할 수 없어 요일별 배율이나 임의 시각 보정은 하지 않았습니다.',
      '- 평균 총시간·최장 여정이 늘어나는 조건과20분 초과가 남습니다. 초기 빈줄 위상만 수정한 혼합 예측이며 모든 시간표 위상 정보가 제거된 것은 아닙니다.0.1의 개인차와2분 판단 오차는 새 실측 추정값이 아닙니다.',
      '- 실제 도착 정보가 있는 승객과 없는 승객을 구분할 표본, 반복 측정한 목적지별 줄 합류·승차·경로변경 기록이 필요합니다. 새 날짜의 실측 정답은 열지 않았습니다. 결과는 시드0·고정 수요/공급의 조건부 모의 비교입니다.',
      '- 공개V11·경로 추천·active/latest는 유지했습니다. 새 후보의 사이트 연결·브라우저 성능·독립 실측 검증과 운영 교체 승인을 완료한 것으로 표시하지 않습니다.','',
      '[가정·자료·출처](SOURCES_AND_ASSUMPTIONS.md), [예측·개인 기준 초과 추적](grid-wait-cause-ledger.json), [실행 원장](grid-validation.json), [정적 검토](../collaboration/v12_queue_fit_review_261116010854/READ_ONLY_REVIEW.md).','']
    path=w/'RESULTS.md';write(path,'\n'.join(text))
    result={'release_id':w.name,'comparison_parent':BASE.name,'main_cases':10,'ablation_cases':2,'physical_gate_passed':all(x['status']=='PASS_INTERNAL_INVARIANTS' for x in v['results']),
        'behavior_gate':behavior['status'],'max_wait_before':old_max,'max_wait_after':new_max,'over20_weight_before':before_over,'over20_weight_after':after_over,'over20_reduction':1-after_over/before_over,
        'reused_field_error_sum_before':olderr,'reused_field_error_sum_after':newerr,'reused_field_error_reduction':1-newerr/olderr,'mean_journey_delta_range': [min(mean_delta),max(mean_delta)],
        'unserved_weight':unserved,'strict_all_waits_under20_passed':after_over<1e-7,'operating_adoption_recommended':False,'private_revision_fit_improved':newerr<olderr and after_over<before_over,
        'new_date_field_accuracy':'NOT_EVALUATED','report_sha256':sha(path),'production_writes':False}
    write(w/'recommendation.json',json.dumps(result,ensure_ascii=False,indent=2));print('RESULTS_READY',result,flush=True)
if __name__=='__main__':main()
