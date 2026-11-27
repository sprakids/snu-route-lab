"""Derive 30-minute arrival-cohort charts from full preserved wait records.

This does not run the vehicle model or alter any existing replay dataset.
"""
from collections import defaultdict
from pathlib import Path
import gzip,hashlib,json,math
import capacity_model as base

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'public/data/half_hour_v1'
WORK=ROOT/'chart_aggregation_2026-11-08'
INTERVAL=1800
BINS=list(range(base.START//INTERVAL*INTERVAL,base.END,INTERVAL))
FOLDERS={'capacity_v3':'capacity_model/speed_40_65','capacity_v4':'adaptive_model','capacity_v5':'city_bus_model_2026-11-08'}


def normalize(row):
    node,a,b,w,denied,unserved,uid=row[:7]
    outcome=row[7] if len(row)>7 else ('unserved' if unserved else 'boarded')
    # Old v3/v4 use END+1 as a display sentinel. Censor statistical exposure
    # at the actual observation boundary, matching the corrected v5 method.
    if unserved:b=min(b,base.END)
    assert outcome in ('boarded','switched','unserved') and w>=0 and b>=a
    return node,a,b,w,denied,unserved,uid,outcome


def stats(rows):
    boarded=[r for r in rows if r[7]=='boarded']
    total=math.fsum(r[3] for r in rows);served=math.fsum(r[3] for r in boarded)
    denied=math.fsum(r[3] for r in rows if r[4]>=0)
    return {'arrival_weight':total,'served_weight':served,
        'unserved_weight':math.fsum(r[3] for r in rows if r[7]=='unserved'),
        'switched_weight':math.fsum(r[3] for r in rows if r[7]=='switched'),
        'mean_wait_min':math.fsum((r[2]-r[1])*r[3] for r in boarded)/served/60 if served else None,
        'p90_wait_min':base.percentile([((r[2]-r[1])/60,r[3]) for r in boarded],.9),
        'mean_queue_exposure_min':math.fsum((r[2]-r[1])*r[3] for r in rows)/total/60 if total else None,
        'denied_weight':denied,'denied_share':denied/total if total else None}


def aggregate(rows,count):
    groups=defaultdict(list)
    for row in rows:
        r=normalize(row)
        if base.START<=r[1]<base.END:
            assert 0<=r[0]<count
            groups[r[0],int(r[1]//INTERVAL)*INTERVAL].append(r)
    return {str(n):{str(t):stats(groups[n,t]) for t in BINS} for n in range(count)}


def main():
    OUT.mkdir(parents=True,exist_ok=True);WORK.mkdir(exist_ok=True)
    reports=[];cells=0
    for dataset,folder in FOLDERS.items():
        charts=base.read(ROOT/f'public/data/{dataset}/charts.json')
        sources=[];scenarios={}
        for scenario in base.SCENARIOS:
            scenarios[scenario]={}
            for day in base.DAYS.values():
                source=ROOT/f'{folder}/audit-{scenario}-{day}.json.gz'
                audit=json.loads(gzip.decompress(source.read_bytes()))
                original=charts['scenarios'][scenario][day]['hourly']
                groups=aggregate(audit['waits'],len(original));scenarios[scenario][day]=groups
                # Recombining half-hours must exactly recover hourly cohort
                # weights and boarded-only means. Quantiles are never averaged.
                for node,hours in original.items():
                    for h,row in hours.items():
                        pieces=[groups[node][str(t)] for t in BINS if t//3600==int(h)]
                        for field in ('arrival_weight','served_weight','unserved_weight','switched_weight','denied_weight'):
                            assert abs(math.fsum(p[field] for p in pieces)-row.get(field,0))<1e-5,(dataset,scenario,day,node,h,field)
                        served=math.fsum(p['served_weight'] for p in pieces)
                        if served:
                            mean=math.fsum(p['mean_wait_min']*p['served_weight'] for p in pieces if p['served_weight'])/served
                            assert abs(mean-row['mean_wait_min'])<1e-7
                        else:assert row['mean_wait_min'] is None
                        cells+=len(pieces)
                sources.append({'path':source.relative_to(ROOT).as_posix(),'sha256':base.sha(source)})
        data={'schema_version':1,'interval_seconds':INTERVAL,'start_second':base.START,'end_second':base.END,
            'bin_starts':BINS,'grouping':'stop arrival, half-open bins [start,end)',
            'mean_denominator':'boarded weighted flows; switchers and unserved are separate',
            'original_dataset':dataset,'scenarios':scenarios,'audit_sources':sources}
        base.OUT=OUT;base.public(dataset+'.json',data)
        reports.append({'dataset':dataset,'runs':10,'nodes':len(original),'bins':len(BINS),'sources':sources,
            'json_sha256':base.sha(OUT/(dataset+'.json'))})
    result={'status':'PASS','interval_seconds':INTERVAL,'datasets':reports,'runs':30,
        'half_hour_cells_reconciled_to_hourly':cells,'simulation_recomputed':False,
        'original_replay_datasets_changed':False,'legacy_hourly_reference_resampled':False,
        'builder_sha256':base.sha(Path(__file__))}
    base.save(WORK/'verification.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('datasets','builder_sha256')}))


if __name__=='__main__':main()
