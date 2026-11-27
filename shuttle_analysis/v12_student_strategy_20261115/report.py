"""Review a behavioral hypothesis against the frozen parent without retuning."""
from pathlib import Path
import argparse,csv,hashlib,json,math
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'261112220847'
def read(p):return json.loads(p.read_bytes())
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');p.add_argument('--group',default='grid');a=p.parse_args();w=Path(a.candidate).resolve()
    out=w/(a.group+'-RESULTS.md');assert not out.exists();v=read(w/(a.group+'-validation.json'));d=read(w/(a.group+'-diagnostics.json'));behavior=read(w/(a.group+'-behavior-validation.json'))
    old={(r['case']['day'],r['case']['scenario']):r for r in read(PARENT/'grid-validation.json')['results']}
    maxwait=max(r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min'] for r in v['results']);over=sum(r['extended_diagnostics']['all_recorded_time_over20_episode_weight'] for r in v['results']);unserved=sum(r['unserved_trip_weight'] for r in v['results'])
    field=rows(w/(a.group+'-field-comparison.csv'));own=[r for r in field if r['model']==w.name];regressions=0
    for x in own:
        oldfield=next(z for z in field if z['model']==PARENT.name and z['scenario']==x['scenario'] and z['observation_id']==x['observation_id'])
        regressions+=float(x['expected_absolute_distance_to_count_or_interval'])>float(oldfield['expected_absolute_distance_to_count_or_interval'])+1e-7
    reused=sum('reused_run' in r for r in v['results'])
    run_scope=(f'{reused}조건은 동일 코드·입력·실효 설정의 완료 원장을 증거와 함께 재사용했습니다.' if reused else '실행 코드가 바뀌었으므로10조건 모두 새 후보에서 각각 한 번 실행했습니다. 이전 코드 결과는 재사용하지 않았습니다.')
    lines=[f'# 학생의 하교 전략을 반영한 후보 {w.name}','',
      f"{len(v['results'])}조건 물리 원장 감사. 행동 검사: {behavior['status']}. **20분 초과는 개인차를 허용한 진단이며, 강제 이탈로 없애지 않았습니다. 운영V11은 유지합니다.**",'',
      f'**운영 교체를 권고하지 않습니다.** 재사용 관측 비교{len(own)}건 중{regressions}건에서 기대 절대오차가 이전 후보보다 커졌습니다. 새 행동의 동작 검사와 실측 적합성은 구분합니다.','',
      '처음 셔틀/시내버스/도보를 선택한 성향을 출발점으로 두고, 셔틀 선호자는 예상 총대기가 개인 기다림 한계 안이면 선호를 유지하도록 바꿨습니다. 이미 기다린 시간에 앞으로 예측한 첫 승차 대기를 합쳐 판단하므로 실제로20분이 될 때까지 무조건 버티게 하지 않습니다. 시내버스 선호자는 접근 보행을 포함해 가장 빨리 실제 승차할 수 있는 정류장을 고릅니다. 호환 버스2대에 만차로 못 탔고2대 이상 추가 대기가 예상되거나 개인 한계를 넘으면 다른 노선·셔틀·가까운 목적지 도보를 재검토합니다. 이미 떠난 승차 정류장과 지금 떠날 정류장을 후속 환승으로 다시 찾는 후보도 제거합니다.','',
      '기숙사는 도보 귀가를 고려하고, 먼 서울대입구역은1km 초과 최종 도보를 막아 정문 밖 ARS21128의5511/5513/5515/5528/6515를 대안으로 둡니다. 이곳을 정식 마지막 대안으로 선택하면 다시 교내를 돌아다니지 않고 호환 버스를 기다립니다. 걷는 중 임시 승차는 기존 경로로 실제 정류장에 접근하고 준비/FIFO/정원을 거칩니다. 못 타면 짧은 기회 뒤 원래 도보를 이어갑니다. 초기 먼설입 도보 수요를city로 전환하는 예외를 포함해 전체 인원·출발·목적지 질량은 보존하며, 정류장 배치는 행동에 따라 달라집니다.','',
      '개인 기다림 중앙값20분·로그표준편차0.25, 도중 승차30초 창과80m 추가 보행 등은 측정되지 않은 시나리오값입니다. 기숙사에 근거 없는 별도12분 기준을 만들지 않고 같은 개인 인내를 기본으로 사용했습니다. 실제 학생 개인별 선호를 조사한 자료라는 뜻은 아닙니다. [구현 명세와 근거](../v12_student_strategy_20261115/SPEC.md).','',
      '만차 경험을 다음 버스 예상에 반영하는 기존 장치는 유지했습니다. 별도 민감도에서 이를 끈 변경은 채택하지 않았습니다. '+run_scope+' 선택 과정은 명세에 공개했습니다.','',
      '빠른 첫 승차를 고르기 전에 확인된 잘못된 방향을 제외합니다. 대학동 목적의 마지막5516승차는 동결 공식 정류장 metadata의 대학동고시촌입구 방향을 요구합니다. 노량진 방향으로 타서 돌아오는82분 차내 사례는 후보에서 제외했습니다. 후속 환승이 있는 중간승차나 다른 목적지를 일괄 배제하지 않습니다.','',
      '같은 모의 UID798720의 화요일 기본 여정은 방향 수정 전135.62분에서 수정 후22.31분으로 변했습니다. 이는 중간154738 대비 확인된 오류 한 건의 추적이며 전체 모델의 주 비교 기준이나 실제 학생의 개선효과가 아닙니다. [사례 전후 원장](direction-repair-diagnosis.json).','',
      '## 전체 여정과 연속 대기','',
      '총시간 분포는 완료한 모의 여정의 조건부 통계이며 미완료 질량은 별도로 표시합니다. 비교 기준은 수정 전 후보261112220847입니다. 중간 미채택 파일럿을 기준 모델로 바꿔 개선 폭을 부풀리지 않습니다.','',
      '|요일|배차 조건|평균 총시간 기준→수정(분)|p99 기준→수정|최장 기준→수정|전체 기록 최대 연속대기|20분 초과 가중치|미완료 가중치|','|---|---|---:|---:|---:|---:|---:|---:|']
    improved={k:0 for k in ('mean','p99','maximum')};deltas=[]
    for r in v['results']:
        c=r['case'];b=old[c['day'],c['scenario']]['extended_diagnostics']['finished_trip_quantiles']['total_min'];q=r['extended_diagnostics']['finished_trip_quantiles']['total_min'];z=r['extended_diagnostics']
        for k in improved:improved[k]+=q[k]<b[k]-1e-7
        deltas.append(q['mean']-b['mean'])
        lines.append(f"|{c['day']}|{c['scenario']}|{b['mean']:.2f}→{q['mean']:.2f}|{b['p99']:.2f}→{q['p99']:.2f}|{b['maximum']:.2f}→{q['maximum']:.2f}|{z['all_recorded_time_max_continuous_wait_min']:.3f}|{z['all_recorded_time_over20_episode_weight']:.3f}|{r['unserved_trip_weight']:.3f}|")
    lines+=['',f"전체 기록 최대 연속대기 {maxwait:.6f}분,20분 초과 구간 가중치 합 {over:.6f},미완료 가중치 합 {unserved:.6f}입니다. 초과 가중치는 고유 학생 수가 아닙니다. 평균 감소{improved['mean']}/{len(v['results'])},p99감소{improved['p99']}/{len(v['results'])},최장 감소{improved['maximum']}/{len(v['results'])}입니다. 전체 결과는 동일 시드0·수요/공급의 모의 시나리오이며 모든 난수나 현실 정확도 보장이 아닙니다.".replace('전체 기록','전체 기록').replace('.','.'),'',
      f"[전체 기록 모든 정류장{d['all_recorded_stop_rows']}행]({a.group}-all-recorded-stops.csv), [전체 기록 진입시각30분{d['all_recorded_half_hour_rows']}행]({a.group}-all-recorded-half-hour-waits.csv), [전체 여정 원표]({a.group}-journey-comparison.csv). 표시시간11:20~23:10과 겹친 대기의 기존 형식은 [정류장 표]({a.group}-all-stops.csv), [30분 표]({a.group}-half-hour-waits.csv)로 별도 보존했습니다.",'',
      '## 행동 원장','',
      '|조건|정류장 복귀 가중치|잘못된 목적지 가중치|설입 마지막 장거리 도보|예측 가능한 셔틀을 개인 한계 전에 포기|정식 정문대안 이탈|잘못된5516최종방향|정문 대안 가중치|기숙사 도보 전환 가중치|','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in behavior['cases']:
        s=r['student_strategy_counts'];c=r['case']
        lines.append(f"|{c['day']} {c['scenario']}|{r['returned_stop_weight']:.6f}|{r['wrong_destination_weight']:.6f}|{r['far_final_station_walk_weight']:.6f}|{r['shuttle_left_early_with_forecastable_service_weight']:.6f}|{r['ordinary_snu_final_gate_departure_weight']:.6f}|{r['wrong_terminal_service_direction_weight']:.6f}|{s.get('snu_gate_fallback_weight',0):.3f}|{s.get('dorm_terminal_walk_weight',0):.3f}|")
    lines+=['','## 정문·법대 대기열 회상 기준','',
      '40명은 사용자의 회상 기준이며 새 실측값이 아닙니다.11:20~23:10에서 초과를 강제로 잘라내지 않고 최대치와 지속시간을 공개합니다.','',
      '|요일·배차|ARS|정류장|최대 줄 가중치|40명 초과 합계(분)|최장 지속(분)|','|---|---|---|---:|---:|---:|']
    for case in d['cases']:
        c=case['case']
        for x in case['named_stop_40_recollection_comparison']:
            lines.append(f"|{c['day']} {c['scenario']}|{x['ars']}|{x['name']}|{x['maximum_queue']:.2f}|{x['minutes_above40_recollection_reference']:.2f}|{x['longest_spell_above40_minutes']:.2f}|")
    lines+=['','## 도보 중 실제 승차 기회','',
      '모두 가중 보행/시도/승차 건수이며 고유 학생 수가 아닙니다. 기존 경로의 정확한 prefix/suffix가 있는 곳만 지원하므로 보행 전체에서 기회를 찾았다고 해석하지 않습니다. 못 탄 수요는 사라지지 않고 원래 걷기를 이어갑니다.','',
      '|조건|보행 구간 가중 노출|접합 가능한 노출|플랫폼 접근 시도|실제 승차|도보 재개|','|---|---:|---:|---:|---:|---:|']
    for r in behavior['cases']:
        f=r['walking_opportunities']['flow'];c=r['case']
        lines.append(f"|{c['day']} {c['scenario']}|{f.get('walking_opportunity_weight',0):.3f}|{f.get('walking_weight_with_geometry',0):.3f}|{f.get('intercept_attempt_weight',0):.3f}|{f.get('opportunistic_boarded_weight',0):.3f}|{f.get('resumed_walking_weight',0):.3f}|")
    lines+=['','## 재사용한 과거 줄 관측','',
      '분 안의 관측 초를 균등하게 본 평균과 관측 범위까지의 기대 절대오차를 구분합니다. 월요일 날짜는 추정이고 문화관 방향은 미확정입니다. 과거 네 점은 이미 보정·후보 비교에 사용했으므로 독립 검증이 아닙니다. 이 네 점에 다시 맞추기 위한 수요/정원/운행표 조정은 하지 않았습니다.','',
      '|조건·관측|보고 인원|직전 평균 / 오차|수정 평균 / 오차|','|---|---:|---:|---:|']
    for r in own:
        b=next(x for x in field if x['model']==PARENT.name and x['scenario']==r['scenario'] and x['observation_id']==r['observation_id']);err='expected_absolute_distance_to_count_or_interval'
        band=r['observed_low'] if r['observed_low']==r['observed_high'] else r['observed_low']+'~'+r['observed_high']
        lines.append(f"|{r['weekday']} {r['scenario']} {r['reported_minute']} {r['stop']}|{band}|{float(b['uniform_minute_mean']):.2f} / {float(b[err]):.2f}|{float(r['uniform_minute_mean']):.2f} / {float(r[err]):.2f}|")
    gate=read(w/'gate-flow-diagnosis-v2.json')
    lines+=['','## 정문 밖 과소예측의 원장 진단','',
      '월요일16:30~17:04의 정문 밖21128 유입·탑승을 비교했습니다. 동일 운행 입력에서 새 후보의 도착 수요 자체가 줄었습니다. 탑승 처리량도 줄었으므로 짧은 줄을 교통 개선으로 해석하지 않습니다. 초기 정류장 선택과 경로 변경 규칙의 개별 효과를 분리한 실험은 아니며, 실제 수요를 관측한 결과도 아닙니다.','',
      '|후보|17:03 분 평균 줄|도착 가중치|탑승 가중치|변경 후 도착 가중치|','|---|---:|---:|---:|---:|']
    for x in gate['cases']:
        f=x['flow'];lines.append(f"|{x['model']}|{x['minute_mean_17_03']:.2f}|{f.get('arrivals',0):.2f}|{f.get('exit_boarded',0):.2f}|{x['arrivals_after_changes']:.2f}|")
    lines+=['','초기 셔틀/시내버스 선호 비중은 첫 수단의 대리값이고, 새 도착 관측으로 검증하지 못했습니다. 첫 승차를 빠르게 하는 정류장 선택과 기다림에 따른 경로 전환이 정문 유입을 과하게 줄이는지 추가 검토가 필요합니다. 기존 네 점에 임의 계수를 다시 맞춰 정확도가 좋아졌다고 표현하지 않았습니다. [흐름 검산](gate-flow-diagnosis-v2.json).','',
      '## 제약과 검산','','- 수요 질량·정원·FIFO·차량 시계·도보 구간 물리시간·누적대기는 원장으로 검사했습니다.20분에 강제 이탈시키거나 수요를 삭제하지 않습니다. 미완료는 별도 표시합니다.',
      '- 도보 도중 승차는 기존 prefix/suffix가 있는 유효 경로만 지원합니다. 임의 위치에서 버스를 세우거나 모든 도보를 완전히 관측한 것은 아닙니다. 유효 경로·제안·실제 승차·만차 후 재개 원장을 별도로 보존합니다.',
      '- [승차 방향 감사 범위](DIRECTION_AUDIT_SCOPE.md): 중간 환승으로 탄 뒤 나중에 도보로 변경한 버스는 실제 마지막으로 탄 버스라도 금지한 직행과 다릅니다. 후속 변경이 없는 최종승차 및 대학동까지 반대방향으로 돌아오는 승차를 검사하고, 허용한 중간승차 노출은 별도 열로 남겼습니다. 계획 의도는 별도 로그 필드로 없으며 정적 검토를 함께 사용했습니다.',
      '- [별도 에이전트의 정적 검토](../collaboration/v12_direction_review_261115160710/READ_ONLY_REVIEW.md), [증거 해시와 범위](independent-static-review.json). 이 검토자는 모형·시험을 실행하지 않았으며 실측 정확도나 배포 준비를 승인한 것이 아닙니다.',
      '- 기존 수업/수강생 가중 수요·기숙사/목적지 비중·도서관 경유 가정과 시내버스11/10 운행 입력을 계승했습니다. 실제 개인 이동 경로/대기나 숫자 재차인원 자료는 확보한 것으로 만들지 않았습니다. [직전 자료·사용 장부](../261112220847/OBSERVATION_USAGE.md).',
      '- 기존 셔틀44명·두 대 편성 시나리오, 시내버스 정원, 노선별 주어진 운행 계획과 구간시간은 바꾸지 않았습니다. BUSIN 위치와 순서형 혼잡을 숫자 재차인원으로 바꾸지 않습니다.',
      '- 시내버스의 실제 교외 선점 인원은 아직 식별하지 못했습니다. 현재 물리 가용좌석은 모형 내 수요와 기존 정원 시나리오 기준이며, 실제 버스의 남은 자리나 실시간 개인 대기를 관측했다는 뜻이 아닙니다.',
      '- 개인 인내를 넘으면 대안을 검토합니다. 검토 시각과 선택이 확률적이고 유효한 대안이 없을 수도 있어 정확히 그 순간 무조건 떠나지 않습니다. ['+a.group+' 개인 인내 초과 원표]('+a.group+'-wait-threshold-diagnosis.json)와20분 초과 집계를 따로 남깁니다. 기존 엄격한 모든 대기20분 이하 기준은 통과한 것으로 표시하지 않습니다.',
      f"- [물리 원장]({a.group}-validation.json), [행동 원장]({a.group}-behavior-validation.json), [동결 입력](future_evaluation_plan.json). 신규 날짜의 실측 정답은 열지 않았습니다. 동작 검증과 현실 적합성을 구분합니다.",'']
    out.write_text('\n'.join(lines),encoding='utf8')
    rec={'release_id':w.name,'group':a.group,'cases':len(v['results']),'physical_gate_passed':all(r['status']=='PASS_INTERNAL_INVARIANTS' for r in v['results']),
      'behavior_gate':behavior['status'],'max_all_recorded_wait_min':maxwait,'over20_episode_weight':over,'unserved_weight':unserved,
      'mean_improved':improved['mean'],'p99_improved':improved['p99'],'maximum_improved':improved['maximum'],'mean_total_delta_range':[min(deltas),max(deltas)],
      'old_strict_twenty_minute_gate_passed':over<1e-7,'twenty_minutes_is_new_personal_patience_diagnostic':True,
      'reused_field_comparisons':len(own),'reused_field_error_regressions':regressions,
      'operating_adoption_recommended':False,'adoption_status':'BEHAVIOR_IMPLEMENTED_NOT_ACCEPTED_FOR_OPERATION',
      'blockers':['reused_gate_queue_fit_regression','strict_all_waits_under20_failed','new_field_accuracy_not_evaluated','candidate_site_and_route_wiring_and_browser_checks_not_completed'],
      'recollection40_reference_exceed_cases':sum(any(x['minutes_above40_recollection_reference']>0 for x in c['named_stop_40_recollection_comparison']) for c in d['cases']),
      'report_sha256':sha(out),'new_date_accuracy':'NOT_EVALUATED','production_writes':False}
    p=w/(a.group+'-recommendation.json');assert not p.exists();p.write_text(json.dumps(rec,ensure_ascii=False,indent=2),encoding='utf8');print('REPORT_WRITTEN',a.group,len(v['results']),flush=True)
if __name__=='__main__':main()
