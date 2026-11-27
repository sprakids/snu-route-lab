"""Publish every registered main condition and its tradeoffs, without refitting."""
from pathlib import Path
import sys,json,csv,math,hashlib
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent/'261116010854'
def read(p):return json.loads(p.read_bytes())
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,s):
    assert not p.exists(),p
    p.write_text(s,encoding='utf8')
def main():
    w=Path(sys.argv[1]).resolve();v=read(w/'grid-validation.json')['results'];old=read(BASE/'grid-validation.json')['results']
    assert len(v)==10
    pairs=[(next(b for b in old if (b['case']['day'],b['case']['scenario'])==(a['case']['day'],a['case']['scenario'])),a) for a in v]
    over=lambda r:r['extended_diagnostics']['all_recorded_time_over20_episode_weight']
    mx=lambda r:r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min']
    q=lambda r:r['extended_diagnostics']['finished_trip_quantiles']['total_min']
    before=math.fsum(over(a) for a,b in pairs);after=math.fsum(over(b) for a,b in pairs)
    fields=rows(w/'grid-field-comparison.csv');mine=[r for r in fields if r['model']==w.name];assert len(mine)==8
    key='expected_absolute_distance_to_count_or_interval';fp=[]
    for a in mine:
        b=next(r for r in fields if r['model']==BASE.name and (r['scenario'],r['observation_id'])==(a['scenario'],a['observation_id']))
        fp.append((b,a))
    e0=math.fsum(float(a[key]) for a,b in fp);e1=math.fsum(float(b[key]) for a,b in fp)
    d0=read(BASE/'grid-diagnostics.json')['cases'];d1=read(w/'grid-diagnostics.json')['cases']
    def named(ds,day,scenario,node):
        r=next(r for r in ds if (r['case']['day'],r['case']['scenario'])==(day,scenario))
        return next(x for x in r['named_stop_40_recollection_comparison'] if x['node']==node)
    law0=max(named(d0,r['case']['day'],r['case']['scenario'],n)['maximum_queue'] for r in v for n in [47,60])
    law1=max(named(d1,r['case']['day'],r['case']['scenario'],n)['maximum_queue'] for r in v for n in [47,60])
    causes=read(w/'grid-wait-cause-ledger.json')['cases'];within=math.fsum(c['counts'].get('over20_within_personal_weight',0.) for c in causes)
    rawover=math.fsum(c['counts']['over20_episode_weight'] for c in causes)
    delta=[q(b)['mean']-q(a)['mean'] for a,b in pairs]
    s=[f'# 남은 대기·정문·법대 개선 비교 {w.name}','',
       f'비교 기준은 직전 후보{BASE.name}입니다. 수요·목적지·운행·정원·속도·출발 지연·개인 기다림 분포와 취향을 고정하고 경로 선택의 정합성을 수정했습니다.20분 강제 이탈,40명 줄 절단, 숨은 배경 승객 추가는 하지 않았습니다.','',
       f'평일5일×기본/피크10조건의20분 초과 가중 대기 구간은 **{before:.3f}→{after:.3f}({(1-after/before)*100:.1f}% 변화)**, 최대 연속대기는 **{max(mx(a) for a,b in pairs):.3f}→{max(mx(b) for a,b in pairs):.3f}분**입니다. 재사용4관측×2배차 조건의 기대 절대오차 합은 **{e0:.3f}→{e1:.3f}({(1-e1/e0)*100:.1f}% 변화)**입니다. 감소율이 음수면 악화입니다. 가중 구간은 고유 학생 수가 아니며 두 배차 대안은 독립 날짜 표본이 아닙니다.','',
       '## 확인한 원인과 수정','',
       '1. 잠긴 초기/환승 노선 풀 때문에 선호가 풀려도 같은 정류장의 다른 합법 노선을 비교할 수 없었습니다. 현재 FIFO 위치에서 기존 경로와 합법 확장 정책을 비교합니다. 후속 경로까지 평가한 가장 낮은 비용의 확장1개를 대안으로 넣으며, 합집합을 강제하거나 목록 수로 확률을 키우지 않습니다. 대기 시작·준비·ticket·만차 경험·물리 이동 횟수는 유지합니다.',
       '2. 최초 선택이 첫 탑승 수단만 보존해, 원래 시내버스 직행 수요를 시내버스→통학셔틀로 바꾸고 환승 후 새로운 셔틀 충성을 적용했습니다. source94963/모의UID1519408의 무변경24.38분 사례를 기존 원장으로 확인했습니다. 이제 SNU/대학동은 원래 정책의 주수단 허용 집합도 보존합니다. 각 pool 멤버의 후속 경로, 교내 접근셔틀, 이미 탄 주수단과 해제 전 도보 중 승차를 구분합니다. 혼합 source 집합은 그대로 두며 새 비율을 정하지 않습니다. 기존 기준으로 허용이 풀린 뒤 주수단 변경은 가능합니다.',
       '3. 준비 중 같은 자리 노선 정책을 바꾼 뒤 타인의 예측에 남는 접근 의도 목록도 갱신했습니다. 기존 시각·인원·serial은 그대로이며 새 대기자를 만들지 않습니다.',
       '4. 법대21298 최대 대기의 낙성대45.61명 중42.99명은5511/5516 하차 후 환승 수요였습니다. 그곳에서 낙성대로 가는 저장된 첫 서비스는02-2뿐이며 직후 모의 여석은8.60명분이었습니다. 같은 정류장 노선 검토만으로 이 수요 전부를 다른 버스에 태울 수 없습니다.',
       '5. 사용자는 “목적지행 주노선에 빨리 타기인데, 접근용 버스를 탄 뒤 환승 대기까지 고려하진 않아”라고 명시했습니다. 이에 초기city선택의 바깥 대안을 첫feeder정류장이 아닌 주노선 물리 승차지로 묶었습니다. 각pool 멤버의 실제 후속경로를 목표별로 먼저 분리하고 접근 방법 하나를 고른 뒤 노드당 판단오차를 한 번 줍니다. 접근편 이후 차내·보행은 인지점수에 넣지만 환승 대기·준비는 빼고, 이후 줄·정원으로 초기 후보를 미리 제거하지 않습니다. 미래ETA도 동률에 사용하지 않습니다. 이는 실제 예상 승차시각이 아닌 사용자 설명에 따른 근시안적 접근 점수이며, 도착 뒤 실제 대기를 0으로 만든 것이 아닙니다.','',
       '[독립 원인 분석](../collaboration/v12_remaining_queues_20261116/DIAGNOSIS.md), [주수단 정적 검토](../collaboration/v12_remaining_queues_20261116/TRUNK_STATIC_REVIEW_261116103210.md), [사용자 명시 해석의 사전 계획](../v12_remaining_queues_20261116/PRIMARY_PROTOCOL.md).','',
       '## 요일·배차별 전체 기록','',
       '|요일|배차|최대 대기 전→후(분)|20분 초과 가중 구간 전→후|평균 총시간 전→후(분)|p99 전→후|최장 전→후|미완료|',
       '|---|---|---:|---:|---:|---:|---:|---:|']
    for a,b in pairs:
        c=b['case'];s.append(f"|{c['day']}|{c['scenario']}|{mx(a):.2f}→{mx(b):.2f}|{over(a):.2f}→{over(b):.2f}|{q(a)['mean']:.2f}→{q(b)['mean']:.2f}|{q(a)['p99']:.2f}→{q(b)['p99']:.2f}|{q(a)['maximum']:.2f}→{q(b)['maximum']:.2f}|{b['unserved_trip_weight']:.3f}|")
    s+=['',f'평균 총시간 변화 범위는{min(delta):+.3f}~{max(delta):+.3f}분입니다. 완료 조건부 분포이며 미완료는 별도 표시했습니다.20분 초과 원시 방문 중 개인 기준 안의 가중치는{within:.3f}/{rawover:.3f}({100*within/rawover if rawover else 0:.1f}%)입니다. 이 기준은 대안 검토 자격이지 반드시 떠나는 시각이 아닙니다. 정문 최종 대안 또는 더 느린 합법 대안 때문에 기준 뒤에도 기다릴 수 있습니다.','',
        '## 재사용 관측 비교','',
        '관측 분 안의 초를 균등하게 적분합니다. 평균의 절대오차와 기대 절대오차는 다릅니다. 네 관측은 이미 여러 후보 검토에 썼고 문화관 방향·월요일 날짜의 불확실성이 남습니다. 독립 정확도 검증이 아닙니다.','',
        '|시각·배차|관측|분 평균 전→후|기대 절대오차 전→후|','|---|---:|---:|---:|']
    for a,b in fp:s.append(f"|{b['reported_minute']} {b['scenario']}|{b['observed_low']}~{b['observed_high']}|{float(a['uniform_minute_mean']):.2f}→{float(b['uniform_minute_mean']):.2f}|{float(a[key]):.2f}→{float(b[key]):.2f}|")
    s+=['','## 법대 양방향40명 회상 기준','',
        '아래는 기존과 같은11:20~23:10 표시 구간의 비교입니다.40명은 회상 기준이며 실제 상한·차량 정원으로 적용하지 않았습니다. [표시 밖까지 포함한99노드×10조건 줄 프로필](grid-stop-queue-exposure.csv)도 별도로 공개합니다.','',
        '|요일·배차|21298 최대 전→후|21270 최대 전→후|21298의40명 초과 합계분 전→후|','|---|---:|---:|---:|']
    for b in v:
        day,sc=b['case']['day'],b['case']['scenario'];a0,a1=named(d0,day,sc,60),named(d1,day,sc,60);z0,z1=named(d0,day,sc,47),named(d1,day,sc,47)
        s.append(f"|{day} {sc}|{a0['maximum_queue']:.2f}→{a1['maximum_queue']:.2f}|{z0['maximum_queue']:.2f}→{z1['maximum_queue']:.2f}|{a0['minutes_above40_recollection_reference']:.2f}→{a1['minutes_above40_recollection_reference']:.2f}|")
    s+=['','## 해석과 남은 문제','',
        '- 초기 수단·주수단은 실제 선호 설문이 아닌 원래 계획의 대리값입니다. 이 수정은 대리값과 선택 규칙의 정합성 교정이며 실제 개인 선호를 새로 알아낸 결과가 아닙니다.',
        '- 최대 대기와 특정 정류장 줄, 총 귀가시간·최장 여정은 서로 다른 지표입니다. 일부만 좋아져도 모든 병목이 해결됐다고 부르지 않습니다. 표에서 악화 조건도 그대로 확인할 수 있습니다.',
        '- 관악02-2 정원24·일반버스50과 외부 탑승자 부재는 계승한 미확인 물리 가정입니다. 혼잡 등급을 인원으로 바꾸거나 정원을 키워 줄을 맞추지 않았습니다. 실제 차종·재차·하차와 목적지별 환승 관측이 있어야 남은 차이를 구분할 수 있습니다.',
        '- 원래 동일 정류장 경로 목록의 같은rid/board에 다른 후속 정책이 있는 모든 변형까지 개방한 것은 아닙니다. 차내에서 미리 다른 정류장에 내리는 선택도 새로 만들지 않았습니다.',
        '- 고정 시드0·고정 수요/공급의 조건부 모의 비교입니다. 새 날짜 실측 정답, 브라우저 성능, 사이트 연결·운영 교체를 완료한 모델로 표시하지 않습니다. 공개 V11과active/latest는 유지합니다.','',
        '## 자료와 검산','',
        '[가정·출처](SOURCES_AND_ASSUMPTIONS.md), [전체 정류장 대기](grid-all-recorded-stops.csv), [30분 진입집단 대기](grid-all-recorded-half-hour-waits.csv), [수업 종료부터 귀가](class-end-journey-comparison.csv), [대기 원인 원장](grid-wait-cause-ledger.json), [정문 유입·유출](gate-flow-before-after.json), [같은 운행의 모형 재차 비교](gate-service-diagnosis.json), [행동 경계 검사](grid-behavior-validation.json).','']
    write(w/'RESULTS.md','\n'.join(s))
    rec={'release_id':w.name,'comparison_parent':BASE.name,'main_cases':10,'diagnostic_cases':len(read(w/'experiment_lock.json')['pilot_cases'])-10,'intermediate_prototype_cases':6,
         'max_wait_before':max(mx(a) for a,b in pairs),'max_wait_after':max(mx(b) for a,b in pairs),'over20_weight_before':before,'over20_weight_after':after,'over20_reduction':1-after/before,
         'reused_field_error_sum_before':e0,'reused_field_error_sum_after':e1,'reused_field_error_reduction':1-e1/e0,'mean_journey_delta_range':[min(delta),max(delta)],
         'law_display_max_before':law0,'law_display_max_after':law1,'unserved_weight':math.fsum(r['unserved_trip_weight'] for r in v),
         'physical_gate_passed':all(r['status']=='PASS_INTERNAL_INVARIANTS' for r in v),'behavior_gate':read(w/'grid-behavior-validation.json')['status'],
         'strict_all_waits_under20_passed':after<1e-7,'law40_recollection_passed':law1<=40+1e-7,'operating_adoption_recommended':False,'new_date_accuracy':'NOT_EVALUATED',
         'report_sha256':sha(w/'RESULTS.md'),'production_writes':False}
    write(w/'recommendation.json',json.dumps(rec,ensure_ascii=False,indent=2)+'\n')
    print('REPORT_COMPLETE',json.dumps(rec,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
