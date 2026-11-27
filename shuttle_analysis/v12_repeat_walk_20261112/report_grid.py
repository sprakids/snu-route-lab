"""Report the new conditional walking rule without claiming empirical calibration."""
from pathlib import Path
import argparse,csv,hashlib,json,math
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'261112210916'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def num(x):return f'{float(x):.2f}'
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve();out=w/'RESULTS_FINAL.md';assert not out.exists()
    v=read(w/'grid-validation.json');d=read(w/'grid-diagnostics.json');pilot=read(w/'pilot-assessment.json');trace=read(w/'grid-trace-and-costs.json');prob=read(w/'grid-probability-validation.json')
    before=read(PARENT/'grid-validation.json')['results'];old={(r['case']['day'],r['case']['scenario']):r for r in before}
    maxwait=max(r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min'] for r in v['results'])
    totalmax=max(r['extended_diagnostics']['finished_trip_quantiles']['total_min']['maximum'] for r in v['results'])
    over=math.fsum(r['extended_diagnostics']['all_recorded_time_over20_episode_weight'] for r in v['results'])
    passed=d['all_invariant_audits_pass'] and over<1e-7 and d['unserved_trip_weight']<1e-7
    fields=rows(w/'grid-field-comparison.csv');own=[r for r in fields if r['model']==w.name and r['scenario']=='regular'];assert len(own)==4
    lines=[f'# 경로 변경 횟수에 따른 목적지 도보확률 — {w.name}','',
      f"**{'물리·20분10조건 통과' if passed else '물리·20분 조건 미충족'} · 사용자 지정 행동 시나리오 · 운영V11 유지 · 새 날짜 정확도 미검증**",'',
      '목적지까지 계속 걷는 선택의 조건부 확률을 완료한 경로 변경 횟수에 따라 높였습니다. 같은 현재 거리·대기경험·개인성향·후보집합을 놓고 `p(n)=1-(1-p_ref)^(2^n)`를 사용합니다. 작은 확률에서는 대략 두 배씩 증가하고 이후100%에 포화합니다. 증가율2는 사용자 요청을 구체화한 기본 시나리오값이며 실측 추정값이 아닙니다.','',
      '|완료 변경 횟수 n|0|1|2|3|4|','|---|---:|---:|---:|---:|---:|','|기준10%일 때 도보확률|10.00%|19.00%|34.39%|56.95%|81.47%|','',
      '실제 선택기의 도보 그룹 합계 확률이 위 목표가 되도록 로그가중치를 이동합니다. 도보 대안에 단순히2^n을 곱하는 방식과 구분됩니다. 기존 변경 횟수 증가 비용이 새 효과를 역전하지 않도록 기준확률 산출에서만 그 증가분을 제거합니다. 원시 비용 함수·거리·경로별 물리시간 계산은 바꾸지 않았으며, 선택한 경로가 달라져 실제 모의 여정 시간은 달라질 수 있습니다. 로짓 확률과 iid Gumbel 관계의 근거는 [Train(2009),3.1절·식3.6](https://eml.berkeley.edu/books/choice2nd/Ch03_p34-75.pdf)이며, 이 자료가 서울대 학생의 증가율2를 입증하는 것은 아닙니다. [수식과 적용 범위](../v12_repeat_walk_20261112/SPEC.md), [확률표45행](probability-law.csv).','',
      '## 유지한 조건과 적용 위치','',
      '- 대기 중 경로 재검토와 버스 도착 시 승차/대기/다른 경로 선택에 모두 적용합니다. 초기0회 선택은 기존과 같습니다.',
      '- 목적지 도보에만 효과를 붙입니다. 다른 정류장으로 걸어가 버스를 타는 경로는 직접 증폭하지 않습니다. 정규화 때문에 비도보 대안의 절대확률은 함께 줄지만, 그 대안들끼리의 상대 확률은 유지됩니다.',
      '- 0~500m 평탄,1km 이후 급감하는 거리 선호와 보행·대기·혼잡·피로 기본 계수, 공급·정원·수요·수업 후 출발 배율1.125, 인과적 접근 수요 예측은 유지했습니다.1회 이상에서 목적지 도보가 근사 비용 가지치기에 미리 없어지는 경우만 방지했습니다.',
      '- 경로 변경 횟수 제한은 없습니다.20분 강제 이탈이나N회 후 강제 도보도 없습니다. 큰 횟수의 수치 넘침을 막는 거의100%의 계산상 포화만 사용합니다.',
      '- **실제 의사결정 기회에서의 조건부 확률**입니다. 재검토 시점의 기존0.3^n 감쇠는 그대로입니다. 따라서 분당 도보 전환율이나 서로 다른 집단의n별 실제 도보 비율까지 단조증가한다고 해석하지 않습니다.','',
      '## 모의 운행에서의 선택 분포','',
      '아래는10조건의 재검토/승차 의사결정을 합친 가중 평균입니다. 같은 합성 승객이 여러 번 포함될 수 있어 고유 인원 비율이 아닙니다. 횟수별 거리·대기·남은 승객 구성이 달라 고정 조건 확률표와 값이 다릅니다. 도보가 불가능한 결정도 분모에 포함합니다.','',
      '|완료 변경 횟수|결정 가중치|도보 가능한 결정 비율|효과 전 확률 평균|적용 확률 평균|실제 선택 도보 비율|','|---|---:|---:|---:|---:|---:|']
    groups={}
    for r in rows(w/'grid-walking-by-change-count.csv'):
        n=int(r['completed_changes']);mass=float(r['decision_weight']);g=groups.setdefault(n,dict(mass=0.,available=0.,raw=0.,target=0.,selected=0.))
        g['mass']+=mass;g['available']+=float(r['walk_available_weight'])
        for dest,key in [('raw','mean_unboosted_probability'),('target','mean_target_probability'),('selected','realized_terminal_walk_fraction')]:g[dest]+=mass*float(r[key])
    for n,g in sorted(groups.items()):
        m=g['mass'];lines.append(f"|{n}|{m:.3f}|{g['available']/m:.2%}|{g['raw']/m:.2%}|{g['target']/m:.2%}|{g['selected']/m:.2%}|")
    lines+=['',f"[요일·조건·결정지점별 원표](grid-walking-by-change-count.csv). 기록된 확률식 {prob['recorded_probability_checks']}건을 대조한 최대 수치 오차는{prob['maximum_probability_formula_error']:.3g}입니다. 이 건수는 로그 대조 횟수이며 독립 표본수가 아닙니다.",'',
      '## 평일 전체 시간과 대기','',
      '월~금×regular/peak, 시드0, 직전210916과 동일 가중 수요·공급입니다. 실제 수강생 개개인의 목적지나 실제 대기시간 측정값이 아닌 모의 시나리오입니다. 단위는 분이며 총시간은 출발→목적지입니다.','',
      '|요일|조건|평균 총시간 직전→수정|p99 직전→수정|최장 총시간 직전→수정|최대 연속대기|','|---|---|---:|---:|---:|---:|']
    improvements={k:0 for k in ('mean','p99','maximum')};regress=[];walk=[];p99=[];changes=[]
    for r in v['results']:
        c=r['case'];b=old[c['day'],c['scenario']]['extended_diagnostics']['finished_trip_quantiles'];q=r['extended_diagnostics']['finished_trip_quantiles'];x,y=b['total_min'],q['total_min']
        for stat in improvements:improvements[stat]+=y[stat]<x[stat]-1e-7
        if y['mean']>x['mean']+1e-7:regress.append({'day':c['day'],'scenario':c['scenario'],'delta_min':y['mean']-x['mean']})
        walk.append(q['walk_min']['mean']-b['walk_min']['mean']);changes.append(q['changes']['mean']-b['changes']['mean']);p99.append(y['p99']-x['p99'])
        lines.append(f"|{c['day']}|{c['scenario']}|{num(x['mean'])}→{num(y['mean'])}|{num(x['p99'])}→{num(y['p99'])}|{num(x['maximum'])}→{num(y['maximum'])}|{num(r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min'])}|")
    parentmax=max(r['extended_diagnostics']['finished_trip_quantiles']['total_min']['maximum'] for r in before)
    lines+=['',f"최대 연속대기는 전체 기록 기준{maxwait:.6f}분,20분 초과 구간 가중치 합{over:.6f},미완료 가중치 합{d['unserved_trip_weight']:.6f}입니다. 평균 감소{improvements['mean']}/10조건,p99감소{improvements['p99']}/10조건,최장 감소{improvements['maximum']}/10조건입니다.",'',
      f"p99 변화는{min(p99):+.3f}~{max(p99):+.3f}분, 평균 도보 변화는{min(walk):+.3f}~{max(walk):+.3f}분, 평균 변경 횟수 변화는{min(changes):+.3f}~{max(changes):+.3f}회입니다.10조건의 최장 총시간은{parentmax:.3f}→{totalmax:.3f}분입니다. 시간 감소를 보장하는 규칙으로 해석하지 않습니다.",'',
      f"[전체 정류장{d['stop_rows']}행](grid-all-stops.csv), [줄 진입 시각별30분{d['half_hour_rows']}행](grid-half-hour-waits.csv), [보행·대기·총시간·변경횟수40행](grid-journey-comparison.csv), [수업 종료 기준40행](class-end-journey-comparison.csv). 수업 종료→출발 평균은 같고 수업 종료→목적지 평균 차이는 출발→목적지 평균 차이와 일치하는지 검산했습니다.",'',
      '## 반복 사용한 과거 관측과 비교','',
      '각 분 안의 측정 초를 균등하게 본 줄 평균과 관측값/범위까지의 기대 절대오차를 분리했습니다. 월요일 날짜는 대화로 추정했고 문화관 방향은 미확정입니다. 이미 보정과 후보 선택에 사용한 네 보고이므로 독립 정확도 검증이 아닙니다.','',
      '|관측|보고 인원|직전 평균 / 오차|수정 평균 / 오차|','|---|---:|---:|---:|']
    field_improved=field_worse=0
    for r in own:
        b=next(x for x in fields if x['model']==PARENT.name and x['scenario']=='regular' and x['observation_id']==r['observation_id']);err='expected_absolute_distance_to_count_or_interval'
        field_improved+=float(r[err])<float(b[err])-1e-7;field_worse+=float(r[err])>float(b[err])+1e-7
        band=r['observed_low'] if r['observed_low']==r['observed_high'] else r['observed_low']+'~'+r['observed_high']
        lines.append(f"|{r['weekday']} {r['reported_minute']} {r['stop']}|{band}|{num(b['uniform_minute_mean'])} / {num(b[err])}|{num(r['uniform_minute_mean'])} / {num(r[err])}|")
    lines+=['',f"방향확인3점 정규화 손실은{pilot['primary_reused_report_loss_before']:.6f}→{pilot['primary_reused_report_loss_after']:.6f}입니다. 네 보고 중 오차 감소{field_improved}건,증가{field_worse}건입니다. 증가율2는 이 결과를 보기 전에 고정했고 재적합하지 않았습니다. [모든 과거 대조 원표](grid-field-comparison.csv).",'',
      '## 정문·법대40명 참고값과 긴 여정','',
      '40명은 사용자 기억에 근거한 불확실한 참고값이며 강제 상한이 아닙니다.','',
      '|정류장 ARS|최대 줄 인원분|40명 초과 조건|최장 연속 초과(분)|','|---|---:|---:|---:|---:|']
    named={}
    for r in d['cases']:
        for s in r['named_stop_40_recollection_comparison']:named.setdefault(str(s['ars']),[]).append(s)
    named_exceed=0
    for ars,items in sorted(named.items()):
        n=sum(s['maximum_queue']>40 for s in items);named_exceed+=n
        lines.append(f"|{items[0]['name']} {ars}|{num(max(s['maximum_queue'] for s in items))}|{n}/10|{num(max(s['longest_spell_above40_minutes'] for s in items))}|")
    lines+=['','기존 긴 여정의 동일 합성ID1205536은 분할된 모든 완료 조각을 합쳐 비교합니다. 한 실제 학생의 관측이나 현장 인과 효과로 해석하지 않습니다.','',
      '|모델|완료 조각 수|총 가중치|가중 평균 총시간|평균 도보|평균 변경횟수|최장 조각|','|---|---:|---:|---:|---:|---:|---:|']
    for t in trace['traces']:
        tw=math.fsum(x['weight']*x['leg_times']['walk'] for x in t['fragments'])/t['mass'];tc=math.fsum(x['weight']*x['route_changes'] for x in t['fragments'])/t['mass']
        lines.append(f"|{t['model']}|{t['fragment_count']}|{t['mass']:.6f}|{t['weighted_mean_total_min']:.3f}|{tw:.3f}|{tc:.3f}|{t['maximum_total_min']:.3f}|")
    lines+=['',f"화요일regular의 거절 로그 비용벡터{trace['cost_vectors_checked']}개를 독립 산술로 재구성한 최대 오차는{trace['maximum_cost_error_minutes']:.3g}분 등가입니다. 이 검사는 원시 비용·물리 ETA 검산이며 새 로그확률 이동량의 검증과는 분리됩니다. [추적·비용 검산](grid-trace-and-costs.json).",'',
      '## 검증과 남은 한계','',
      '- 기존 시험을 포함한89개 시험 통과. 고정 조건 실제 Gumbel추첨,0회 보존,기존 변경비용 역전 방지,비도보 상대비율·중복 후보·큰 횟수 안정성,두 결정지점 전달을 확인했습니다. 시험 준비 중 발견한 mock/API·fixture 오류 로그도 보존했습니다. [최종 시험](boundary-tests.log).',
      '- [구현 에이전트의 읽기 전용 수식/연결 검토](../collaboration/v12_repeat_walk_review_261112220847/READ_ONLY_REVIEW.md)는 새 차단 사유를 찾지 못했습니다. [검토 증거](../collaboration/v12_repeat_walk_review_261112220847/evidence.json)는 접수17해시·현재14런타임·22동결해시·당시7개시작영수증을 대조한 범위이며, 시험 실행이나 전체10조건의 독립 성능 승인으로 해석하지 않습니다.',
      '- 정원·FIFO·차량 시계·수요 질량·구간 합계·누적대기 원장은10조건을 감사했습니다.20분과 미완료 조건은 이번 시드/입력 범위의 결과이며 모든 난수나 실제 현장의 보장은 아닙니다. [실행 감사](grid-validation.json), [확률 검산](grid-probability-validation.json).',
      '- 새 날짜 정답을 열지 않았고 증가율을 실측으로 추정하지 않았습니다. 수강편람 가중 수요·목적지와 기숙사 시나리오·도서관 경유 가정·교외 선점·혼잡 순서등급의 역할은 [직전 자료 설명](../261112210916/RESULTS_FINAL.md)을 계승합니다. 순서형 혼잡을 실승객 수로 환산하지 않습니다.',
      '- [실측 사용 장부](OBSERVATION_USAGE.md)는 기존53항목·보존 스냅샷39개·동결 입력7개와 최신 화요일 정정을 대조합니다. 버스 통과간격·구간시간·순서형 혼잡은11/10입력을 계승하고11/11은 이미 탐색한 진단으로 구분했습니다. 개인 대기189초+탑승 후30초는 전역 도착/승차/출발 분리가 부족해 개인 오차 비교불가로 남겼습니다. [보행·줄·차내·총시간 평균20행](mean-physical-components.csv)은 모의 여정 단위를 명시합니다.',
      '- 접근 수요 예측은 이미 출발해 걷거나 준비 중인 합성 승객의 현재 의도/준비 예정시각을 아는 정보 가정입니다. 실제 학생 위치·목적지 자료가 아닙니다. 미래 경로 변경·동시 준비 순서·미출발 수요·차내 승객의 후속 환승에는 근사가 남습니다.',
      '- [미래 평가22개 동결해시](future_evaluation_plan.json), [소스·운영V11 읽기 확인](final_verification.json), [원표 정합성 검사](artifact_verification_final.json). 이번 후보는 비운영이며 사용자 승인 전V11과 교체하지 않습니다.','']
    out.write_text('\n'.join(lines),encoding='utf8')
    result={'release_id':w.name,'parent':PARENT.name,'recommendation':'KEEP_PRIVATE_DO_NOT_PROMOTE','internal_ten_case_gate_passed':passed,
      'conditional_probability_formula':'1-(1-p_ref)**(2**n)','growth_factor':2.,'growth_empirically_estimated':False,'base_distance_and_cost_coefficients_unchanged':True,
      'review_timing_unchanged':True,'unlimited_changes':True,'maximum_all_recorded_continuous_wait_min':maxwait,'over20_episode_weight':over,'unserved_trip_weight':d['unserved_trip_weight'],
      'mean_total_improved':improvements['mean'],'p99_total_improved':improvements['p99'],'max_total_improved':improvements['maximum'],
      'maximum_total_journey_min':totalmax,'parent_maximum_total_journey_min':parentmax,'p99_delta_range':[min(p99),max(p99)],
      'mean_walk_delta_range':[min(walk),max(walk)],'mean_change_count_delta_range':[min(changes),max(changes)],'mean_total_regressions':regress,
      'primary_loss_before':pilot['primary_reused_report_loss_before'],'primary_loss_after':pilot['primary_reused_report_loss_after'],
      'old_field_errors_improved':field_improved,'old_field_errors_worse':field_worse,'named_40_reference_exceed_conditions':named_exceed,
      'target_trace':trace['traces'],'recorded_probability_checks':prob['recorded_probability_checks'],
      'independent_field_accuracy':'NOT_EVALUABLE','new_day_outcomes_opened':False,'production_writes':False,'report_sha256':sha(out)}
    target=w/'release_recommendation_final.json';assert not target.exists();target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    readme=w/'README.md'
    readme.write_text(f'# 목적지 도보확률 후보 {w.name}\n\n[최종 결과](RESULTS_FINAL.md)를 보세요. 경로 변경에 따라 포화형 지수 규칙을 적용한 비운영 후보이며, 운영V11은 유지합니다.\n',encoding='utf8')
    print('REPORT_WRITTEN',w.name,'maxwait',maxwait,'probability_checks',prob['recorded_probability_checks'],flush=True)
if __name__=='__main__':main()
