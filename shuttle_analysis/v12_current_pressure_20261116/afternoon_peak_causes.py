"""Reconstruct afternoon queues from completed fragments and their prior rides."""
from pathlib import Path
from collections import Counter
import csv,gzip,hashlib,json,math
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
profiles=list(csv.DictReader((ROOT/'afternoon-law-before-after.csv').open(encoding='utf-8-sig')))
frozen=read(ANALYSIS/'261116122336/frozen/prepared_capacity44_pair.json.gz');dest=frozen['destination_keys']
output=[]
for model,fn in [('261116010854','grid-validation.json'),('261116122336','pilot-validation.json')]:
    r=next(x for x in read(ANALYSIS/model/fn)['results'] if x['case']['day']=='화' and x['case']['scenario']=='regular' and not x['case']['case'].startswith('ablation'))
    p=Path(r['source_directory'])/'audit-regular-tue.json.gz';assert sha(p)==r['audit_sha256'];a=read(p)
    pro=next(x for x in profiles if x['model']==model and x['weekday']=='화' and x['node']=='60')
    at=float(pro['peak_seconds']);vehicles={v['id']:v for v in a['vehicles']};groups=Counter();matched=0.
    for trip in a['legs']:
        for index,leg in enumerate(trip['legs']):
            if leg[0]!=1 or leg[4]!=60 or not leg[1]<=at<leg[2]:continue
            d=dest[str(trip['parent_id'])];weight=trip['weight'];matched+=weight
            prior=[x for x in trip['legs'][:index] if x[0]==3]
            key=(d,'after_prior_bus' if prior else 'no_prior_bus',vehicles[prior[-1][6]]['rid'] if prior else '')
            groups[key]+=weight
    assert abs(matched-float(pro['maximum_queue']))<1e-5,(matched,pro)
    nak=math.fsum(v for k,v in groups.items() if k[0]=='nak')
    nak_transfer=math.fsum(v for k,v in groups.items() if k[0]=='nak' and k[1]=='after_prior_bus')
    output.append({'model':model,'case':r['case']['case'],'node':60,'ars':21298,'afternoon_peak_kst':pro['peak_kst'],
        'matched_queue_weight':matched,'nak_queue_weight':nak,'nak_after_prior_bus_weight':nak_transfer,
        'destination_and_prior_ride':[{'destination':k[0],'approach':k[1],'prior_route':k[2],'weight':v} for k,v in groups.most_common()],
        'audit_sha256':r['audit_sha256']})
out=ROOT/'afternoon-peak-causes.json';assert not out.exists()
out.write_text(json.dumps({'scope':'Completed model fragments at Tuesday afternoon law21298 queue maxima. Reconstructs weights, not observed student trajectories.','cases':output,'production_writes':False},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
text=['# 화요일 하교 법대21298의 환승 수요 확인','',
      '오전 전체 최대의 원인을 오후에 그대로 적용하지 않도록,15~20시 최대 줄의 구성원을 완료된 모의 경로 조각으로 다시 합산했습니다. 원장 최대와 재구성 합의 차이는1e-5명 상당 이내입니다. 실제 학생 추적 자료가 아닙니다.','',
      '|모형|오후 최대 시각|전체 줄|낙성대행|낙성대행 중 이전 버스 승차 있음|','|---|---|---:|---:|---:|']
for r in output:text.append(f"|{r['model']}|{r['afternoon_peak_kst']}|{r['matched_queue_weight']:.3f}|{r['nak_queue_weight']:.3f}|{r['nak_after_prior_bus_weight']:.3f}|")
text+=['',
       '목적지와 직전 노선별 세부 구성은[JSON 원장](afternoon-peak-causes.json)에 남겼습니다. 모형에서 환승 접근 수요가 집중되는 기전과 실제로 그만큼 환승하는지는 구분해야 합니다. 실제 목적지별 하차·환승과 차량 여석을 측정하지 않은 상태에서 비율을 바꾸어40명에 맞추지 않았습니다.','',
       '[오후 최대·지속시간 비교](AFTERNOON_BOTTLENECKS.md),[팀 전달본](START_HERE.md),[가정·출처](SOURCES_AND_ASSUMPTIONS.md).','']
out=ROOT/'AFTERNOON_PEAK_CAUSES.md';assert not out.exists();out.write_text('\n'.join(text),encoding='utf8')
print('AFTERNOON_PEAK_CAUSES_COMPLETE',json.dumps([{k:v for k,v in r.items() if k!='destination_and_prior_ride'} for r in output],ensure_ascii=False),flush=True)
