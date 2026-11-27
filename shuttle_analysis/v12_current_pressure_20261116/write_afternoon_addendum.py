from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import hashlib,json,re
ROOT=Path(__file__).resolve().parent
data=json.loads((ROOT/'afternoon-peak-causes.json').read_bytes())['cases']
by=[];prior=[]
for case in data:
    counts=Counter()
    for r in case['destination_and_prior_ride']:counts[r['destination']]+=r['weight']
    assert abs(sum(counts.values())-case['matched_queue_weight'])<1e-5
    by.append(counts)
    prior.append(sum(r['weight'] for r in case['destination_and_prior_ride'] if r['destination']=='snu' and r['approach']=='after_prior_bus'))
total0,total1=[c['matched_queue_weight'] for c in data]
snu0,snu1=[x['snu'] for x in by]
nak0,nak1=[x['nak'] for x in by]
dorm0,dorm1=[x['dorm_ug']+x['dorm_grad'] for x in by]
text=f'''# 하교 시간 병목의 원인 보완:오전과 다른 구성

이 문서는 오전 전체 최대에서 확인한 낙성대 환승 기전을 화요일 오후에 그대로 적용하지 않도록 보완합니다. 완료된 모의 경로의 가중 조각을 합산했으며 실제 학생 추적이 아닙니다. 두 모형의 최대는 각각17:01:11.959와17:01:00.298로,각자 오후 최대 시점의 비교입니다.

|구성|요청 직전010854 → 최신122336(명 상당)|
|---|---:|
|전체 줄|{total0:.3f}→{total1:.3f}|
|서울대입구행 합계|{snu0:.3f}→{snu1:.3f}|
|서울대입구행 중 이전 버스에서 내린 수요|{prior[0]:.3f}→{prior[1]:.3f}|
|낙성대행 합계|{nak0:.3f}→{nak1:.3f}|
|학부·대학원 기숙사행 합계|{dorm0:.3f}→{dorm1:.3f}|

**최신안의 오후 줄 증가를 낙성대 환승 증가로 설명하면 틀립니다.** 낙성대행은 오히려 소폭 줄었고,서울대입구행과 기숙사행이 늘었습니다. 특히 서울대입구행 중 접근 버스를 이미 탔던 수요가3.59→17.84명 상당으로 늘었습니다. 앞의 버스를 빨리 탈 수 있는 접근 방식과 이후 환승 대기 미예견을 넓혀 적용한 전체 후보에서,법대가 설입행 환승 지점으로 더 사용되는 경로가 나타났습니다. 이는 모형 원장으로 확인한 구성 변화이며,상태 분리 한 기능의 독립 효과나 현실 학생의 인과효과로 해석하지 않습니다.

오전 전체 최대의 낙성대45.61명/환승42.99명과 이 오후 구성을 구분해야 합니다. 서로 다른 시간대의 원인을 섞어 수요 비율이나 정원을 조절하지 않았습니다. 현재 자료로는 실제 목적지별 환승 비율과 후속 대기 인지 범위를 식별하지 못해 최신안을 채택하지 않았습니다.

[목적지·직전 노선별 원장](afternoon-peak-causes.json),[재구성 방법과 검산](AFTERNOON_PEAK_CAUSES.md),[오후 최대·지속시간](AFTERNOON_BOTTLENECKS.md),[팀 전달본](START_HERE.md).
'''
out=ROOT/'AFTERNOON_CAUSE_ADDENDUM.md';assert not out.exists();out.write_text(text,encoding='utf8')
for href in re.findall(r'\]\(([^)]+)\)',text):assert (ROOT/href).exists()
names=['AFTERNOON_CAUSE_ADDENDUM.md','AFTERNOON_PEAK_CAUSES.md','afternoon-peak-causes.json']
out=ROOT/'TEAM_PACKAGE_SUPPLEMENT.json';assert not out.exists()
out.write_text(json.dumps({'created_at':datetime.now(timezone.utc).isoformat(),'supplements_existing_package':'TEAM_PACKAGE.json',
    'scope':'Tuesday afternoon composition checked separately from the morning whole-record maximum.',
    'document_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names},
    'new_simulations':0,'production_writes':False},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('AFTERNOON_CAUSE_ADDENDUM_READY',by,prior,flush=True)
