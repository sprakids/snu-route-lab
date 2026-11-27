"""Trace the largest queue misses and every consecutive wait exceeding twenty minutes."""
import csv
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'261124160531'
sys.path.insert(0,str(BASE/'report'))
from compare import Curve, read, seconds, save_json

def phase(data,node,stamp):
    doors=[(v,op,dp) for n,v,op,dp,_ in data['door_windows'] if n==node and op<stamp+60 and dp>stamp]
    cut=sorted({stamp,stamp+60,*[t for v,op,dp in doors for t in (op,dp) if stamp<t<stamp+60]})
    fraction=sum(b-a for a,b in zip(cut,cut[1:]) if any(op<=a<dp for v,op,dp in doors))/60
    return dict(fraction_with_open_bus=fraction,windows=doors,
                outside=Curve(data['queue_timeline'][node]).stats(stamp,stamp+60),
                onboard=Curve(data['onboard_wait_timeline'][node]).stats(stamp,stamp+60))

if __name__=='__main__':
    common=read(BASE/'viewer-data/common.json.gz')
    out=[]
    tails=[]
    for d in ('mon','tue','wed','thu','fri'):
        for s in ('peak','regular'):
            key=f'{s}-{d}'
            for c in ('baseline','combined'):
                dir=BASE/'runs'/key/'attempt-01' if c=='baseline' else HERE/'runs'/c/key
                data=read(dir/f'{key}.json.gz')
                if d in ('mon','tue','wed'):
                    minutes={'mon':['16:53'],'tue':['15:23','15:18'],'wed':['16:00']}[d]
                    for t in minutes:
                        node=common['hot_nodes']['admin_snu']
                        out.append(dict(day=d,service=s,condition=c,time=t,**phase(data,node,seconds(t))))
                if c=='combined':
                    summary=read(dir/'summary.json')
                    if summary['over20_weight']>0:
                        audit=read(dir/f'audit-{key}.json.gz')
                        for w in audit['wait_audit']:
                            if (w['end']-w['physical_stop_entry'])<=1200+1e-6:
                                continue
                            allowed=w['eligibility']
                            events=[e for e in data['events'] if e[1]==w['node'] and [e[11],e[12]] in allowed and
                                    w['physical_stop_entry']<=e[0]<=w['end']]
                            tails.append(dict(day=d,service=s,stop=common['nodes'][w['node']]['name'],weight=w['weight'],
                                arrival=w['physical_stop_entry'],end=w['end'],full_passes=w['full_passes_seen'],
                                switches=w['realized_change_count'],outcome=w['outcome'],eligible_events=events))
    save_json(HERE/'개문과_장기대기_원인.json',dict(shuttle_minutes=out,over20= tails))
