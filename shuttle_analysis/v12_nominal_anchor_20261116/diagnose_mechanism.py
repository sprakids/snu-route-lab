"""Post-run mass balances, destination-specific law peaks and wait mechanisms."""
from pathlib import Path
from collections import Counter
import csv,gc,gzip,hashlib,json,math,time
ROOT=Path(__file__).resolve().parent;A=ROOT.parent;w=Path(json.loads((ROOT/'candidate.json').read_bytes())['path']);P=A/'261116153200'
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,d):
    assert not p.exists(),p
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
deadline=time.monotonic()+5400
while not (w/'pilot-law-transfer-metrics.json').exists():
    assert not list((w/'runs').glob('*/attempt_01/failure.json'))
    assert time.monotonic()<deadline
    time.sleep(10)
f=read(w/'frozen/prepared_capacity44_pair.json.gz');dest=f['destination_keys'];nodes=f['prepared']['common']['nodes']
sources={p[0]:p for ps in f['prepared']['plans'].values() for p in ps}
allrows=[];gate=[]
for model in [P,w]:
    law=read(model/'pilot-law-transfer-metrics.json')['cases']
    rows=[r for r in read(model/'pilot-validation.json')['results'] if not r['case']['case'].startswith('ablation')]
    for r in rows:
        c=r['case'];did={'월':'mon','화':'tue'}[c['day']];path=Path(r['source_directory'])/f'audit-regular-{did}.json.gz'
        assert sha(path)==r['audit_sha256'];a=read(path);trips={t['id']:t for t in a['legs']}
        lm=next(z for z in law if z['case']['case']==c['case']);peaks=[]
        for z in lm['law_profiles']:
            at=z['peak_seconds'];counter=Counter()
            for v in a['wait_audit']:
                if v['node']!=z['node'] or not v['arrival']<=at<v['end']:continue
                t=trips[v['id']];d=dest[str(v['parent_id'])]
                prior=[l for l in t['legs'] if l[0]==3 and l[2]<=v['arrival']+1e-7]
                counter[d]+=v['weight']
                if d=='snu' and prior:counter['snu_prior_ride']+=v['weight'];counter['snu_prior_ride_'+str(prior[-1][6])]+=v['weight']
            total=math.fsum(v for k,v in counter.items() if k in set(dest.values()))
            assert abs(total-z['maximum_queue'])<1e-5,(total,z)
            peaks.append({**z,'stop':nodes[z['node']]['name'],'ars':nodes[z['node']].get('ars'),'destination_stock':dict(counter)})
        raw=Counter();by_node=Counter();max_visit=None
        for v in a['wait_audit']:
            sec=v['end']-v['arrival'];t=trips[v['id']];personal=t['student_patience_seconds']
            if sec>1200+1e-7:
                raw['over20']+=v['weight'];by_node[v['node']]+=v['weight']
                raw['within_personal' if sec<=personal+1e-7 else 'beyond_personal']+=v['weight']
                raw['over20_'+v['outcome']]+=v['weight']
                if sec>personal+1e-7:raw['beyond_personal_'+('gate' if v['node']==62 else 'elsewhere')]+=v['weight']
            if max_visit is None or sec>max_visit['seconds']:
                max_visit={'seconds':sec,'personal_seconds':personal,'node':v['node'],'weight':v['weight'],'outcome':v['outcome'],
                    'entry_forecast':v.get('entry_forecast'),'full_passes_seen':v.get('full_passes_seen')}
        allrows.append({'model':model.name,'day':c['day'],'audit_sha256':r['audit_sha256'],
            'law_afternoon_peak_stock':peaks,'raw_visit_wait_categories':dict(raw),'raw_visit_scope':'Raw visit weights, not merged canonical episodes or unique students.',
            'largest_raw_wait':max_visit,'raw_over20_by_node':dict(by_node)})
        if c['day']=='월':
            start,end,minute=59400.,61440.,61380.;visits=[v for v in a['wait_audit'] if v['node']==62];flow=Counter();cohort=Counter()
            for v in visits:
                wt=v['weight'];arrival=v['arrival'];finish=v['end']
                if arrival<=start<finish:flow['queue_at_16_30']+=wt
                if arrival<=end<finish:flow['queue_at_17_04']+=wt
                if start<arrival<=end:
                    flow['arrivals']+=wt;t=trips[v['id']];source=sources[t['parent_id']]
                    mode='walk' if not source[6] else 'shuttle' if source[6][0]['rid'].startswith('shuttle') else 'city'
                    cohort[mode]+=wt
                    flow['arrivals_after_route_change' if any(h[0]<=arrival+1e-7 for h in t['history']) else 'arrivals_initial_plan']+=wt
                if start<finish<=end:flow['exits']+=wt;flow['exit_'+v['outcome']]+=wt
                flow['minute_mean_17_03']+=max(0.,min(finish,minute+60)-max(arrival,minute))/60*wt
            balance=flow['queue_at_16_30']+flow['arrivals']-flow['exits']-flow['queue_at_17_04'];assert abs(balance)<1e-6
            buses=[{'time':e[0],'route':e[11],'vehicle':e[2],'capacity':e[3],'known_onboard_before':e[4],'alighting':e[5],
                    'model_free_before_gate':e[3]-e[4]+e[5],'boarded':e[6]} for e in a['events'] if e[1]==62 and start<e[0]<=end]
            gate.append({'model':model.name,'day':c['day'],'window':[start,end],'flow':dict(flow),'arrival_source_modes':dict(cohort),
                'mass_balance_error':balance,'buses':buses,'offered_seat_events':math.fsum(b['model_free_before_gate'] for b in buses),
                'scope':'Known simulated occupancy; seat opportunities and arrivals are not unique passengers or measured external loads.'})
        del a,trips;gc.collect()
keys=lambda g:[(b['time'],b['route'],b['vehicle'],b['capacity']) for b in g['buses']]
assert keys(gate[0])==keys(gate[1])
old=list(csv.DictReader((P/'pilot-all-recorded-stops.csv').open(encoding='utf-8-sig')))
new=list(csv.DictReader((w/'pilot-all-recorded-stops.csv').open(encoding='utf-8-sig')))
old={(r['weekday'],r['node']):r for r in old if not r['case'].startswith('ablation')};deltas=[]
for r in new:
    if r['case'].startswith('ablation'):continue
    o=old[(r['weekday'],r['node'])];delta=float(r['over20_episode_weight'])-float(o['over20_episode_weight'])
    if abs(delta)>1e-7:deltas.append({'day':r['weekday'],'node':int(r['node']),'stop':r['stop'],'before':float(o['over20_episode_weight']),
        'after':float(r['over20_episode_weight']),'delta':delta})
deltas.sort(key=lambda r:r['delta'],reverse=True)
save(w/'mechanism-diagnosis.json',{'scope':'Post-hoc diagnosis of the already executed fixed pilot, no tuning or new field outcomes.',
    'models':allrows,'gate_mass_balances':gate,'exogenous_gate_buses_unchanged':True,'canonical_stop_over20_changes':deltas,'production_writes':False})
s=['# 法대·정문·긴 대기 원인 원장','','같은 월·화 기본 운행에서 부모 G와 배차 인지 후보를 비교했습니다. 운영 숫자 조정이나 새 실측을 사용한 분석이 아닙니다.','',
    '## 정문: 수요 유입과 승차로 나눈 비교','','16:30 직후부터 17:04까지의 질량 보존을 확인했습니다. 그 사이 버스의 시각·노선·차량·정원은 전후 동일합니다.','',
    '|모형|16:30 줄|누적 유입|누적 이탈|17:04 줄|17:03 분 평균|','|---|---:|---:|---:|---:|---:|']
for g in gate:
    d=g['flow'];s.append(f"|{g['model']}|{d['queue_at_16_30']:.3f}|{d['arrivals']:.3f}|{d['exits']:.3f}|{d['queue_at_17_04']:.3f}|{d['minute_mean_17_03']:.3f}|")
s+=['','이 표는 정문 예측 변화가 어디서 생겼는지 분해합니다. 관측 줄 33~39명 한 건만으로 실제 유입과 실제 잔여 좌석을 각각 식별할 수는 없습니다. 외부 승객 수를 임의로 더하지 않았습니다.','',
    '## 법대 오후 최대 줄의 목적지 구성','','아래는 각 경우 **자신의 최대 시각**에 남아 있는 인원입니다. 누적 도착량과 구분합니다.','',
    '|모형·요일·ARS|최대 줄|설입행|그중 이전 버스 탑승|낙성대행|기숙사행|','|---|---:|---:|---:|---:|---:|']
for r in allrows:
    for z in r['law_afternoon_peak_stock']:
        d=z['destination_stock'];dorm=math.fsum(v for k,v in d.items() if k.startswith('dorm'))
        s.append(f"|{r['model']}·{r['day']}·{z['ars']}|{z['maximum_queue']:.3f}|{d.get('snu',0):.3f}|{d.get('snu_prior_ride',0):.3f}|{d.get('nak',0):.3f}|{dorm:.3f}|")
s+=['','## 20분 초과와 개인 기준 초과','','이 표는 연속 대기를 합친 표와 달리 원시 대기 방문을 분류합니다. 같은 학생의 여러 방문이나 분할된 가중 입자가 포함되므로 고유 인원으로 읽지 않습니다.','',
    '|모형·요일|20분 초과 방문|개인 기준 이내|개인 기준도 초과|가장 긴 방문, 분|그 개인 기준, 분|','|---|---:|---:|---:|---:|---:|']
for r in allrows:
    d=r['raw_visit_wait_categories'];m=r['largest_raw_wait']
    s.append(f"|{r['model']}·{r['day']}|{d.get('over20',0):.3f}|{d.get('within_personal',0):.3f}|{d.get('beyond_personal',0):.3f}|{m['seconds']/60:.3f}|{m['personal_seconds']/60:.3f}|")
s+=['','개인 기준 이내의 긴 방문은 기존 이질적 인내 가정에서 생깁니다. 개인 기준을 넘는 방문에는 검토 후에도 대안이 불리해 남는 경우와 새 유입·만차로 예측이 달라지는 경우가 있을 수 있으므로, 줄을 강제로 제거하지 않고 개별 예측·만차 이력을 함께 남겼습니다.','',
    '## 정류장별 악화 및 개선','','아래는 연속 대기를 합친 20분 초과 가중 구간의 변화가 큰 곳입니다. 전체 정류장 결과는 CSV에 있습니다.','',
    '|요일·정류장|전 → 후|증감|','|---|---:|---:|']
for r in [*deltas[:8],*deltas[-8:]]:s.append(f"|{r['day']}·{r['stop']}({r['node']})|{r['before']:.3f} → {r['after']:.3f}|{r['delta']:+.3f}|")
s+=['','[계산 원장](mechanism-diagnosis.json), [결과 본문](RESULTS.md).','']
out=w/'MECHANISM_DIAGNOSIS.md';assert not out.exists();out.write_text('\n'.join(s).replace('# 法대','# 법대'),encoding='utf8')
print('MECHANISM_DIAGNOSIS_COMPLETE',w.name,flush=True)
