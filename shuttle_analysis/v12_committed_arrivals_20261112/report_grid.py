"""Report conditional forecast improvement, preserved walking preference and tradeoffs."""
from pathlib import Path
import argparse,csv,hashlib,json,math
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'261112171315'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def num(x):return f'{float(x):.2f}'
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve();out=w/'RESULTS_FINAL.md';assert not out.exists()
    v=read(w/'grid-validation.json');d=read(w/'grid-diagnostics.json');pilot=read(w/'pilot-assessment.json');trace=read(w/'grid-trace-and-costs.json')
    before=read(PARENT/'grid-validation.json')['results'];old={(r['case']['day'],r['case']['scenario']):r for r in before}
    fields=rows(w/'grid-field-comparison.csv');classes=rows(w/'class-end-journey-comparison.csv')
    maxwait=max(r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min'] for r in v['results'])
    totalmax=max(r['extended_diagnostics']['finished_trip_quantiles']['total_min']['maximum'] for r in v['results'])
    over=math.fsum(r['extended_diagnostics']['all_recorded_time_over20_episode_weight'] for r in v['results'])
    passed=d['all_invariant_audits_pass'] and over<1e-7 and d['unserved_trip_weight']<1e-7
    own=[r for r in fields if r['model']==w.name and r['scenario']=='regular'];assert len(own)==4
    lines=[f'# 도보 선호를 유지한 탑승 가능성 예측 보완 — {w.name}','',
      f"**{'물리·20분10조건 통과' if passed else '물리·20분 조건 미충족'} · 파일럿p99검토예산 초과 · 운영V11 유지 · 새 날짜 정확도 미검증**",'',
      '후반에 도보를 더 선호하는 성향은 기존 의도라는 사용자 확인을 반영했습니다. 직전171315의 보행·대기·혼잡·피로·변경 계수, 거리 확률, 제한 없는 변경 규칙은 유지했습니다. 수업 종료 후 출발 배율1.125도 그대로이며 이번에 계수를 다시 적합하지 않았습니다. [파일럿의 함수·설정 보존 검사](pilot-assessment.json).','',
      '## 바꾼 범위와 이유','',
      '기존 예측은 현재 큐를 사용했습니다. 도보 후 정류장에 도착하기 전에 다른 수요가 먼저 준비를 마치면, 예측했던 버스가 와도 정원 때문에 못 탈 수 있습니다. 새 후보는 판단 시점에 이미 출발해 걷거나 준비 중인 모의 수요를 추가하고, 본인보다 준비를 먼저 마칠 사람만 FIFO 앞에 놓습니다. 현재 줄 순번이 이미 발급됐으면 뒤의 유입은 추월하지 못합니다. 선행 수요도 준비 전 버스에는 탈 수 없고, 앞선 다른 버스가 처리한 질량은 다시 세지 않습니다. 물리 정원이나 실제 탑승 질량을 바꾸는 기능이 아닙니다.','',
      '초기 모든 계획이 미리 등록되는 엔진에서도 실제 판단시각까지 출발한 기록만 활성화합니다. 미래 수업의 미출발 계획·사후 실제 큐·나중의 경로 변경은 읽지 않습니다. **이미 이동 중인 모의 승객의 현재 목표와 도착 예정을 예측기가 안다는 정보 가정**입니다. 실제 학생 위치·목적지 관측을 확보했다는 뜻은 아닙니다. 아직 승차 중인 사람의 향후 환승과 미출발 집단의 확률적 유입은 이번 작은 수정의 범위 밖입니다.','',
      '자발적 거절 로그에는 승차·대기·선택 대안의 전체 예측 성분과 개인 계수·누적대기·현재 줄 진입·만차 경험을 추가했습니다. 큰 선호 비용이 어디서 나왔는지 실제 ETA와 분리해 검산할 수 있습니다. [수정 명세](../v12_committed_arrivals_20261112/SPEC.md), [직전 긴 여정의 독립 진단](../collaboration/v12_tail_review_261112171315/READ_ONLY_REVIEW.md).','',
      '파일럿에서 화요일 총시간p99가1.088분 늘어, 사전에 둔 증가1분의 검토 예산을 약5.3초 초과했습니다. 최초 예산 통과로 표시하지 않았습니다. 평균 총시간 감소·줄 관측 손실 감소와20분/보존 조건 통과를 근거로, 추가 승격 없이 평일 전체 진단을 진행한 판단은 [파일럿 추가 검토 결정](pilot_review_decision.json)에 따로 기록했습니다. 원래 등록·실패 판정·계수는 유지했습니다.','',
      '## 과거 관측과의 비교','',
      '단위는 가중 모의 인원분입니다. 각 분 안에서 측정 초를 균등하게 본 평균과, 관측값/범위까지의 기대 절대오차를 따로 표시했습니다. 월요일 날짜는 대화에서 추정됐고 문화관 방향은 미확정입니다. 이 네 관측은 앞서도 사용한 보정·선택 자료이며 독립 검증이 아닙니다.','',
      '|관측|실제 보고|직전 평균 / 오차|수정 평균 / 오차|','|---|---:|---:|---:|']
    improved=0
    for r in own:
        b=next(b for b in fields if b['model']==PARENT.name and b['scenario']=='regular' and b['observation_id']==r['observation_id'])
        err='expected_absolute_distance_to_count_or_interval';improved+=float(r[err])<float(b[err])-1e-7
        band=r['observed_low'] if r['observed_low']==r['observed_high'] else r['observed_low']+'~'+r['observed_high']
        lines.append(f"|{r['weekday']} {r['reported_minute']} {r['stop']}|{band}|{num(b['uniform_minute_mean'])} / {num(b[err])}|{num(r['uniform_minute_mean'])} / {num(r[err])}|")
    lines+=['',f"방향확인3점 정규화 손실은 {pilot['primary_loss_before']:.6f}→{pilot['primary_loss_after']:.6f}입니다. 네 보고 중 오차 감소는 {improved}/4건입니다. [regular/peak와 모든 과거 대조를 포함한 원표](grid-field-comparison.csv).",'',
      '## 평일 전체와 전체 여정','',
      '월~금×regular/peak, 시드0입니다. 수요·공급·기존 선호는 같고, 새 예측에 따른 내생적 선택은 달라질 수 있습니다. 아래 총시간은 출발→목적지입니다.','',
      '|요일|조건|평균 총시간 직전→수정|p99 직전→수정|최장 총시간 직전→수정|모든 기록의 최대 연속대기|','|---|---|---:|---:|---:|---:|']
    mean_improved=p99_improved=max_improved=0;regress=[];walk=[];p99_deltas=[]
    for r in v['results']:
        c=r['case'];b=old[c['day'],c['scenario']]['extended_diagnostics']['finished_trip_quantiles'];q=r['extended_diagnostics']['finished_trip_quantiles']
        x,y=b['total_min'],q['total_min'];mean_improved+=y['mean']<x['mean'];p99_improved+=y['p99']<x['p99'];max_improved+=y['maximum']<x['maximum']
        p99_deltas.append(y['p99']-x['p99'])
        if y['mean']>x['mean']:regress.append({'day':c['day'],'scenario':c['scenario'],'delta_min':y['mean']-x['mean']})
        walk.append(q['walk_min']['mean']-b['walk_min']['mean'])
        lines.append(f"|{c['day']}|{c['scenario']}|{num(x['mean'])}→{num(y['mean'])}|{num(x['p99'])}→{num(y['p99'])}|{num(x['maximum'])}→{num(y['maximum'])}|{num(r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min'])}|")
    lines+=['',f'모든 기록의 최대 연속대기는 {maxwait:.6f}분입니다.',
      f"20분 초과 구간 가중치 합{over:.6f}, 미완료 가중치 합{d['unserved_trip_weight']:.6f}입니다. 평균 감소{mean_improved}/10조건·p99감소{p99_improved}/10조건·최장 감소{max_improved}/10조건이며 평균 도보 변화는{min(walk):+.3f}~{max(walk):+.3f}분입니다. 모든 난수·현장의20분 이하를 보장하는 결과는 아닙니다.",'',
      f"p99 변화는 {min(p99_deltas):+.3f}~{max(p99_deltas):+.3f}분입니다. 전체10조건의 최장 여정도 {max(r['extended_diagnostics']['finished_trip_quantiles']['total_min']['maximum'] for r in before):.3f}→{totalmax:.3f}분으로 바뀌었습니다. 추적한 한 조각의 단축을 전체 극단 여정 해결로 해석하지 않습니다.",'',
      '수업 종료→목적지 시간도 별도로 산출했습니다. 출발 시차가 같아서 평균 변화는 출발→목적지의 평균 변화와 일치해야 하며, 원표 정합성 검사에서 이를 확인합니다. [수업 종료 기준40행](class-end-journey-comparison.csv).','',
      f"[모든 정류장{d['stop_rows']}행](grid-all-stops.csv), [진입 시각별30분{d['half_hour_rows']}행](grid-half-hour-waits.csv), [보행·누적대기·총시간·변경횟수40행](grid-journey-comparison.csv). 같은 물리 줄의 연속 대기는 합치고,20분에 강제 이탈시키거나 수요를 삭제하지 않았습니다.",'',
      '## 정문·법대40명 참고 조건','',
      '40명은 사용자 기억에 근거한 불확실한 참고값입니다. 실제 상한으로 강제하지 않았습니다. 아래는 각 정류장10조건의 최대와 초과 지속시간입니다.','',
      '|정류장 ARS|최대 줄 인원분|40명 초과 조건|최장 연속 초과(분)|','|---|---:|---:|---:|']
    named={}
    for r in d['cases']:
        for s in r['named_stop_40_recollection_comparison']:named.setdefault(str(s['ars']),[]).append(s)
    named_exceed=0
    for ars,items in sorted(named.items()):
        n=sum(s['maximum_queue']>40 for s in items);named_exceed+=n
        lines.append(f"|{items[0]['name']} {ars}|{num(max(s['maximum_queue'] for s in items))}|{n}/10|{num(max(s['longest_spell_above40_minutes'] for s in items))}|")
    lines+=['','## 이전101분 조각의 추적','',
      '같은 합성 ID가 분할될 수 있어 완료 조각 수와 질량을 함께 확인했습니다. 한 실제 학생의 관측이나 하나의 원인에 대한 현장 인과 추정으로 읽지 않습니다.','',
      '|모델|완료 조각 수|총 가중치|가중 평균 총시간|평균 도보|평균 변경횟수|최장 조각|','|---|---:|---:|---:|---:|---:|---:|']
    for t in trace['traces']:
        tw=math.fsum(x['weight']*x['leg_times']['walk'] for x in t['fragments'])/t['mass']
        tc=math.fsum(x['weight']*x['route_changes'] for x in t['fragments'])/t['mass']
        lines.append(f"|{t['model']}|{t['fragment_count']}|{t['mass']:.6f}|{t['weighted_mean_total_min']:.3f}|{tw:.3f}|{tc:.3f}|{t['maximum_total_min']:.3f}|")
    lines+=['',f"화요일regular 새 거절 로그의 비용 벡터{trace['cost_vectors_checked']}개를 별도 산술로 재구성했고 최대 차이는{trace['maximum_cost_error_minutes']:.3g}분 등가였습니다. 이는 비용 산술의 일치이며 선호 계수의 현장 타당성 증명은 아닙니다. [추적·비용 검산](grid-trace-and-costs.json).",'',
      '## 검증과 남은 한계','',
      '- 76개 시험을 통과했고 최종 로그 성분 추가 뒤 관련13개 시험을 다시 확인했습니다.150개 무작위 oracle대조는 단일 정류장·board0·빈 차내 조건입니다. 전체 물리 정원·FIFO·차량 시계·승하차 질량·보행/대기/승차 합계·누적대기는10조건 원장 감사로 별도 확인합니다. [시험](boundary-tests.log), [최종 관련 회귀](preflight-final.log), [실행 감사](grid-validation.json).',
      '- 추가3개 시험에서는 비어 있지 않은 차내·정류장순번1에서의 하차·과거 예약 분리, 이미 지난 차량의 수요 처리 제외, 여러 차량의 부분 여석을 한 사람의 자리로 합치지 않는 조건을 확인했습니다. 활성 모델 파일을 고치지 않고 같은 동결 함수에 적용했습니다. [추가 시험](additional-timed-tests.log).',
      '- [구현 에이전트의 최종 정적 검토](../collaboration/v12_committed_review_261112210916/READ_ONLY_REVIEW_FINAL.md)는 인과정보·FIFO·등록 중복·정원 산술 범위에서 차단 사유를 찾지 못했습니다. 해당 검토가 시험 실행이나 현장 정확도 승인이라는 뜻은 아닙니다. 실행 전 마무리 변경을 가로질렀던 최초 해시 검토의 실패도 보존하고 최종 동결판과 구분했습니다.',
      '- 현재 의도대로 준비를 마쳐 줄에 들어올 것이라는 조건부 예측입니다. 이후 실제 경로 재선택·정확한 동시 ready 순서·미출발 집단·차내 승객의 향후 환승을 완전히 예측하지 않습니다. 미래에 첫 승차 가능 차량을 탄다는 근사와 실제 재선택 정책의 차이도 남습니다.',
      '- 정원·시계·원본 수요를 늘리거나 선호 계수를 바꾸지 않았습니다. 과거 수업 수강인원 가중치·목적지/기숙사 시나리오·실측 혼잡등급의 역할과 미확보 자료는 [직전 자료 설명](../261112171315/RESULTS_FINAL.md)을 계승합니다. 순서형 혼잡을 실제 승객 수로 환산하지 않습니다.',
      '- 새 날짜 정답은 열지 않았습니다. [향후평가22해시](future_evaluation_plan.json), [소스 보존·운영 읽기 확인](final_verification.json), [원표·문서 검사](artifact_verification_final.json). 운영V11은 유지하며 사용자 승인 전 승격하지 않습니다.','']
    out.write_text('\n'.join(lines),encoding='utf8')
    result={'release_id':w.name,'recommendation':'KEEP_PRIVATE_DO_NOT_PROMOTE','parent':PARENT.name,'internal_ten_case_gate_passed':passed,
      'walking_preference_preserved':True,'alpha_unchanged':1.125,'numeric_parameter_fitting_this_round':False,'pilot_original_review_budgets_passed':False,
      'primary_loss_before':pilot['primary_loss_before'],'primary_loss_after':pilot['primary_loss_after'],'old_field_errors_improved':improved,
      'maximum_all_recorded_continuous_wait_min':maxwait,'over20_episode_weight':over,'unserved_trip_weight':d['unserved_trip_weight'],
      'maximum_total_journey_min':totalmax,'mean_total_improved':mean_improved,'p99_total_improved':p99_improved,'max_total_improved':max_improved,
      'p99_delta_range':[min(p99_deltas),max(p99_deltas)],'parent_maximum_total_journey_min':max(r['extended_diagnostics']['finished_trip_quantiles']['total_min']['maximum'] for r in before),
      'mean_total_regressions':regress,'mean_walk_delta_range':[min(walk),max(walk)],'target_trace':trace['traces'],
      'named_40_reference_exceed_conditions':named_exceed,
      'independent_field_accuracy':'NOT_EVALUABLE','new_day_outcomes_opened':False,'production_writes':False,'report_sha256':sha(out)}
    target=w/'release_recommendation_final.json';assert not target.exists();target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    (w/'README.md').write_text(f'# 탑승 예측 보완 후보 {w.name}\n\n[최종 결과](RESULTS_FINAL.md)를 보세요. 후반 도보 선호는 유지했고 조건부 미래 유입 정보만 보완했습니다. 운영V11은 유지합니다.\n',encoding='utf8')
    print('REPORT_WRITTEN',w.name,'all_recorded_maxwait',maxwait,'field_improved',improved,flush=True)
if __name__=='__main__':main()
