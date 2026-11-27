"""Explain residual all-recorded law peaks, without changing any model input."""
from pathlib import Path
from collections import Counter
import csv,gc,gzip,hashlib,json,math
ROOT=Path(__file__).resolve().parent;w=Path(json.loads((ROOT/'candidate.json').read_bytes())['path'])
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
f=read(w/'frozen/prepared_capacity44_pair.json.gz');dest=f['destination_keys']
plans={p[0]:p for ps in f['prepared']['plans'].values() for p in ps}
q=list(csv.DictReader((w/'grid-stop-queue-exposure.csv').open(encoding='utf-8-sig')))
v=read(w/'grid-validation.json')['results'];reports=[]
for day,node in [('월',47),('수',60)]:
    r=next(z for z in v if z['case']['day']==day and z['case']['scenario']=='regular')
    ref=next(z for z in q if z['case']==r['case']['case'] and int(z['node'])==node)
    at=float(ref['peak_seconds']);eng={'월':'mon','수':'wed'}[day]
    p=Path(r['source_directory'])/f'audit-regular-{eng}.json.gz'
    assert hashlib.sha256(p.read_bytes()).hexdigest()==r['audit_sha256']
    a=read(p);trips={t['id']:t for t in a['legs']};dests=Counter();arrivals=Counter();buildings=Counter();services=Counter();changes=Counter();mass=0.
    for z in a['wait_audit']:
        if z['node']!=node or not z['arrival']<=at<z['end']:continue
        t=trips[z['id']];source=plans[t['parent_id']];weight=z['weight'];mass+=weight
        d=dest[str(t['parent_id'])];dests[d]+=weight;buildings[source[1]]+=weight
        prior=[l for l in t['legs'] if l[0]==3 and l[2]<=z['arrival']+1e-7]
        arrivals['after_prior_ride' if prior else 'no_prior_ride']+=weight
        if prior:services[str(prior[-1][6])]+=weight
        changes['after_route_change' if any(h[0]<=z['arrival']+1e-7 for h in t['history']) else 'initial_plan']+=weight
    assert abs(mass-float(ref['maximum_queue']))<1e-5
    reports.append({'case':r['case'],'node':node,'ars':ref['ars'],'peak_kst':ref['peak_kst'],'queue_weight':mass,
        'destination_stock':dict(dests),'access':dict(arrivals),'previous_service_path_ids':dict(services),
        'initial_plan_or_changed':dict(changes),'source_building_weights':dict(buildings),'audit_sha256':r['audit_sha256']})
    del a,trips;gc.collect()
p=w/'morning-residual-diagnosis.json';assert not p.exists()
p.write_text(json.dumps({'scope':'Current fixed model peak decomposition, not observed queue or inferred real morning demand.',
    'cases':reports,'model_parameters_changed':False,'production_writes':False},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
s=['# 오전 법대 잔여 피크','','오후15~20시 개선만으로 모든 시간대의 법대 문제가 해결됐다고 볼 수 없어, 전체 기록의 큰 오전 피크 두 곳을 따로 추적했습니다.','',
    '|요일·ARS·시각|전체 줄|설입행|낙성대행|기숙사행|이전 버스 이용 후 합류|','|---|---:|---:|---:|---:|---:|']
for r in reports:
    d=r['destination_stock'];dorm=math.fsum(v for k,v in d.items() if k.startswith('dorm'))
    s.append(f"|{r['case']['day']}·{r['ars']}·{r['peak_kst']}|{r['queue_weight']:.2f}|{d.get('snu',0):.2f}|{d.get('nak',0):.2f}|{dorm:.2f}|{r['access'].get('after_prior_ride',0):.2f}|")
s+=['','이 표는 실제 인원 조사가 아니라 고정 모형의 대기 원장을 분해한 결과입니다. 목적지·이전 탑승·원래 출발 건물·초기 배정/경로 변경 구성을 JSON에 함께 남겼습니다.',
    '오전 법대의 실제 유입·승차·대기인원 관측이 없어 모의 피크가 현실적인지 검증하지 못했습니다. 기존 수업 종료 가중 수요는 각 학생의 당일 마지막 수업과 실제 귀가를 직접 추적한 자료가 아닙니다. 따라서 오전 수요를 임의로 줄이거나 40명에서 잘라내지 않았습니다.',
    '다음 확인은 같은 방향 정류장에서 11시 전후의 유입·실제 승차·차내 혼잡을 함께 보는 것입니다. 그 전에는 출발 수요 문제인지, 호환 노선 공급 문제인지, 다른 목적지 접근 경로 문제인지 단일 줄 크기만으로 단정하지 않습니다.','',
    '[수치와 구성 원장](morning-residual-diagnosis.json), [전체 시간대 점검](ALL_STOP_REVIEW.md), [최종 비교](FINAL_REVIEW.md).','']
p=w/'MORNING_RESIDUAL.md';assert not p.exists();p.write_text('\n'.join(s),encoding='utf8')
print('MORNING_RESIDUAL_COMPLETE',reports,flush=True)
