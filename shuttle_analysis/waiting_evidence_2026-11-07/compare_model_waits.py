"""Reaggregate preserved full capacity_v3 audit waits; no model rerun."""
import csv
import gzip
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
VIEWER=ROOT.parent/'simulation_viewer_2026-11-07'
PUBLIC=VIEWER/'public/data/capacity_v3'
AUDIT=VIEWER/'capacity_model/speed_40_65'
COMMON=json.loads((PUBLIC/'common.json').read_text(encoding='utf-8'))
HOT=COMMON['hot_nodes']
DAYS={'mon':'월','tue':'화','wed':'수','thu':'목','fri':'금'}

def summarize(waits):
    total=sum(x[3] for x in waits)
    served=[x for x in waits if not x[5]]
    sw=sum(x[3] for x in served)
    mw=sum((x[2]-x[1])*x[3]/60 for x in served)/sw if sw else None
    p90=None
    cum=0
    for x in sorted(served,key=lambda x:x[2]-x[1]):
        cum+=x[3]
        if cum>=sw*.9:
            p90=(x[2]-x[1])/60
            break
    return dict(arrival_weight=total,served_weight=sw,unserved_weight=sum(x[3] for x in waits if x[5]),
        mean_wait_min=mw,p90_wait_min=p90,
        served_wait_ge10_pct=100*sum(x[3] for x in served if x[2]-x[1]>=600)/sw if sw else None,
        served_wait_ge20_pct=100*sum(x[3] for x in served if x[2]-x[1]>=1200)/sw if sw else None,
        denied_at_least_once_pct=100*sum(x[3] for x in waits if x[4]>=0)/total if total else None)

def write_csv(name,rows):
    with (ROOT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    hourly=[];windows=[];pooled={};checks=[];manifest=[]
    for scenario in ['regular','peak']:
        pooled[scenario]=[]
        for day,ko in DAYS.items():
            path=AUDIT/f'audit-{scenario}-{day}.json.gz'
            raw=path.read_bytes(); d=json.loads(gzip.decompress(raw)); waits=d['waits']
            manifest.append(dict(path=str(path.relative_to(ROOT.parent)),sha256=hashlib.sha256(raw).hexdigest()))
            public=json.loads((PUBLIC/f'{scenario}-{day}.json').read_text(encoding='utf-8'))
            pooled[scenario].extend(waits)
            for stop,idx in HOT.items():
                for h in range(11,24):
                    lo=max(h*3600,COMMON['start_second']);hi=min((h+1)*3600,COMMON['end_second'])
                    v=summarize([x for x in waits if x[0]==idx and lo<=x[1]<hi])
                    hourly.append(dict(scenario=scenario,weekday=ko,stop=stop,label=COMMON['nodes'][idx]['label'],arrival_hour=h,**v))
                    p=public['hourly'].get(str(idx),{}).get(str(h))
                    if p and v['served_weight'] and p.get('mean_wait_min') is not None:
                        delta=abs(v['mean_wait_min']-p['mean_wait_min'])
                        assert delta<1e-5,(scenario,day,stop,h,delta)
                        checks.append(delta)
                for start,end in [(15,19),(17,18)]:
                    v=summarize([x for x in waits if x[0]==idx and start*3600<=x[1]<end*3600])
                    windows.append(dict(scenario=scenario,weekday=ko,stop=stop,label=COMMON['nodes'][idx]['label'],window=f'{start:02}:00-{end:02}:00',**v))
    totals=[]
    for scenario, waits in pooled.items():
        for stop,idx in HOT.items():
            for start,end in [(15,19),(17,18)]:
                totals.append(dict(scenario=scenario,stop=stop,label=COMMON['nodes'][idx]['label'],window=f'{start:02}:00-{end:02}:00',
                    **summarize([x for x in waits if x[0]==idx and start*3600<=x[1]<end*3600])))
    for rows in [hourly,windows,totals]:
        for row in rows: assert abs(row['arrival_weight']-row['served_weight']-row['unserved_weight'])<1e-7
    write_csv('model_hourly_waits.csv',hourly)
    write_csv('model_weekday_windows.csv',windows)
    write_csv('model_pooled_windows.csv',totals)
    result=dict(status='PASS',dataset='capacity_v3',campus_max_kmh=40,external_target_kmh=65,
        capacity_large=60,capacity_reverse=25,scenario_count=2,weekday_count=5,
        meaning='Preserved representative route-choice run, two headway scenarios; not independent Monte Carlo replications or actual people.',
        audit_inputs=manifest,hourly_rows=len(hourly),weekday_window_rows=len(windows),pooled_window_rows=len(totals),
        public_hour_mean_comparisons=len(checks),max_public_hour_mean_difference=max(checks) if checks else None,
        waiting_definition='First ready arrival at this shuttle stop to actual boarding; excludes approach walk and onboard time. Served-only durations; unserved weight separate. One transfer can appear at more than one stop.',
        window_definition='Wait arrival time in half-open interval; boarding may occur later. Pooled weekdays use passenger-equivalent weights, not arithmetic mean of weekday means.',
        source_comparison='No same-date, same-route, same-direction, same-stop measured waiting-time sample acquired. These are scenario outputs, not validated error scores.')
    (ROOT/'comparison_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='audit_inputs'},ensure_ascii=False,indent=2))
    for x in totals:
        if x['window']=='15:00-19:00':print(json.dumps(x,ensure_ascii=False))

if __name__=='__main__':main()
