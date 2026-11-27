"""Build a reviewable, source-backed report from completed immutable experiments."""
from pathlib import Path
import argparse,csv,hashlib,json,math
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent;PARENT='261112132736'
def read(p):return json.loads(p.read_bytes())
def csvrows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def number(x):return f'{float(x):.2f}'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,value):
    assert not p.exists(),str(p);p.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');args=p.parse_args();work=Path(args.candidate).resolve()
    report=work/'RESULTS_FINAL.md';assert not report.exists()
    d=read(work/'grid-diagnostics.json');v=read(work/'grid-validation.json');base=read(ANALYSIS/PARENT/'grid-validation.json')
    selected=read(ROOT/'calibration_selection_final.json');winner=next(x for x in selected['scores'] if x['model']==work.name)
    assert selected['selected_for_full_grid']==work.name
    fields=csvrows(work/'grid-field-comparison.csv');classrows=csvrows(work/'class-end-journey-comparison.csv')
    old={(r['case']['day'],r['case']['scenario']):r for r in base['results']}
    def q(r,metric):return r['all_recorded_diagnostics']['finished_trip_quantiles'][metric]
    passed=d['all_invariant_audits_pass'] and d['all_continuous_waits_under20'] and d['unserved_trip_weight']<1e-7
    lines=[f'# 추가 논문 검토와 V12 실측 정합성 보정 — {work.name}','',
      f"**{'내부 평일 10조건 통과' if passed else '내부 조건 미충족'} · 과거 관측 후향 보정 · 새 날짜 정확도 미검증 · 운영 V11 유지**",'',
      '직전 수정 후보 `261112132736`에서 출발했습니다. 수치는 수업 편람·수강인원과 기존 목적지/이동수단 배분에 따른 가중 모의 여정입니다. 실제 학생 개인들의 목적지·퇴실 시각·통행수단을 모두 관측한 모형은 아닙니다. 운영 모델 `capacity_v11 / 261110162302`과 공개 사이트는 교체하지 않았습니다. 사용자 지시는 [운영 교체 범위](USER_DIRECTIVE.md)에 보존되어 있습니다.', '',
      '## 논문에서 확인하고 실제로 바꾼 것', '',
      '1. **미래 차량의 혼잡 비용을 현재 줄과 일치시켰습니다.** [Drabicki 등(2023)](https://doi.org/10.1016/j.rtbm.2023.100963)은 혼잡 때문에 다음 차를 기다리는 선택과, 그 선택으로 다음 차가 채워지는 일관성을 다룹니다. 기존 코드는 앞사람의 승차로 승차 가능 시간을 계산하면서 미래 차의 혼잡 비용에는 그 승차를 누락했습니다. 44명 차량에 앞사람40명·본인1명이면 진입 부하는41명분인데 비용에는1명분만 들어갈 수 있었습니다. 이제 알려진 잔류 인원+그 차에 타는 선행 인원+본인을 함께 반영합니다. 과거 여석에서 추정한 예약 용량은 실제 사람과 분리해 진단에만 남깁니다. 이미 관측 혼잡등급이 있는 시내버스의 순서형 비용은 유지했습니다.', '',
      '2. **사람마다 달랐던 기존 보행 배율을 복원했습니다.** [Berggren 등(2022)](https://doi.org/10.1080/23249935.2021.1973146)은 접근·환승·마지막 보행과 관측 범위를 구분합니다. 점검 결과 기존 물리 경로 보정이 동결 입력의 개인별 배율을 모두1로 덮었습니다. 원래0.799~1.345 배율을 첫 접근·환승·마지막 보행에 각각 한 번만 적용합니다. 새 난수나 해외 보행 계수를 넣지 않았습니다. 명목4.8km/h와 경로의 경사·계단 규칙은 유지하지만, 개인별 시간은 달라집니다. 이 배율도 서울대 실측값이 아닌 기존 시나리오입니다.', '',
      f"3. **미측정 출발 시차만 전교 공통 배율 α={winner['alpha']}로 후향 보정했습니다.** [Kaparias 등(2015)](https://openaccess.city.ac.uk/id/eprint/6257/)의 도착·대기 측정과 [Liu & Miller(2020)](https://doi.org/10.1016/j.tra.2020.09.014)의 차량 시계·승객 접근 전략 구분을 참고했습니다. 해외의 수치나 분포를 가져온 것이 아니라, 서울대의 과거 방향확인 줄 관측 세 점에 유효 출발시각을 맞춘 탐색입니다. `출발 = 수업 종료 + α×(원래 출발−수업 종료)`이며 질량·건물·목적지·차량 시계·정원은 보존합니다. 6,201개 수업 종료 사건과297,648개 원본 가중 조각의 연결을 전부 검증했습니다. 조각 수는 실제 사람 수가 아닙니다.", '',
      '[Arriagada 등(2025)](https://doi.org/10.1016/j.tra.2025.104467)은 실제 반복 이용 이력으로 관성을 추정합니다. 서울대 이력이 없는 상태에서 관성·반복 변경 확률을 임의로 높여 줄을 맞추는 수정은 하지 않았습니다. 취향·hazard·혼잡 비용의 숫자 계수도 이번에 적합하지 않았습니다. 논문의 주장, 코드 오류 수정, 미추정 시나리오 복원, 후향 보정을 서로 구분합니다.', '',
      '원문 확인 쪽수·한계는 [추가 이론 검토](../v12_empirical_refinement_20261112/ADDITIONAL_THEORY.md), [구현 에이전트의 문헌 검토](../collaboration/v12_additional_papers_20261112/REVIEW_KO.md), [혼잡 비용 검토](../collaboration/v12_additional_papers_20261112/CROWDING_READ_ONLY.md), [보행·혼잡 계산 독립 점검](../collaboration/v12_additional_papers_20261112/ADDENDUM_B_C_261112164617.md), [수업 자료 연결 점검](../collaboration/v12_additional_papers_20261112/ADDENDUM_D_261112165437.md)에 있습니다. 각각의 읽기 범위가 달라 모든 논문 전체를 분석했다고 주장하지 않습니다.', '',
      '## 관측과 맞는 정도', '',
      '관측 초가 불명확하므로 해당1분 안에서 균등하게 측정했다고 가정했습니다. 아래 평균과 오차는 다릅니다. 오차는 매 시점에서 관측값/범위까지의 절대거리를 적분한 값이며, 평균 줄 인원에 절대값을 한 번 적용한 값이 아닙니다. 줄은 가중 모의 인원분이어서 소수가 나옵니다. 월요일 날짜는 대화에서 추정됐고 문화관 방향은 미확정입니다.', '',
      '|관측|실제 보고|직전 후보 평균 / 오차|이번 후보 평균 / 오차|', '|---|---:|---:|---:|']
    count_improved=0;observations=[]
    err='expected_absolute_distance_to_count_or_interval'
    for row in [r for r in fields if r['model']==work.name and r['scenario']=='regular']:
        before=next(r for r in fields if r['model']==PARENT and r['scenario']=='regular' and r['observation_id']==row['observation_id'])
        improved=float(row[err])<float(before[err]);count_improved+=improved
        band=row['observed_low'] if row['observed_low']==row['observed_high'] else row['observed_low']+'~'+row['observed_high']
        lines.append(f"|{row['weekday']} {row['reported_minute']} {row['stop']}|{band}|{number(before['uniform_minute_mean'])} / {number(before[err])}|{number(row['uniform_minute_mean'])} / {number(row[err])}|")
        observations.append({'observation_id':row['observation_id'],'parent_mean':float(before['uniform_minute_mean']),'new_mean':float(row['uniform_minute_mean']),
          'parent_error':float(before[err]),'new_error':float(row[err]),'improved':improved})
    decrease=1-winner['primary_normalized_loss']/selected['parent_primary_normalized_loss']
    lines += ['',f"방향확인 세 점의 정규화 손실은 {selected['parent_primary_normalized_loss']:.6f}→{winner['primary_normalized_loss']:.6f}, 감소율은 {decrease*100:.2f}%입니다.",
      f'네 보고 중 절대 구간 오차가 줄어든 것은 {count_improved}/4건입니다. **이 네 관측은 이전에도 구조 선택에 썼고 이번에는 α 보정에도 재사용했습니다. 독립 검증 정확도·실시간 예측 정확도가 아닙니다.** [regular/peak 전체 비교와 분 안 최소·최대](grid-field-comparison.csv)를 함께 보세요.', '',
      '## 버린 실험과 보정의 범위', '',
      '먼저 과거 제약으로 생긴 예약 용량까지 사람처럼 혼잡 비용에 넣는 후보 A를 별도 민감도로 남겼고, 실제 알려진 부하만 쓰는 B를 기본 구조로 선택했습니다. 이 수정만으로는 행정관 오차가 거의 변하지 않았습니다. C는 B에 개인별 보행 배율만 복원한 직접 대조입니다.', '',
      '첫 격자 α=0.5·0.75·1에서 출발 시차를 압축한 두 후보는 행정관 과대추정을 악화했습니다. 이 결과를 본 뒤 반대 방향1.25·1.5를 시험하도록 두 번째 격자를 등록했습니다.1.25에서 월요일과 화요일의 상충이 커서 마지막으로 중간값1.125 하나를 추가한 뒤 탐색을 종료했습니다. 따라서 연구 전체를 정답 확인 전 사전등록 실험이라고 부를 수 없습니다. 모든 후보와 실패 증거를 보존했습니다.', '',
      '|후보|α|방향확인3점 평균 정규화 손실|월·화 내부 대기/수지 조건|', '|---|---:|---:|---|']
    for s in selected['scores']:
        lines.append(f"|{s['model']}|{s['alpha']}|{s['primary_normalized_loss']:.6f}|{'통과' if s['pilot_internally_feasible'] else '미충족'}|")
    lines += ['',
      '목적함수는 세 관측 각각의 1분 내 기대 절대 구간 오차를53·67·36으로 나눈 평균입니다. 문화관5명은 방향 불확실성이 있어 보조로만 봤습니다. 목적함수 산출 때 생성기와 다른 구간 경계 적분법으로 원본 큐 시계열을 다시 계산해 일치를 확인했습니다. [점수·분모·관측·원장 해시](../v12_empirical_refinement_20261112/calibration_selection_final.json), [두 번째 탐색 등록](../v12_empirical_refinement_20261112/stage2_protocol.json), [마지막 중간값 등록](../v12_empirical_refinement_20261112/final_midpoint_protocol.json), [기존 문서와 보정 범위 명확화](protocol_clarification.json).', '',
      'α는 실제 학생의 건물 이탈 시차를 식별한 값이 아닙니다. 원래의 즉시 이동50%, 목적지/수단 배분, 명목 셔틀 배차 위상이 미측정이라 그 오차도 흡수할 수 있습니다. α는 평균 시차와 분산을 함께 바꾸며, 같은 수업의 순서는 유지해도 서로 다른 수업 및 버스와의 만남은 바뀝니다. 일별·정류장별로 따로 계수를 맞추거나 수요를 삭제하지 않았습니다.', '',
      '## 평일 전체와 부작용', '',
      '월~금×regular/peak, 시드0의 같은 수요·공급 시나리오입니다. 아래 총시간은 **모의 출발→목적지**이며 처음 건물 안에서 머무는 시차는 제외합니다. 서로 다른 조건은 합쳐 실제 주간 인원으로 해석하지 않습니다.', '',
      '|요일|조건|평균 총시간 직전→이번|p99 직전→이번|최장 총시간 직전→이번|이번 최대 연속대기|', '|---|---|---:|---:|---:|---:|']
    regressions=[];walk_deltas=[];mean_improved=p99_improved=max_improved=0
    for row in d['cases']:
        c=row['case'];before=old[c['day'],c['scenario']]['extended_diagnostics']['finished_trip_quantiles'];new=q(row,'total_min');b=before['total_min']
        lines.append(f"|{c['day']}|{c['scenario']}|{number(b['mean'])}→{number(new['mean'])}|{number(b['p99'])}→{number(new['p99'])}|{number(b['maximum'])}→{number(new['maximum'])}|{number(row['all_recorded_diagnostics']['all_recorded_time_max_continuous_wait_min'])}|")
        mean_improved+=new['mean']<b['mean'];p99_improved+=new['p99']<b['p99'];max_improved+=new['maximum']<b['maximum']
        walk_deltas.append(q(row,'walk_min')['mean']-before['walk_min']['mean'])
        if new['mean']>b['mean']:regressions.append({'day':c['day'],'scenario':c['scenario'],'increase_min':new['mean']-b['mean']})
    maximum=max(r['all_recorded_diagnostics']['all_recorded_time_max_continuous_wait_min'] for r in d['cases'])
    over=math.fsum(r['all_recorded_diagnostics']['all_recorded_time_over20_episode_weight'] for r in d['cases'])
    late=math.fsum(r['late_finished_weight'] for r in d['cases'])
    lines += ['',f'평균 총시간 감소 {mean_improved}/10조건, p99 감소 {p99_improved}/10조건, 최대 총시간 감소 {max_improved}/10조건입니다. 평균 도보시간 변화는 {min(walk_deltas):+.2f}~{max(walk_deltas):+.2f}분입니다. 모든 지표가 좋아진 것은 아닙니다.', '',
      f"모든 기록 시각을 포함한 최대 연속 정류장 대기는 **{maximum:.6f}분**,20분 초과 구간 가중치 합 **{over:.6f}**, 미완료 가중치 합 **{d['unserved_trip_weight']:.6f}**, 표시창 이후 완료 가중치 합 **{late:.6f}**입니다. 대기/보행·환승을 포함한 전체 여정은 별도로 보존했습니다.20분 강제 이탈·줄40명 자르기·수용량 증가는 없습니다.", '',
      f"[모든 정류장 {d['stop_rows']}행](grid-all-stops.csv), [진입 시각별30분 구간 {d['half_hour_rows']}행](grid-half-hour-waits.csv), [보행·누적대기·총시간·변경횟수 분포](grid-journey-comparison.csv). 재방문과 변경횟수도 진단에 남으며 변경 상한은 없습니다.", '',
      '### 건물 안에서 기다리는 시간까지 포함', '',
      '출발 시차를 바꿨으므로 짧아진 줄만 보고 개선이라고 결론내리지 않습니다. 아래는 **수업 종료→최종 목적지**로 다시 계산한 평균입니다. 수업 후 건물 안 시간도 포함한 모의 결과이며 실제 관측시간은 아닙니다. [평균·분위수·최대 원표](class-end-journey-comparison.csv).', '',
      '|요일|조건|수업 종료→목적지 평균 직전→이번|변화(분)|', '|---|---|---:|---:|']
    class_regressions=[]
    for row in d['cases']:
        c=row['case'];b=next(r for r in classrows if r['model']==PARENT and r['weekday']==c['day'] and r['scenario']==c['scenario'] and r['metric']=='class_end_to_destination_min')
        n=next(r for r in classrows if r['model']==work.name and r['weekday']==c['day'] and r['scenario']==c['scenario'] and r['metric']=='class_end_to_destination_min')
        delta=float(n['mean'])-float(b['mean'])
        lines.append(f"|{c['day']}|{c['scenario']}|{number(b['mean'])}→{number(n['mean'])}|{delta:+.2f}|")
        if delta>0:class_regressions.append({'day':c['day'],'scenario':c['scenario'],'increase_min':delta})
    tail=read(work/'tail_regression_diagnosis_final.json')
    trace=tail['new_worst']
    lines += ['', '### 줄이 짧아도 남은 긴 여정', '',
      f"화요일regular의 같은 원본 가중 조각 하나는 직전 {tail['same_source_parent_before'][0]['duration_min']:.2f}분에서 이번 {trace['duration_min']:.2f}분으로 길어졌습니다. 경로 변경 {trace['route_change_count']}회, 도보 {trace['leg_time_minutes']['walk']:.2f}분, 여러 줄의 대기 합 {trace['leg_time_minutes']['queue_wait']:.2f}분, 승차 {trace['leg_time_minutes']['ride']:.2f}분입니다. 같은 정류장 인근을 다시 거쳐 윗공대로 올라간 뒤 목적지까지 걷는 이례적인 경로입니다.", '',
      f"이 조각의 가중치는 {trace['weight']:.6f}, 해당 조건 수요의 {tail['new_worst_weight_share']*100:.6f}%이며 실제 관측한 학생이나 발생 확률이 아닙니다. 한정된 표본의 극값만으로 모든 행동이 나빠졌다고 단정할 수 없지만, 연속대기20분 통과가 전체 여정의 현실성을 보장하지도 않습니다. 같은 부모라도 보행 배율·출발 시각·내생적 선택 경로가 함께 달라졌으므로 α 단독 원인으로 해석하지 않습니다. 미래 첫 승차가능 서비스 근사와 반복 선택의 계속가치는 후속 검토 대상으로 남습니다. [실제 보행·대기·승차 합계를 맞춘 최종 추적](tail_regression_diagnosis_final.json).", '',
      '### 40명 참고 조건', '',
      '사용자 기억에 근거한40명은 불확실한 참고값입니다. 실제 측정 상한으로 강제하지 않았습니다. 최대 줄뿐 아니라40명 초과가 지속되는 시간도 확인했습니다.', '',
      '|정류장 ARS|10조건 최대 줄 인원분|40명 초과 조건|최장 연속 초과(분)|', '|---|---:|---:|---:|']
    groups={}
    for r in d['cases']:
        for s in r['named_stop_40_recollection_comparison']:groups.setdefault(str(s['ars']),[]).append(s)
    named_exceed=0
    for ars,items in sorted(groups.items()):
        n=sum(s['maximum_queue']>40 for s in items);named_exceed+=n
        lines.append(f"|{items[0]['name']} {ars}|{number(max(s['maximum_queue'] for s in items))}|{n}/10|{number(max(s['longest_spell_above40_minutes'] for s in items))}|")
    lines += ['',f'참고값 초과는 정류장×조건 {named_exceed}/40개입니다. 이 조건과 과거 줄을 모두 설명하는 완성 모형은 아닙니다.', '',
      '## 검증 및 남은 문제', '',
      '- 67개 단위·통합 시험을 통과했습니다. [시험 로그](boundary-tests.log).44명 두 대, 미래 선행 탑승의 중복 제외, 예약 용량과 알려진 사람 구분, FIFO fast/slow 경로 일치, 개인별 배율 한 번 적용, 전체 금요일 준비의 수요·차량시계·수업종료 계보 보존을 포함합니다.',
      '- 전체10조건 원장의 수요·승하차 질량, 정원, 운행 명단·시각, 실제 탑승 의향자 사이 FIFO, 누적대기, 보행/대기/승차 시간 분해를 독립 감사했습니다. [실행 감사](grid-validation.json), [상세 진단](grid-diagnostics.json), [소스·입력·공개V11 읽기 확인](final_verification.json), [보고서/원표 정합성 검사](artifact_verification_final.json). 소프트웨어 감사 통과와 실제 정확도는 다릅니다.',
      '- 한 차의 알려진 진입 부하를 이후 승차 구간에도 적용하는 근사는 남습니다. 미래 유입·중간 하차·모든 자발적 승차 거절을 완전히 예측한 부하 곡선이나 Bellman 계속가치는 아닙니다. 최소1명분 한계 질의는 합성 조각의 실제 질량이나 관측 인원수가 아닙니다. 혼잡등급을 정확한 사람 수로 환산하지 않았습니다.',
      '- 실제 목적지·첫 수단·즉시 하교 비율, 교외에서 이미 탄 사람 수, 학교 셔틀의 실제 출발 위상은 미확정입니다. 출발 시차 보정만으로 잠재 수요를 역추정했다고 주장할 수 없습니다.',
      '- 화요일189초는 한 사람의 줄 대기, 추가30초는 승차 후 출발까지의 시간입니다. 전역 엔진은 도착·승차·출발 사건을 합치는 근사가 남아 있어 이를 전체 차량의 승차·정차 분포로 적합하지 않았습니다. 두 사진이나67명 줄을 여러 개의 독립 대기시간 표본으로 세지 않았습니다.',
      '- 위 숫자는 시드0의 유한10조건입니다. 모든 난수·현장 상황에서20분 이하를 보장하지 않습니다. 새 날짜 정답은 열지 않았습니다.22개 코드/입력 해시를 [동결](future_evaluation_plan.json)했으며,2026-11-12 완료 날짜는11월13일 이후에 범위·누락·스키마를 점검한 다음 별도 검증할 수 있습니다.',
      '- 운영 교체는 하지 않았습니다. 기존 모델·탈락 후보·원본 자료·실패 로그를 보존했습니다. 구현 에이전트와 이 결과 및 한계를 공유합니다.', '',
      '## 재현 및 계보', '',
      '`261112132736` → 알려진 부하 수정 B `261112164250` → 보행 배율 복원 C `261112164617` → 시차 배율 후보입니다. A `261112163730`은 예약 용량을 포함한 상한 민감도입니다. D `261112165437/165438`은 시차 압축 후 탈락한 후보이고 E `261112170547/170548`은 반대 방향 탐색입니다. 마지막 `261112171315`는 중간값1.125입니다. 모든 후보는 별도 폴더를 사용했습니다.', '',
      '생성·실행·점수·재분석·보고 스크립트는 `../v12_empirical_refinement_20261112/`에 있습니다. 이미 완료한 월·화regular 두 사례는 영수증과 감사 해시를 확인해 전체10조건에서 재사용했으며 같은 사례를 중복 실행하지 않았습니다. α 단독 효과의 대조는 C이며, 위 직전132736과의 전체 비교는 부하·보행·시차 변경을 모두 포함합니다.', '']
    report.write_text('\n'.join(lines),encoding='utf8')
    decision={'release_id':work.name,'operating_model':'capacity_v11/261110162302','recommendation':'KEEP_PRIVATE_DO_NOT_PROMOTE',
      'internal_ten_case_gate_passed':passed,'retrospective_queue_calibration':True,'parameter':'cohort_release_lag_scale','alpha':winner['alpha'],
      'independent_field_accuracy':'NOT_EVALUABLE','old_queue_reports_improved_vs_immediate_parent':count_improved,
      'primary_normalized_loss_before':selected['parent_primary_normalized_loss'],'primary_normalized_loss_after':winner['primary_normalized_loss'],
      'primary_loss_decrease_fraction':decrease,'field_comparisons':observations,
      'maximum_all_recorded_continuous_wait_min':maximum,'over20_episode_weight':over,'unserved_trip_weight':d['unserved_trip_weight'],
      'mean_total_improved_conditions':mean_improved,'p99_total_improved_conditions':p99_improved,'max_total_improved_conditions':max_improved,
      'mean_total_regressions':regressions,'mean_walk_change_range_min':[min(walk_deltas),max(walk_deltas)],
      'class_end_total_mean_regressions':class_regressions,'named_40_reference_exceed_conditions':named_exceed,
      'rare_tail_regression':{'case':tail['new_case']['case'],'source_parent':trace['parent_id'],'before_total_min':tail['same_source_parent_before'][0]['duration_min'],
        'after_total_min':trace['duration_min'],'route_changes':trace['route_change_count'],'scenario_weight':trace['weight'],'scenario_weight_share':tail['new_worst_weight_share']},
      'new_day_outcomes_opened':False,'production_writes':False,'report_sha256':sha(report)}
    save(work/'release_recommendation_final.json',decision)
    (work/'README.md').write_text(f'# 비운영 V12 추가 개선 후보 {work.name}\n\n[최종 보고서](RESULTS_FINAL.md)를 보세요. 과거 관측에 맞춘 유효 출발시각 보정이며 새 날짜 정확도는 미검증입니다. 운영V11은 유지했습니다. 수업종료 기준 총시간·퇴행·실패 후보도 보고서에 함께 남겼습니다.\n',encoding='utf8')
    print('REPORT_COMPLETE',work.name,'queue_report_improvements',count_improved,'primary_loss_decrease',decrease,flush=True)
if __name__=='__main__':main()
