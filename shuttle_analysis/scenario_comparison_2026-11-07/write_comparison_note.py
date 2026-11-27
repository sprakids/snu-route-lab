"""Write a concise calculation record from reviewed comparison outputs."""
from pathlib import Path
import json
import pandas as pd

ROOT=Path(__file__).resolve().parent
spec=json.loads((ROOT/'scenario_specs.json').read_text(encoding='utf-8'))
provenance=json.loads((ROOT/'simulation_outputs/execution_provenance.json').read_text(encoding='utf-8'))
assert provenance['status']=='complete'
valid=json.loads((ROOT/'comparison_validation.json').read_text(encoding='utf-8'))
w=pd.read_csv(ROOT/'weekly_stop_peak_comparison.csv',dtype={'stop_id':str})
daily=pd.read_csv(ROOT/'stop_peak_comparison.csv',dtype={'stop_id':str})
w=w[w.stage.eq('all')]
priority=['snu-410','120000174','120000173','snu-1001','snu-901','120900172','120000191','120000177']
labels={'snu-410':'행정관 셔틀','120000174':'유회진학술정보관·제1공학관 시내버스',
        '120000173':'제2공학관 시내버스','snu-1001':'301동 교내셔틀','snu-901':'302동 교내셔틀',
        '120900172':'노천강당 시내버스','120000191':'농생대 시내버스','120000177':'관악사삼거리 시내버스'}
def row(stop,scenario,window='afternoon'):
    x=w[w.stop_id.eq(stop)&w.scenario.eq(scenario)&w.window.eq(window)]
    assert len(x)==1,(stop,scenario,window)
    return x.iloc[0]
lines=['# 목적지·기숙사 비중 시나리오 비교 계산 기록', '',
 '2026-11-07 실제 오프라인 실행을 완료했습니다. 구현 채팅은 기존 이동 엔진을 보존한 별도 runner로 계산했고, 분석 채팅은 기존 결과의 가중치를 역산한 별도 계산과 대조하고 정류장별 비교를 집계했습니다.', '',
 '## 비교의 의미', '',
 '**숫자의 단위는 수강 인원을 가중한 예상 탑승 통행/5분입니다. 관측 탑승자, 고유 학생, 잔류 대기열, 혼잡률 또는 차량 정원 초과 인원이 아닙니다.** 정류장에 도착해 탑승하려는 통행을 뜻하며, 실제 만차나 탑승 실패는 모형에 없습니다.', '',
 '기준은 기숙사 5,772/29,613=19.4914%, 수업 후 즉시 이동 50%, 교외 목적지 서울대입구권:낙성대권:신림권=55.7:27.2:17.0입니다. 원문 합이 99.9%여서 계산 가중치만 55.7558%:27.2272%:17.0170%로 정규화했습니다. 기숙사는 별도 목적지로 유지해 교내 이동을 없애지 않았습니다.', '',
 '과거 값은 2022년 4월의 학생 전용·하교 전용이 아닌 전체 대중교통 통행 비중입니다. 신림권 전체를 대학동 대표 목적지에 대응시킨 가정이 있습니다. 현재 학생 목적지 비중이나 총학생회 설문 응답률로 해석하면 안 됩니다. 발행기관 원본 PDF는 미확보이며 공개 재게시 문서의 표 판독에 의존합니다. 원문 통행량 행 합계와 총계는 9통행 차이, 낙성대권의 사당 셔틀 묶음도 미해결 상태로 남깁니다.', '',
 '기숙사 분자는 사용자가 선택한 5,772명이고 분모는 2025년 대학 전체 재학생 29,613명입니다. 시점·관악캠퍼스 범위·실제 거주/수용 정의가 일치한다고 검증된 비율이 아니므로 참고 시나리오로 사용합니다.', '',
 '## 같은 조건으로 계산한 10개 경우', '',
 '| 시나리오 | 서울대입구권 % | 낙성대권 % | 대학동 대표점 % | 기숙사 % |',
 '|---|---:|---:|---:|---:|']
for s in spec['scenarios']:
    lines.append(f"| {s['label']} | {100*s['external_mix'][0]:.2f} | {100*s['external_mix'][1]:.2f} | {100*s['external_mix'][2]:.2f} | {100*s['dorm_share']:.2f} |")
lines += ['', '교외 세 방향의 비중은 기숙사 제외 교외 이동 안의 조건부 비중입니다. 한 방향을 10%p 늘린 경우 다른 두 방향에서 5%p씩 뺐습니다. 기숙사 비중을 고정하면 전체 이동에서 해당 방향이 증가하는 폭은 약 8.05%p입니다.', '',
 '## 하교 중심: 15:00–23:10', '',
 '아래 기준값은 월~금 중 해당 정류장에서 가장 큰 **10회 반복 평균의 5분 유입값**입니다. 시나리오별 피크 시각은 달라질 수 있습니다. 상·하행 도시버스 정류장 ID는 합치지 않았고, 같은 ID의 노선·최초/환승 탑승은 같은 시각에 합산했습니다.', '',
 '| 정류장 | 과거 참고 기준값 | 기준 피크 | 서울대입구 +10%p | 낙성대 +10%p | 대학동 +10%p | 균등 비중 |',
 '|---|---:|---|---:|---:|---:|---:|']
for stop in priority:
    b=row(stop,'historical_reference')
    change=[f"{row(stop,s).weekly_peak_change_percent:+.1f}%" for s in ['snu_plus10pp','nak_plus10pp','daehak_plus10pp','equal_reference']]
    lines.append(f"| {labels[stop]} | {b.peak_5min_weight:.1f} | {b.weekday} {b.peak_time} | "+' | '.join(change)+' |')
lines += ['', '증감률은 각 시나리오의 최대 5분 값과 과거 참고 시나리오의 최대 5분 값을 비교했습니다. 같은 요일·같은 시각의 증감은 stop_peak_comparison.csv의 weight_at_baseline_peak_bin 및 same_bin_change_percent에 별도로 남겼습니다.', '',
 '## 윗공대: 요일별 하교 시간의 유입', '',
 '| 정류장 | 요일 | 과거 참고 | 피크 시각 | 서울대입구 +10%p | 낙성대 +10%p | 대학동 +10%p |',
 '|---|---|---:|---|---:|---:|---:|']
for stop in priority[1:5]:
    for day in '월화수목금':
        p=daily[daily.stop_id.eq(stop)&daily.weekday.eq(day)&daily.window.eq('afternoon')&daily.stage.eq('all')].set_index('scenario')
        if 'historical_reference' not in p.index: continue
        b=p.loc['historical_reference']
        values=[f"{p.loc[s,'peak_5min_weight']:.1f} ({p.loc[s,'peak_change_percent']:+.1f}%)" for s in ['snu_plus10pp','nak_plus10pp','daehak_plus10pp']]
        lines.append(f"| {labels[stop]} | {day} | {b.peak_5min_weight:.1f} | {b.peak_time} | "+' | '.join(values)+' |')
lines += ['', '## 기숙사 비율 민감도', '',
 '교외 방향 비중과 즉시 이동률은 고정했습니다. 기숙사 거주자의 교내 버스 이용이 남아 있으므로 정류장에 따라 증가·감소 방향이 다를 수 있습니다.', '',
 '| 정류장 | 기숙사 10% | 기준 19.49% | 기숙사 30% | 10% 대비 30% 변화 |',
 '|---|---:|---:|---:|---:|']
for stop in priority:
    a,b,c=[row(stop,s).peak_5min_weight for s in ['historical_dorm10','historical_reference','historical_dorm30']]
    lines.append(f'| {labels[stop]} | {a:.1f} | {b:.1f} | {c:.1f} | {(c/a-1)*100:+.1f}% |')
lines += ['', '## 집계와 정합성 확인', '',
 f"- 기존 2026-2 강좌 자료의 평일 종료 사건 {provenance['weekday_ending_events']:,}개, 수강 인원 사건 합 {provenance['enrollment_event_sum']:,}, 건물 {provenance['buildings']}개를 사용했습니다. 동일 학생이 여러 강좌에 포함되므로 고유 인원이 아닙니다.",
 '- 전체 주간의 발생 이동 가중치는 즉시 이동률 50%에 따라 78,169입니다. 창 안의 탑승 유입 합은 도보 제외·시간창 제외·환승 포함 효과가 있으므로 이 값과 무조건 같지 않습니다. 보존 검산은 전체 시간의 이동수단 합으로 수행했습니다.',
 f"- 공통 난수 {provenance['replications']}회, 집단·목적지별 가중 입자 {provenance['particles_per_cohort_destination']}개를 사용했습니다. 목적지 확률 합, 이동수단 합, 최초 탑승 연결을 확인했습니다.",
 f"- 과거 균등비중 결과 재현 오차는 셀당 최대 {provenance['equal_baseline_max_absolute_error']:.8f}, 별도 역산 기준과 새 10개 시나리오의 차이는 최대 {valid['independent_archived_mixture_max_abs_cell_difference']:.8f}였습니다. 이는 수치 정합성 검산이며 실제 수요 예측 정확도 검증은 아닙니다.",
 f"- 원본 기존 파일 {provenance['original_files_verified_unchanged']}개와 원본 강좌 파일의 해시가 유지됐습니다. 실제 API 호출 {provenance['live_api_calls']}회, 새 실행 시간 {provenance['elapsed_seconds']:.1f}초입니다.",
 '- 기존 보행 속도·실내 이탈·노선 선택·시간표 가정을 유지했습니다. 수업별 실제 출석, 개인의 마지막 수업, 실제 귀가 시각, 차량 여유 좌석 및 일반 승객이 없으므로 과밀·탑승 실패·필요 증차 대수를 계산할 수 없습니다.',
 '- 기존 2026년 10월 시내버스 승하차 자료와 모형의 시간대 피크가 일부 다르다는 한계도 유지됩니다. 목적지 비중 민감도가 이 시각 오차를 보정하는 것은 아닙니다.', '',
 '## 재현 자료', '',
 '- 시나리오 명세: scenario_specs.json',
 '- 전체 정류장·요일·창·최초/환승 비교: stop_peak_comparison.csv',
 '- 방향별 상세: direction_peak_comparison.csv',
 '- 월~금 최대 비교: weekly_stop_peak_comparison.csv',
 '- 새 5분 원 집계: simulation_outputs/stop_inflow_5min_scenarios.csv',
 '- 목적지 조건부 평균: simulation_outputs/conditional_mean_bins.csv',
 '- 실행·보존 증거: simulation_outputs/execution_provenance.json 및 original_preservation_check.json',
 '- 분석 검산: comparison_validation.json 및 independent_cell_reconciliation.csv', '',
 '출처: [과거 보고서 공개 재게시](https://www.scribd.com/document/881211763/스크린샷-2025-04-24-15-06-29), [관악학생생활관 현황](https://snudorm.snu.ac.kr/기관-소개/현황/), [서울대 2025 통계연보 안내](https://www.snu.ac.kr/about/downloads?bbsidx=165605&md=v). 상세 원문 판독·한계는 ../collaboration/research_inputs.json과 ../traffic_results_2026-11-06/방향별_실제비중_추적결과.md를 보존했습니다.', '']
(ROOT/'목적지와_기숙사_비중_비교.md').write_text('\n'.join(lines),encoding='utf-8')
print('Saved calculation note with independently reconciled values.')
