"""Matched, single-factor checks of the Monday and Tuesday peak observations."""
from bisect import bisect_right
from pathlib import Path
import argparse
import contextlib
import math

from timing_inputs import HERE, REFERENCE, inputs, metadata, grade_bundle, ref
import demand_engine
import dwell_engine


def summarize(data,minute=918):
    start=minute*60
    def moments(rows,a,b):
        points={r[0]:r[1] for r in rows}
        times=sorted(points)
        cuts=[a,*[t for t in times if a<t<b],b]
        values=[]
        for t in cuts[:-1]:
            index=bisect_right(times,t)-1
            values.append(points[times[index]] if index>=0 else 0.)
        return [min(values),max(values),sum((b-a)*v for a,b,v in zip(cuts,cuts[1:],values))/(cuts[-1]-cuts[0])]
    out={}
    for label,node in [('snu',1),('daehak',42)]:
        q=data['queue_timeline'][node]
        parked=data.get('onboard_wait_timeline',[[] for _ in data['queue_timeline']])[node]
        at=f'{minute//60:02}{minute%60:02}'
        out[label]={'outside_'+at:moments(q,start,start+60),'inside_'+at:moments(parked,start,start+60),
                    'outside_hour_mean':moments(q,start-1800,start+1800)[2],'inside_hour_mean':moments(parked,start-1800,start+1800)[2]}
    return out


def run(which,day):
    folder=HERE/'single_factor'/(which if day=='화' else 'mon_'+which)
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/'summary.json').exists():return
    if which=='timing_only':
        b,_,_,_=inputs(day,'peak')
        engine=demand_engine
    else:
        b,_,_,_=grade_bundle(day,'peak')
        metadata(b['prepared']['common'])
        engine=dwell_engine
    engine.WORK=engine.OUT=engine.base.OUT=folder
    with (folder/'run.log').open('w',encoding='utf8') as log,contextlib.redirect_stdout(log):
        data=engine.simulate(b,day,'peak',export=False)
    report=data['report']
    assert report['capacity_violations']==0 and math.isclose(report['final_weight'],b['prepared']['expected'][day],abs_tol=1e-6)
    ref.previous.SAVE(folder/'summary.json',dict(case=which,day=day,metrics=summarize(data,918 if day=='화' else 1013),unserved=report['unserved_trip_weight']))


if __name__=='__main__':
    cli=argparse.ArgumentParser()
    cli.add_argument('factor',choices=['timing_only','boarding_only'])
    cli.add_argument('--day',choices=('화','월'),default='화')
    args=cli.parse_args()
    run(args.factor,args.day)
