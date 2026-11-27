"""Separate afternoon congestion from early warm-up peaks, without altering runs."""
from pathlib import Path
from collections import defaultdict,Counter
import csv,gzip,hashlib,json,math
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
start,end=15*3600,20*3600;result=[]
for model,file in [('261116010854','grid-validation.json'),('261116122336','pilot-validation.json')]:
    w=ANALYSIS/model
    for r in read(w/file)['results']:
        c=r['case']
        if c['scenario']!='regular' or c['day'] not in ('월','화') or c['case'].startswith('ablation'):continue
        path=Path(r['source_directory'])/f"audit-regular-{'mon' if c['day']=='월' else 'tue'}.json.gz"
        assert sha(path)==r['audit_sha256'];a=read(path);events=defaultdict(Counter)
        for v in a['wait_audit']:
            if v['node'] not in (47,60):continue
            events[v['node']][v['arrival']]+=v['weight'];events[v['node']][v['end']]-=v['weight']
        for node in [47,60]:
            changes=sorted(events[node].items());q=mx=peak=above=run=longest=0.
            for i,(at,delta) in enumerate(changes):
                q+=delta;stop=changes[i+1][0] if i+1<len(changes) else at
                begin,finish=max(at,start),min(stop,end)
                if finish-begin<=1e-7:continue
                if q>mx:mx=q;peak=begin
                if q>40+1e-7:above+=finish-begin;run+=finish-begin;longest=max(longest,run)
                else:run=0.
            result.append({'model':model,'case':c['case'],'weekday':c['day'],'node':node,'ars':21270 if node==47 else 21298,
                'window_start':'15:00','window_end':'20:00','maximum_queue':mx,'peak_seconds':peak,
                'peak_kst':f'{int(peak//3600):02}:{int(peak%3600//60):02}:{peak%60:06.3f}',
                'minutes_above40':above/60,'longest_spell_above40_minutes':longest/60,'audit_sha256':r['audit_sha256']})
out=ROOT/'afternoon-law-before-after.csv';assert not out.exists()
with out.open('x',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,list(result[0]));writer.writeheader();writer.writerows(result)
text=['# 하교 시간 법대·사회대입구 병목:15:00~20:00','',
      '월·화 기본배차의 요청 직전010854와 최신122336을 같은 오후 시간 범위에서 비교합니다. 오전11시 부근에 발생한 전체 기록 최대와 구분하기 위한 분석입니다.40명은 회상 기준이며 실제 상한으로 적용하지 않았습니다.','',
      '|요일|ARS|최대 줄 전→후(명 상당)|최대 시각 전→후|40명 초과 누적 전→후(분)|최장 연속 초과 전→후(분)|',
      '|---|---|---:|---|---:|---:|']
for new in result:
    if new['model']!='261116122336':continue
    old=next(r for r in result if r['model']=='261116010854' and r['weekday']==new['weekday'] and r['node']==new['node'])
    text.append(f"|{new['weekday']}|{new['ars']}|{old['maximum_queue']:.3f}→{new['maximum_queue']:.3f}|{old['peak_kst']}→{new['peak_kst']}|{old['minutes_above40']:.3f}→{new['minutes_above40']:.3f}|{old['longest_spell_above40_minutes']:.3f}→{new['longest_spell_above40_minutes']:.3f}|")
text+=['','특정 방향·요일만 좋아진 수치를 전체 해결로 해석하지 않습니다. 초기 접근편에서 내려 환승하는 모의 수요가 모이는 기전은 확인했지만,실제 목적지별 환승 비율과 차량 여석을 새로 측정한 결과는 아닙니다.','',
       '[원시 수치와 출처 해시](afternoon-law-before-after.csv),[최신 월·화 전체 결과](LATEST_PILOT_RESULTS.md),[전요일·모든 비교안](FINAL_REVIEW.md),[자료·가정·출처](SOURCES_AND_ASSUMPTIONS.md).','']
out=ROOT/'AFTERNOON_BOTTLENECKS.md';assert not out.exists();out.write_text('\n'.join(text),encoding='utf8')
print('AFTERNOON_BOTTLENECKS_COMPLETE',json.dumps(result,ensure_ascii=False),flush=True)
