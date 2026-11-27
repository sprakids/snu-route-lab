"""Trace the November 24 observation against stored Tuesday simulations, without running the engine."""
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path
import gzip
import json
import math

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
MODEL = BASE/'261124110718'
V11 = BASE/'simulation_viewer_2026-11-07'
SOURCE = BASE/'scenario_comparison_2026-11-07/simulation_outputs/input_snapshot/course_endings_current.json'
WINDOW = 15*3600 + 18*60


def read(path):
    with (gzip.open if path.suffix=='.gz' else open)(path,'rt',encoding='utf8') as stream:
        return json.load(stream)


def clock(t):
    return f'{int(t//3600):02}:{int(t%3600//60):02}:{t%60:06.3f}'


def span(curve,start,end):
    pts={t:v for t,v,_ in curve}
    times=sorted(pts)
    levels=[pts[times[bisect_right(times,start)-1]],*(pts[t] for t in times if start<t<end)]
    return [min(levels),max(levels)]


def flow(waits,a,b):
    # State immediately before each endpoint. Events at a enter this accounting interval.
    n0=math.fsum(w['weight'] for w in waits if w['arrival']<a<=w['end'])
    n1=math.fsum(w['weight'] for w in waits if w['arrival']<b<=w['end'])
    entered=math.fsum(w['weight'] for w in waits if a<=w['arrival']<b)
    exits=Counter()
    for w in waits:
        if a<=w['end']<b:
            exits[w['outcome']]+=w['weight']
    assert math.isclose(n0+entered-sum(exits.values()),n1,abs_tol=1e-6)
    return dict(start=clock(a),end_exclusive=clock(b),opening=n0,entries=entered,exits=dict(exits),closing=n1)


def diagnostic(service,events,donors,common):
    name=f'{service}-tue'
    ledger=read(MODEL/'runs'/name/'attempt-01'/f'audit-{name}.json.gz')
    replay=read(MODEL/'viewer-data'/f'{name}.json.gz')
    def course(uid):
        return events[(donors.get(uid,uid)-1)//48]
    trips=ledger['legs']
    starts={}
    weights=Counter()
    for t in trips:
        uid=t['id']
        assert starts.setdefault(uid,t['start'])==t['start']
        weights[uid]+=t['weight']
    result={}
    start=15*3600
    for stop in ('admin_snu','admin_daehak'):
        node=common['hot_nodes'][stop]
        waits=[w for w in ledger['wait_audit'] if w['node']==node]
        visits=[w for w in waits if abs(w['arrival']-w['physical_stop_entry'])<1e-6]
        def describe(w):
            uid=w['id']; c=course(uid)
            return dict(arrival=clock(w['arrival']),departure=clock(starts[uid]),class_end=c['end'],
                        building=c.get('building_name'),mass=w['weight'])
        departures=defaultdict(Counter)
        for e in ledger['events']:
            if e[1]==node and start<=e[0]<start+36*60:
                row=departures[clock(e[0])]
                row['vehicles']+=1;row['boarded']+=e[6];row['available_before_boarding']+=e[3]-e[4]+e[5]
                row['after_last_vehicle_queue']=e[10]
        first915=min((w for w in visits if course(w['id'])['end_minute']==915),key=lambda w:w['arrival'])
        cohorts=defaultdict(Counter)
        for w in visits:
            if start+10*60<w['arrival']<start+19*60:
                cohorts['after_1510_before_1519'][course(w['id'])['end']]+=w['weight']
            if start+20*60<w['arrival']<start+30*60:
                cohorts['after_1520_before_1530'][course(w['id'])['end']]+=w['weight']
        result[stop]=dict(
            queue_1518=span(replay['queue_timeline'][node],WINDOW,WINDOW+60),
            queue_1352=span(replay['queue_timeline'][node],49920,49980),
            queue_1523=span(replay['queue_timeline'][node],55380,55440),
            flows=[flow(waits,start+a*60,start+b*60) for a,b in ((10,18),(18,19),(19,20),(20,25),(25,30))],
            departures=departures,
            previous_arrival=describe(max((w for w in visits if w['arrival']<WINDOW),key=lambda w:w['arrival'])),
            next_arrival=describe(min((w for w in visits if w['arrival']>=WINDOW),key=lambda w:w['arrival'])),
            first_from_1515_classes=describe(first915),
            new_visit_arrivals_by_class_end=cohorts)
    cohorts=[]
    for m in (890,915,920):
        ids=[u for u in weights if course(u)['end_minute']==m]
        elapsed=[starts[u]-m*60 for u in ids]
        assert all(60<=t<=480 for t in elapsed)
        cohorts.append(dict(class_end_minute=m,mass=math.fsum(weights[u] for u in ids),min_exit_delay_s=min(elapsed),
                            max_exit_delay_s=max(elapsed)))
    result['class_cohorts']=cohorts
    result['campus_departures_1500_to_1516']=math.fsum(w for uid,w in weights.items() if start<=starts[uid]<start+16*60)
    result['campus_departures_1516_to_1519']=math.fsum(w for uid,w in weights.items() if start+16*60<=starts[uid]<start+19*60)
    # Partial counterfactual for the direct-shuttle pool only. Keep each student's actual
    # start, weight and walking time on the original access path, with current terrain.
    original=read(V11/'peak_pair_correction_2026-11-10/prepared.json.gz')
    surface=read(BASE/'261124103744/walking_surface.json.gz')
    eligible=Counter()
    for p in original['prepared']['plans']['화']:
        uid=p[0]
        if original['destination_keys'][str(uid)]!='daehak' or not p[6]:
            continue
        st=p[6][0]
        if st['rid']!='shuttle-daehak' or st['board']!=0:
            continue
        assert starts[uid]==p[4]
        pid,sec=p[5]
        t=starts[uid]+sec*surface[str(pid)]['factor']
        if start+10*60<t<start+19*60:
            eligible['1510_to_1519']+=weights[uid]
        if start+20*60<t<start+30*60:
            eligible['1520_to_1530']+=weights[uid]
    result['v11_direct_daehak_group_all_keep_original_access_no_network_feedback'] = {
        key:eligible[key] for key in ('1510_to_1519','1520_to_1530')}
    return result


def main():
    events=[r for r in read(SOURCE) if r['included_main'] and r['weekday'] in '월화수목금' and r['end_minute']<=1390]
    donors={r['plan'][0]:r['donor'] for r in read(BASE/'261124102753/inputs/tue.json.gz')['replacements']}
    common=read(MODEL/'viewer-data/common.json.gz')
    assert common['candidate_id']=='R261124110718'
    refs={}
    for version,directory in [('V11',V11/'public/data/capacity_v11'),
                              ('R261124103744',BASE/'261124103744/viewer-data'),('R261124110718',MODEL/'viewer-data')]:
        replay=read(directory/('peak-tue.json' if version=='V11' else 'peak-tue.json.gz'))
        refs[version]={key:span(replay['queue_timeline'][common['hot_nodes'][key]],WINDOW,WINDOW+60)
                       for key in ('admin_snu','admin_daehak')}
    by_end=read(BASE/'261124101820/runs/regular-tue/attempt-01/departure_profile.json')['rate_by_class_end']
    detail={s:diagnostic(s,events,donors,common) for s in ('peak','regular')}
    for r in detail.values():
        for cohort in r['class_cohorts']:
            row=next(row for row in by_end if row['end_minute']==cohort['class_end_minute'])
            assert math.isclose(row['immediate_trip_mass'],cohort['mass'],abs_tol=1e-5)
    out=dict(model=common['candidate_id'],date='2026-11-24',reference_1518=refs,
             class_endings=[r for r in by_end if 890<=r['end_minute']<=920],cases=detail)
    (HERE/'1518_원인분석.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')


if __name__=='__main__':
    main()
