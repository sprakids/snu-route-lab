"""Inspect the remaining Wednesday afternoon law peak in the completed ledger."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json,math
ROOT=Path(__file__).resolve().parent;w=Path(json.loads((ROOT/'candidate.json').read_bytes())['path'])
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
f=read(w/'frozen/prepared_capacity44_pair.json.gz');dest=f['destination_keys'];routes=f['prepared']['routes']
parents={p[0]:p for ps in f['prepared']['plans'].values() for p in ps}
r=next(z for z in read(w/'grid-validation.json')['results'] if z['case']['day']=='수' and z['case']['scenario']=='regular')
law=next(z for z in read(w/'grid-law-transfer-metrics.json')['cases'] if z['case']['case']==r['case']['case'])
peak=next(z for z in law['law_profiles'] if z['node']==60);at=peak['peak_seconds']
p=Path(r['source_directory'])/'audit-regular-wed.json.gz';assert hashlib.sha256(p.read_bytes()).hexdigest()==r['audit_sha256']
a=read(p);trips={t['id']:t for t in a['legs']};dests=Counter();priorbydest=Counter();origins=Counter();changed=Counter();ages=[]
for v in a['wait_audit']:
    if v['node']!=60 or not v['arrival']<=at<v['end']:continue
    t=trips[v['id']];d=dest[str(t['parent_id'])];wt=v['weight'];dests[d]+=wt;origins[parents[t['parent_id']][1]]+=wt
    prior=[l for l in t['legs'] if l[0]==3 and l[2]<=v['arrival']+1e-7]
    if prior:priorbydest[d]+=wt
    changed['after_change' if any(h[0]<=v['arrival']+1e-7 for h in t['history']) else 'initial_plan']+=wt
    ages.append((at-v['arrival'],wt))
mass=math.fsum(dests.values());assert abs(mass-peak['maximum_queue'])<1e-5
events=[]
for e in a['events']:
    if e[1]!=60 or not at-600<=e[0]<=at+600:continue
    rid=e[11];events.append({'time':e[0],'route':rid,'route_name':routes.get(rid,{}).get('name',rid),
        'capacity':e[3],'known_onboard_before':e[4],'alighting':e[5],
        'model_free_before_boarding':e[3]-e[4]+e[5],'boarded':e[6]})
result={'scope':'Fixed Wednesday regular15-20 law peak, not field observation or actual external load.',
    'case':r['case'],'node':60,'ars':'21298','peak':peak,'destination_stock':dict(dests),'prior_ride_by_destination':dict(priorbydest),
    'initial_or_changed':dict(changed),'origin_building_stock':dict(origins),
    'standing_age_at_peak_mean_minutes':math.fsum(sec*wt for sec,wt in ages)/mass/60,
    'standing_age_at_peak_max_minutes':max(sec for sec,wt in ages)/60,'bus_events_plus_minus10min':events,
    'source_audit_sha256':r['audit_sha256'],'production_writes':False}
p=w/'wednesday-residual-diagnosis.json';assert not p.exists();p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
clock=lambda t:f'{int(t//3600):02}:{int(t%3600//60):02}:{t%60:05.2f}'
s=['# 수요일 오후 법대의 남은 피크','',
    f"기본 운행 수요일 {clock(at)}의 법대·사회대입구(21298) 줄은 {mass:.2f}명 상당입니다. 15~20시 40명 초과 누적 시간은 {peak['minutes_above40']:.2f}분, 최장 연속 초과는 {peak['longest_spell_above40_minutes']:.2f}분입니다. 실제 현장 관측값은 아닙니다.",'',
    '|목적지|그 시점 줄|그중 이전 버스 이용|','|---|---:|---:|']
for d,v in dests.items():s.append(f'|{d}|{v:.2f}|{priorbydest[d]:.2f}|')
s+=['',f"피크 순간까지 이미 기다린 시간은 가중 평균 {result['standing_age_at_peak_mean_minutes']:.2f}분, 최대 {result['standing_age_at_peak_max_minutes']:.2f}분입니다. 이것은 최종 승차까지의 총 대기시간과 다릅니다.",
    '따라서 큰 줄과 20분 초과 대기는 같은 지표로 취급하지 않습니다. 기존 표에서 해당 승차지의 완료·경로 변경 대기를 따로 확인해야 합니다.','',
    '## 피크 전후 10분의 실제 모형 버스 사건','',
    '차내 인원과 잔여 자리는 모형이 아는 교내 승객 기준입니다. 측정된 외부 승객 인원이 아니며, 노선별 호환 목적지가 달라 빈자리를 모두 합쳐 같은 학생의 승차 기회로 보지 않습니다.','',
    '|시각|노선|정원|모형 잔여 자리|승차 가중량|','|---|---|---:|---:|---:|']
for e in events:s.append(f"|{clock(e['time'])}|{e['route_name']}|{e['capacity']:.0f}|{e['model_free_before_boarding']:.2f}|{e['boarded']:.2f}|")
s+=['','목적지별 유입과 이용 가능한 버스가 같은 시각에 맞지 않으면 전체 줄이 일시적으로 커질 수 있습니다. 이 원장은 그 구성과 운행 사건을 확인하기 위한 자료입니다. 실제 법대 유입·승차·차내 혼잡이 없어 어느 쪽을 얼마나 보정할지는 식별하지 못했습니다. 수요 축소나 추가 차량으로 숫자를 맞추지 않았습니다.','',
    '[계산 원장](wednesday-residual-diagnosis.json), [전 시간대 점검](ALL_STOP_REVIEW.md), [최종 비교](FINAL_REVIEW.md).','']
p=w/'WEDNESDAY_RESIDUAL.md';assert not p.exists();p.write_text('\n'.join(s),encoding='utf8')
print('WEDNESDAY_RESIDUAL_COMPLETE',result,flush=True)
