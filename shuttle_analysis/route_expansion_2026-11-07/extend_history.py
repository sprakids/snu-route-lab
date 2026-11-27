"""Reuse immutable cached citywide T-data pages; no network and no holdout fitting."""
from pathlib import Path
from collections import defaultdict,Counter
from datetime import datetime
import json,gzip,hashlib,math
ROOT=Path(__file__).resolve().parent
APP=ROOT.parent/'app'
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
base=load(APP/'data/weekday_history.json')
routes=load(ROOT/'prepared_routes.json')['routes'];ids={r['id'] for r in routes}
segments=sorted([(r['id'],str(a['seq']),a['id'],b['id']) for r in routes for a,b in zip(r['stops'],r['stops'][1:])],key=lambda s:(s[0],int(s[1])))
lookup={s:i for i,s in enumerate(segments)};cells=defaultdict(dict);selected={};inputs=[]
for date in base['history_dates']:
    directory=ROOT.parent/'tdata_calibration_2026-11-07/collected'/date
    receipt=load(directory/'collection_receipt.json');assert receipt['status']=='complete' and receipt['end_proved_by_empty_page']
    records=[]
    for file in sorted(directory.glob('page_*.json.gz')):
        raw=file.read_bytes();records.extend(r for r in json.loads(gzip.decompress(raw)) if str(r['routeId']) in ids)
        inputs.append({'file':str(file.relative_to(ROOT.parent)),'sha256':hashlib.sha256(raw).hexdigest()})
    selected[date]=records
    for r in records:
        ident=(str(r['routeId']),str(int(r['staSn'])),str(r['fromStaId']),str(r['toStaId']))
        if ident not in lookup:continue
        for hour in range(12,23):
            value=r.get(f'a18SumLoadPsngNum{hour:02d}h')
            if value is not None and math.isfinite(float(value)) and float(value)>=0:cells[(lookup[ident],hour)][date]=float(value)
    print(date,'cached new-route segments',len(records),flush=True)
profiles=[]
for (index,hour),values in sorted(cells.items()):
    mean=math.fsum(values.values())/len(values);predictions=[];counts=[]
    for weekday in range(5):
        items=[v for date,v in values.items() if datetime.strptime(date,'%Y%m%d').weekday()==weekday]
        n=len(items);weekday_mean=math.fsum(items)/n if n else mean
        predictions.append(round(mean+n/(n+base['shrinkage_k'])*(weekday_mean-mean),6));counts.append(n)
    profiles.append([index,hour,round(mean,6),predictions,counts])
payload={'schema':'snu_weekday_history_extension_v1','model_id':'weekday-history-eight-20261107',
         'base_model_id':base['model_id'],'history_dates':base['history_dates'],'shrinkage_k':base['shrinkage_k'],
         'segments':[list(s) for s in segments],'profiles':profiles,'route_names':{r['id']:r['name'] for r in routes},
         'method':'same weekday shrinkage to pooled mean; same frozen fit dates; no new coefficient selection or holdout use',
         'network_requests':0,'unit':base['unit'],'interpretation':base['interpretation']}
dump(APP/'data/weekday_history_extension.json',payload)
dump(ROOT/'cached_history_new_routes.json',selected)
dump(ROOT/'history_extension_verification.json',{'network_requests':0,'fit_dates':base['history_dates'],
     'holdout_dates_used':False,'segments':len(segments),'profiles':len(profiles),'covered_segments':len({r[0] for r in profiles}),
     'missing_segments':[list(s) for i,s in enumerate(segments) if i not in {r[0] for r in profiles}],
     'route_segment_counts':dict(Counter(s[0] for s in segments)),'inputs':inputs})
print(json.dumps({'new_segments':len(segments),'covered_segments':len({r[0] for r in profiles}),'profiles':len(profiles),'network_requests':0}))
