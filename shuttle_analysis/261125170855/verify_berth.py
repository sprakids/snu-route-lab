"""Independent passenger, vehicle, queue, FIFO and terminal dwell checks."""
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
    windows={vid:(node,op,dep,cap) for node,vid,op,dep,cap in data['door_windows']}
    early=Counter(); at_open=Counter()
    metered=bundle.get('terminal_service_treatment', False)
    limited={(vid,node,t):(free,left) for vid,node,t,free,left in data['time_limited_departures']}
    for t,n,vid,w,count,dep in data['preboard_events']:
        node,op,scheduled,cap=windows[vid]
        assert node==n and op<=t<dep==scheduled and 0<w<=count+1e-6 and count<=cap+1e-6
        early[n,vid,t]+=w
    early_total=Counter()
    for key,w in early.items():
        assert abs(board[key]-w)<1e-6
        early_total[key[:2]]+=w
    if metered:
        from policy import SECONDS_PER_RIDER
        last={}
        for (n,vid,t),w in sorted(early.items(),key=lambda item:item[0][2]):
            assert w<=1+1e-6 and t-last.get(vid,windows[vid][1])>=SECONDS_PER_RIDER-1e-7
            last[vid]=t
    presence={vid:(n,area,op,dep,clock) for n,vid,area,op,dep,clock in data['terminal_presence']}
    assert windows.keys()==presence.keys()
    for vid,(node,op,dep,cap) in windows.items():
        n,area,opened,dep2,clock=presence[vid]
        assert node==n and area<=op==opened<dep==dep2
        at_open[vid]=alight[vid,area]
    for n in {row[0] for row in presence.values()}:
        groups=defaultdict(list)
        for node,area,op,dep,clock in presence.values():
            if node==n:groups[clock].append((op,dep))
        previous=-math.inf
        for clock,rows in sorted(groups.items()):
            assert len({dep for op,dep in rows})==1 and all(op>=previous for op,dep in rows)
            previous=rows[0][1]
    if bundle.get('single_line',True):
        last={}
        for (n,vid,t),w in sorted(early.items(),key=lambda item:item[0][2]):
            assert t-last.get(n,-math.inf)>=SECONDS_PER_RIDER-1e-7
            last[n]=t
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
            if pid==common['dwell_path']:
                assert vid in windows and presence[vid][1]<=a<=b<=windows[vid][2]
                assert common['paths'][pid][0]==common['paths'][pid][-1]
                checks['stationary_segments']+=1
            else:
                profile=common['motion_profiles'][str(pid)]
                assert b-a>=profile['duration']-1e-5
            checks['vehicle_segments']+=1
    bynode=defaultdict(list)
    for w,meta in zip(audit['waits'],audit['wait_audit']):
        n,a,b,weight,denied,unserved,uid,outcome=w
        assert b>=a and unserved==(outcome=='unserved') and meta['weight']==weight
        bynode[n].append((w,meta))
    for e in audit['events']:
        t,node,vid,cap,before,off,on,after,left,new,physical,rid,k=e
        assert abs(before-off+on-after)<1e-6 and -1e-6<=after<=cap+1e-6
        terminal=vid in windows and windows[vid][:1]==(node,) and abs(t-windows[vid][2])<1e-7
        check_board=board[node,vid,t]+(early_total[node,vid] if terminal else 0.)
        check_off=at_open[vid] if terminal else alight[vid,t]
        assert abs(check_board-on)<1e-5 and abs(check_off-off)<1e-5
        assert physical+1e-6>=left
        if terminal and metered:
            assert board[node,vid,t]==0
        if left>1e-6 and cap-after>1e-5:
            assert terminal and metered and new==0
            free,residual=limited[vid,node,t]
            assert abs(free-(cap-after))<1e-5 and abs(residual-left)<1e-5
        checks['capacity_events']+=1
        if on>1e-7 and left>1e-7:
            rows=bynode[node]
            taken=[m['ticket'] for w,m in rows if m['vehicle']==vid and abs(m['end']-t)<1e-7]
            remain=[m['ticket'] for w,m in rows if m['ticket'] is not None and m['ready']<=t+1e-7 and
                    m['end']>t+1e-7 and [rid,k] in m['eligibility']]
            if taken and remain:assert max(taken)<=min(remain),(rid,t,'eligible FIFO')
            checks['fifo_events']+=1
    for node in (common['hot_nodes']['admin_snu'],common['hot_nodes']['admin_daehak']):
        # Tickets reflect readiness order. Patients who boarded this dedicated queue
        # cannot overtake an earlier ticket that boards later, including while doors are open.
        served=sorted((m['ticket'],m['end']) for w,m in bynode[node] if m['outcome']=='boarded')
        last=-1
        for _,end in served:
            assert end>=last-1e-6,(node,'terminal FIFO',end,last)
            last=end
        checks['terminal_fifo_tickets']+=len(served)
        intervals=defaultdict(float)
        for (n,vid,t),w in early.items():
            if n==node:
                intervals[t]+=w
                intervals[windows[vid][2]]-=w
        mass=0.
        rows=data['onboard_wait_timeline'][node]
        assert len(rows)==len(intervals)
        for (t,w),(actual_t,actual_mass) in zip(sorted(intervals.items()),rows):
            mass+=w
            assert t==actual_t and math.isclose(mass,actual_mass,abs_tol=1e-6)
        assert abs(mass)<1e-6
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

