"""Render the already saved numeric ledger, including legitimate zero balances."""
from pathlib import Path
import json,math,sys,time
w=Path(sys.argv[1]).resolve();deadline=time.monotonic()+3600
while not (w/'mechanism-diagnosis.json').exists():
    assert time.monotonic()<deadline
    time.sleep(10)
d=json.loads((w/'mechanism-diagnosis.json').read_bytes())
s=['# 법대·정문·긴 대기 원인 분석','','이미 완료한 고정 실험의 사건 원장을 분석했습니다. 새 수요나 계수를 맞추는 작업은 하지 않았습니다.','',
    '## 정문 수요와 승차의 분해','','16:30~17:04에 들어온 양과 나간 양으로 줄의 변화를 재구성했습니다. 버스 시각·노선·차량·정원은 전후 동일합니다.','',
    '|후보|16:30 줄|누적 유입|누적 이탈|17:04 줄|17:03 분 평균|','|---|---:|---:|---:|---:|---:|']
for r in d['gate_mass_balances']:
    f=r['flow'];v=[f.get(k,0.) for k in ['queue_at_16_30','arrivals','exits','queue_at_17_04','minute_mean_17_03']]
    s.append('|'+r['model']+'|'+'|'.join(f'{x:.3f}' for x in v)+'|')
s+=['','관측 33~39명 한 건으로 실제 유입과 잔여 좌석을 각각 식별할 수는 없습니다. 정문 오차를 보려면 같은 시각 유입·승차·차내 혼잡의 자료가 추가로 필요합니다. 누적 승차 자리 기회는 고유 승객 수가 아닙니다.','',
    '## 법대 오후 피크 구성','','각 모형·요일의 **자신의 최대 줄 시각**에 남아 있는 목적지별 인원입니다. 정류장에 도착한 누적량과 구분합니다.','',
    '|후보·요일·ARS|최대 줄|설입행|그중 이전 버스 이용|낙성대행|기숙사행|','|---|---:|---:|---:|---:|---:|']
for r in d['models']:
    for p in r['law_afternoon_peak_stock']:
        c=p['destination_stock'];dorm=math.fsum(v for k,v in c.items() if k.startswith('dorm'))
        s.append(f"|{r['model']}·{r['day']}·{p['ars']}|{p['maximum_queue']:.3f}|{c.get('snu',0):.3f}|{c.get('snu_prior_ride',0):.3f}|{c.get('nak',0):.3f}|{dorm:.3f}|")
s+=['','## 남은 20분 초과 대기','','원시 대기 방문 가중량입니다. 연속 방문을 합친 정류장 표와 범위가 다를 수 있고, 고유 학생 수가 아닙니다.','',
    '|후보·요일|20분 초과 방문|그 개인 기준 이내|그 개인 기준도 초과|가장 긴 방문, 분|그 개인 기준, 분|','|---|---:|---:|---:|---:|---:|']
for r in d['models']:
    c=r['raw_visit_wait_categories'];m=r['largest_raw_wait']
    s.append(f"|{r['model']}·{r['day']}|{c.get('over20',0):.3f}|{c.get('within_personal',0):.3f}|{c.get('beyond_personal',0):.3f}|{m['seconds']/60:.3f}|{m['personal_seconds']/60:.3f}|")
s+=['','개인 기준 이내의 긴 대기는 중앙값 20분과 기존 이질성에 의해 생길 수 있습니다. 개인 기준은 재검토 기회이지 강제 이탈 시각은 아닙니다. 반대로 기준을 넘긴 방문도 숨기지 않고 원장에 남겼습니다. 이미 내보낸 최초 예측과 이후 실제 만차·새 유입은 다른 정보이므로, 최초 예상이 짧았다는 이유만으로 실제 대기가 짧을 것이라고 처리하지 않았습니다.','',
    '## 정류장별 20분 초과 변화','','연속 대기를 합친 가중 구간입니다. 악화가 큰 쪽과 개선이 큰 쪽을 함께 표시했습니다.','',
    '|요일·정류장|전 → 후|증감|','|---|---:|---:|']
rows=d['canonical_stop_over20_changes']
for r in [*rows[:8],*rows[-8:]]:
    s.append(f"|{r['day']}·{r['stop']}({r['node']})|{r['before']:.3f} → {r['after']:.3f}|{r['delta']:+.3f}|")
s+=['','[검산 가능한 수치 원장](mechanism-diagnosis.json), [결과 본문](RESULTS.md).','',
    '문서 생성 시 0명인 경계값의 표시 처리를 보완했습니다. 저장된 수치 원장이나 모형 사건 실행을 다시 계산한 것은 아닙니다.','']
p=w/'MECHANISM_DIAGNOSIS_v2.md';assert not p.exists();p.write_text('\n'.join(s),encoding='utf8')
print('RENDERED_MECHANISM_REPORT',w.name,flush=True)
