"""Full-flow statistics; never count the viewer's sampled dots."""
from collections import defaultdict
import math
from artifacts import START,END,EPS

def percentile(rows,q):
    if not rows:return None
    target=sum(w for x,w in rows)*q;acc=0.
    for value,weight in sorted(rows):
        acc+=weight
        if acc>=target-EPS:return value
    return rows[-1][0]

def export_run(prepared,day,scenario,finished,waits,events,vehicles,decisions,gate_boardings,checks,forecast_calls,export=False):
    changes=defaultdict(lambda:defaultdict(float));group=defaultdict(list)
    for row in waits:
        node,a,b,w,*_=row;changes[node][a]+=w;changes[node][b]-=w
        if START<=a<END:group[node,None].append(row);group[node,int(a//3600)].append(row)
    def stats(rows):
        served=[r for r in rows if r[7]=='boarded'];sw=sum(r[3] for r in served)
        return {'arrival_weight':sum(r[3] for r in rows),'served_weight':sw,
                'switched_weight':sum(r[3] for r in rows if r[7]=='switched'),
                'unserved_weight':sum(r[3] for r in rows if r[5]),
                'mean_wait_min':sum((r[2]-r[1])*r[3] for r in served)/sw/60 if sw else None}
    timeline=[]
    for node in range(len(prepared['common']['nodes'])):
        mass=0.;rows=[]
        for t,delta in sorted(changes[node].items()):
            mass+=delta;assert mass>-1e-5
            if t<=END:rows.append([t,max(0.,mass)])
        timeline.append(rows)
    served=[s for s in finished if not s['unserved']];sw=sum(s['w'] for s in served)
    report={'scenario':scenario,'weekday':day,'input_weight':sum(p[3] for p in prepared['plans'][day]),
            'final_weight':sum(s['w'] for s in finished),'finished_weight':sw,
            'unserved_trip_weight':sum(s['w'] for s in finished if s['unserved']),
            'full_particles':len(prepared['plans'][day]),'render_dots_not_generated':True,
            'capacity_checks':checks,'capacity_violations':0,'vehicles':len(vehicles),
            'max_queue':max((v for rows in timeline for t,v in rows),default=0.),
            'switch_event_weight':sum(s[2] for s in decisions),'switched_trip_weight':sum(s['w'] for s in finished if s['history']),
            'forecast_calls':forecast_calls,
            'mean_finished_trip_minutes':sum((s['finish_time']-s['plan'][4])*s['w'] for s in served)/sw/60 if sw else None}
    return {'report':report,'daily':{str(i):stats(group[i,None]) for i in range(len(timeline))},
            'hourly':{str(i):{str(h):stats(group[i,h]) for h in range(11,24)} for i in range(len(timeline))},'queue_timeline':timeline}
