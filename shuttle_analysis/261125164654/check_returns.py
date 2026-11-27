"""Score complete held-out dispatch groups against bounded operator returns."""
import csv
import gzip
import json
from collections import defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'261124160531'

def load(path):
    with (gzip.open if path.suffix=='.gz' else open)(path,'rt',encoding='utf8') as f:
        return json.load(f)

def interval_error(value,bounds):
    return max(bounds[0]-value,value-bounds[1],0)

def compare():
    raw=load(HERE/'validation_samples.json')
    hot=load(BASE/'viewer-data/common.json.gz')['hot_nodes']
    output=[]
    for day,did in [('2026-11-23','mon'),('2026-11-24','tue')]:
        for service in ('regular','peak'):
            key=f'{service}-{did}'
            old=load(BASE/'viewer-data'/f'{key}.json.gz')['door_windows']
            candidate=load(HERE/'runs'/'combined'/key/f'{key}.json.gz')['door_windows']
            by_vid={v:(op,dep) for n,v,op,dep,cap in candidate}
            for route,node in [('41841',hot['admin_snu']),('41843',hot['admin_daehak'])]:
                groups=defaultdict(list)
                for n,v,op,dep,cap in old:
                    if n==node:
                        groups[dep].append((v,op))
                observed=defaultdict(list)
                for record in raw[day]['visits']:
                    if record['route']!=route:
                        continue
                    lo,hi=record['departure']
                    nearest=lambda t:min(groups,key=lambda dep:abs(t-dep))
                    slot=nearest(lo)
                    if not 11*3600+1200<=slot<19*3600 or slot!=nearest(hi):
                        continue
                    observed[slot].append(record)
                for slot,records in observed.items():
                    vehicles=groups[slot]
                    # A partial pair cannot tell us when the first bus opened.
                    # Classify extended depot parking the same way on both dates.
                    if len(records)!=len(vehicles) or any(
                            (sum(r['departure'])-sum(r['arrival']))/2>1800 for r in records):
                        continue
                    bracket=[min(r['arrival'][i] for r in records) for i in (0,1)]
                    before=min(op for vid,op in vehicles)
                    after=min(by_vid[v][0] for v,op in vehicles)
                    output.append(dict(day=day,service=service,route=route,planned_departure_s=slot,
                           vehicles=len(vehicles),observed_arrival_low=bracket[0],observed_arrival_high=bracket[1],
                           old_open_s=before,new_open_s=after,
                           old_error_s=interval_error(before,bracket),new_error_s=interval_error(after,bracket)))
    with (HERE/'별도날짜_복귀검증.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)
    return output

if __name__=='__main__':
    from statistics import mean
    rows=compare()
    for s in ('regular','peak'):
        for route in ('41841','41843'):
            matched=[r for r in rows if r['service']==s and r['route']==route]
            if matched:
                print(s,route,len(matched),*[round(mean(r[k] for r in matched)/60,2) for k in ('old_error_s','new_error_s')])
