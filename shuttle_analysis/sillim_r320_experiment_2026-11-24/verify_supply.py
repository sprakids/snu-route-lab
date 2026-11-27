"""R-only copy of verify_walk_choice_core.check. Resolve split groups to their original class.
Upstream SHA256: 4936cef557907c7f8998c08240f7c32d0beab98254dc15ac21eba5b7fdb0b172
"""
from collections import Counter, defaultdict
import bisect, gzip, json, math
import numpy as np
from verify_walk_choice_core import read, base, planned_departures

def check(bundle,scenario,day,did,folder,donors):
    WORK = OUT = folder
    data=read(OUT/f'{scenario}-{did}.json');audit=read(WORK/f'audit-{scenario}-{did}.json.gz')
    common=bundle['prepared']['common'];plans=bundle['prepared']['plans'][day]
    assert data['report']['city_speed_revision']==common['city_speed_revision']
    for rid,info in common['route_info'].items():
        if info.get('city'):
            for pid,source in zip(info['segments'],info['segment_time_sources']):
                if source.get('campus_stop_corridor_40'):assert max(common['motion_profiles'][str(pid)]['cap'])<=40
    expected={p[0]:p[3] for p in plans};mass=Counter();board=Counter();alight=Counter()
    vehicle_changes=defaultdict(lambda:defaultdict(float));checks=Counter()
    for s in audit['legs']:
        w=s['weight'];mass[s['id']]+=w
        assert all(math.isfinite(h[0]) for h in s['history'])
        for a,b in zip(s['legs'],s['legs'][1:]):assert abs(a[2]-b[1])<1e-5
        for l in s['legs']:
            assert l[2]>=l[1] and 0<=l[3]<len(common['paths']);checks['legs']+=1
            if l[0]==3:
                board[l[4],l[6],l[1]]+=w;alight[l[6],l[2]]+=w
                vehicle_changes[l[6]][l[1]]+=w;vehicle_changes[l[6]][l[2]]-=w
    assert set(mass)==set(expected)
    error=max(abs(mass[k]-v) for k,v in expected.items());assert error<1e-6
    occupancy={}
    for vid,changes in vehicle_changes.items():
        times=sorted(changes);loads=[];value=0.
        for t in times:value+=changes[t];loads.append(value)
        assert abs(value)<1e-6;occupancy[vid]=(times,loads)
    for vid,rid,cap,legs in data['vehicles']:
        info=common['route_info'][rid]
        if info.get('city'):
            assert cap==info['capacity']
            index=info['segments'].index(legs[0][2])
            clock=legs[0][0]-info['offsets'][index]+info['offsets'][info['anchor']]-info['origin_to_modeled_first_stop_seconds']
            assert min(abs(clock-t) for t in planned_departures(info['plan']))<1e-5
            checks['planned_city_departures']+=1
        for a,b,pid,load in legs:
            if vid in occupancy:
                times,loads=occupancy[vid];j=bisect.bisect_right(times,a+1e-7)-1;value=loads[j] if j>=0 else 0.
            else:value=0.
            assert abs(value-load)<2e-5 and -1e-5<=load<=cap+1e-5,(vid,a,value,load)
            profile=common['motion_profiles'][str(pid)]
            assert b-a>=profile['duration']-1e-5;checks['vehicle_segments']+=1
    bynode=defaultdict(list)
    for w,meta in zip(audit['waits'],audit['wait_audit']):
        n,a,b,weight,denied,unserved,uid,outcome=w
        assert b>=a and unserved==(outcome=='unserved') and meta['weight']==weight
        bynode[n].append((w,meta))
    for e in audit['events']:
        t,node,vid,cap,before,off,on,after,left,new,physical,rid,k=e
        assert abs(before-off+on-after)<1e-6 and -1e-6<=after<=cap+1e-6
        assert abs(board[node,vid,t]-on)<1e-5 and abs(alight[vid,t]-off)<1e-5
        assert physical+1e-6>=left and (left<=1e-6 or abs(after-cap)<1e-5)
        checks['capacity_events']+=1
        if on>1e-7 and left>1e-7:
            rows=bynode[node]
            taken=[m['ticket'] for w,m in rows if m['vehicle']==vid and abs(m['end']-t)<1e-7]
            remain=[m['ticket'] for w,m in rows if m['ticket'] is not None and m['ready']<=t+1e-7 and
                    m['end']>t+1e-7 and [rid,k] in m['eligibility']]
            if taken and remain:assert max(taken)<=min(remain),(rid,t,'eligible FIFO')
            checks['fifo_events']+=1
    for node,rows in bynode.items():
        for h in range(11,24):
            group=[w for w,m in rows if max(base.START,h*3600)<=w[1]<min(base.END,(h+1)*3600)]
            row=data['hourly'][str(node)][str(h)];total=math.fsum(w[3] for w in group)
            assert abs(total-row['arrival_weight'])<1e-5
            assert abs(total-row['served_weight']-row['switched_weight']-row['unserved_weight'])<1e-5
            if total:assert abs(math.fsum((w[2]-w[1])*w[3] for w in group)/total/60-row['mean_queue_exposure_min'])<1e-6
            checks['hourly_cells']+=1
        changes=defaultdict(lambda:[0.,0.])
        for w,m in rows:
            n,a,b,weight,denied,unserved,*_=w
            if unserved and b==base.END:b+=1
            changes[round(a,3)][0]+=weight;changes[round(b,3)][0]-=weight
            if denied>=0:changes[round(denied,3)][1]+=weight;changes[round(b,3)][1]-=weight
        times=sorted(changes);running=np.cumsum([changes[t] for t in times],axis=0)
        timeline=data['queue_timeline'][node];public_times=[r[0] for r in timeline]
        for t in range(base.START,base.END+1,73):
            i=bisect.bisect_right(times,t)-1;j=bisect.bisect_right(public_times,t)-1
            want=running[i] if i>=0 else np.zeros(2);got=timeline[j][1:] if j>=0 else [0.,0.]
            assert np.max(np.abs(want-got))<2e-5;checks['queue_samples']+=1
    for profile in common['motion_profiles'].values():
        for i,cap in enumerate(profile['cap']):assert max(profile['v'][i],profile['v'][i+1])*3.6<=cap+1e-4
    # Passenger weights count trips, not unique students. Class-end timing is
    # restored from the original event-to-particle mapping for the summary.
    events=base.read(base.ROOT.parent/'scenario_comparison_2026-11-07/simulation_outputs/input_snapshot/course_endings_current.json')
    events=[e for e in events if e['included_main'] and e['weekday'] in base.DAYS and e['end_minute']<=1390]
    classends={p[0]:events[(donors.get(p[0],p[0])-1)//48]['end_minute']*60 for p in plans}
    summaries=[]
    for scope in ('all','snu','engineering_snu'):
        selected={p[0] for p in plans if base.START<=classends[p[0]]<base.END and
                  (scope=='all' or p[2]=='snu') and (scope!='engineering_snu' or p[1] in ('301','302'))}
        trip=[s for s in audit['legs'] if s['id'] in selected];weight=math.fsum(s['weight'] for s in trip)
        complete=[s for s in trip if not s['unserved']];cw=math.fsum(s['weight'] for s in complete)
        waiting=math.fsum(s['weight']*sum(max(0.,min(l[2],base.END)-min(l[1],base.END)) for l in s['legs'] if l[0]==1) for s in trip)
        total=math.fsum(s['weight']*(s['legs'][-1][2]-classends[s['id']]) for s in complete)
        summaries.append({'scenario':scenario,'weekday':day,'scope':scope,'weight':weight,'completed_weight':cw,
            'unserved_weight':weight-cw,'mean_cumulative_wait_min':waiting/weight/60 if weight else None,
            'mean_class_end_total_min_completed':total/cw/60 if cw else None,
            'switched_trip_weight':math.fsum(s['weight'] for s in trip if s['history'])})
    return {'scenario':scenario,'weekday':day,'status':'PASS','particle_mass_max_error':error,'checks':dict(checks),'summaries':summaries}

