"""Compare the two full trip/event ledgers, including fractional cohort splits."""
import bisect
from collections import Counter, defaultdict
import csv
import math
from experiment import (BASELINE, HERE, OUTPUT, REFERENCE, SCENARIO, TARGET, fingerprint,
                        load, reference, save)

HOURS = range(15,19)


def csv_file(name, rows):
    with (HERE/name).open('w',encoding='utf-8-sig',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def clock(seconds):
    seconds = int(round(seconds))
    return f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}'


def quantile(values, fraction):
    weight = sum(w for _,w in values)
    cumulative = 0.
    for val,w in sorted(values):
        cumulative += w
        if cumulative >= fraction*weight:
            return val


def durations(rows):
    mass = sum(r['weight'] for r in rows)
    return dict(trips=mass, **{k:sum(r[k]*r['weight'] for r in rows)/mass for k in
              ('walk_min','wait_min','ride_min','access_min')},
               access_median_min=quantile([(r['access_min'],r['weight']) for r in rows],.5),
               access_p90_min=quantile([(r['access_min'],r['weight']) for r in rows],.9))


def audit_state(path, assignments, reference_donors, paths, nodes):
    a = load(path/'audit-regular-thu.json.gz')
    data = load(path/'regular-thu.json')
    assert a['report']['capacity_violations']==0
    vehicle = {r[0]:r[1] for r in data['vehicles']}
    signature = fingerprint([(e[0],e[1],e[2],e[3],e[11],e[12]) for e in a['events']])
    mass = Counter()
    stop_hours = defaultdict(Counter)
    trips = []
    original_mode = Counter()
    window_start,window_end = 15*3600,19*3600
    for n,start,end,w,denied,unserved,uid,outcome in a['waits']:
        for h in HOURS:
            t = max(0.,min(end,(h+1)*3600)-max(start,h*3600))
            key = stop_hours[n,h]
            key['passenger_min'] += w*t/60
            if h*3600 <= start < (h+1)*3600:
                key['queue_entries'] += w
            if outcome=='boarded' and h*3600 <= end < (h+1)*3600:
                key['boarded'] += w
    entries = defaultdict(list)
    taken = defaultdict(list)
    for row in a['wait_audit']:
        if row['ticket'] is not None:
            entries[row['node']].append(row)
            if row['vehicle'] is not None and row['outcome']=='boarded':
                taken[row['node'],row['vehicle'],row['end']].append(row['ticket'])
    fifo_checks = 0
    for t,n,v,cap,before,off,on,after,left,_,q,rid,k in a['events']:
        assert abs(before-off+on-after)<1e-6 and -1e-6 <= after <= cap+1e-6
        assert left <= q+1e-6 and (left<1e-6 or abs(after-cap)<1e-6)
        if left>1e-7 and on>1e-7:
            departed = taken[n,v,t]
            remaining = [r['ticket'] for r in entries[n] if r['ready']<=t+1e-7 and
                         r['end']>t+1e-7 and [rid,k] in r['eligibility']]
            if departed and remaining:
                assert max(departed)<=min(remaining)
            fifo_checks += 1
    ledger_max = [0.]*len(nodes)
    ledger_area = [0.]*len(nodes)
    for n,timeline in enumerate(data['queue_timeline']):
        for i,(t,q,_) in enumerate(timeline):
            until = timeline[i+1][0] if i+1<len(timeline) else reference.base.END
            seconds = max(0.,min(until,window_end)-max(t,window_start))
            if seconds>0:
                ledger_max[n] = max(ledger_max[n],q)
                ledger_area[n] += seconds*q/60
        # Display timeline rounds epochs to a millisecond and weights to six decimals.
        integrated = sum(stop_hours[n,h]['passenger_min'] for h in HOURS)
        assert abs(ledger_area[n]-integrated)<.15,(n,ledger_area[n],integrated)
    for s in a['legs']:
        uid = s['id']
        legs = s['legs']
        weight = s['weight']
        assert not any(l[2] < l[1] for l in legs)
        assert all(abs(x[2]-y[1])<1e-5 for x,y in zip(legs,legs[1:]))
        rides = [l for l in legs if l[0]==3]
        if assignments is None:
            mass[uid] += weight
            if uid in reference_donors:
                first = vehicle[rides[0][6]] if rides else 'walk'
                original_mode[uid,first] += weight
            continue
        record = assignments.get(uid)
        mass[record['donor'] if record else uid] += weight
        if not record:
            continue
        assert abs(record['start']-s['start'])<1e-7
        assert not s['unserved'] and len(rides)<=1 and tuple(paths[legs[-1][3]][-1])==TARGET
        times = Counter()
        for l in legs:
            times[l[0]] += (l[2]-l[1])/60
        end = legs[-1][2]
        total = (end-s['start'])/60
        assert math.isclose(sum(times.values()),total,abs_tol=1e-7)
        rid = vehicle[rides[0][6]] if rides else 'walk'
        mode = ('walk' if not rides else ('shuttle' if rid.startswith('shuttle') else 'city'))
        trips.append(dict(id=uid,donor=record['donor'],building=record['building'],old_dest=record['old_dest'],
            weight=weight,stratum=record['stratum'],planned_hour=record['expected_hour'],start=s['start'],
            arrival=end,start_kst=clock(s['start']),arrival_kst=clock(end),mode=mode,route=rid,
            boarded_at=nodes[rides[0][4]]['label'] if rides else '',walk_min=times[0],
            wait_min=times[1],ride_min=times[3],access_min=total))
    return dict(mass=mass,stops=stop_hours,peak=ledger_max,signature=signature,trips=trips,
                report=a['report'],fifo_checks=fifo_checks,events=len(a['events']),original_mode=original_mode)


def main():
    inp = load(OUTPUT/'input_check.json')
    selected = {r['id']:r for r in load(OUTPUT/'assignments.json')}
    common = load(REFERENCE/'common.json.gz')
    nodes = common['nodes']
    paths = common['paths']
    more = load(OUTPUT/'added_paths.json.gz')
    assert len(paths)==more['first_index']
    paths.extend(more['paths'])
    source = {r['donor']:r for r in selected.values()}
    assert len(source)==len(selected)
    assert load(BASELINE/'result.json')['status']=='verified'
    old = audit_state(BASELINE,None,source,paths,nodes)
    new = audit_state(OUTPUT,selected,source,paths,nodes)
    assert old['signature']==new['signature'] and old['events']==new['events']
    assert old['mass'].keys()==new['mass'].keys()
    err = max(abs(old['mass'][u]-v) for u,v in new['mass'].items())
    assert err<1e-6 and math.isclose(sum(new['mass'].values()),inp['total_weight'],abs_tol=1e-6)
    trips = new['trips']
    got = Counter()
    for r in trips:
        got[r['id']]+=r['weight']
    assert set(got)==set(selected) and all(abs(w-selected[u]['weight'])<1e-7 for u,w in got.items())
    assert abs(sum(got.values())-320)<1e-7
    csv_file('station_trips.csv',trips)
    node_rows, hour_rows = [], []
    for n,node in enumerate(nodes):
        agg = Counter()
        for h in HOURS:
            x,y = old['stops'][n,h],new['stops'][n,h]
            row = dict(node=n,stop_id=node['stop_id'],label=node['label'],hour=h)
            for key in ('passenger_min','queue_entries','boarded'):
                for prefix, number in [('base',x[key]),('scenario',y[key]),('delta',y[key]-x[key])]:
                    name=f'{prefix}_{key}'
                    row[name]=number
                    agg[name]+=number
            hour_rows.append(row)
        node_rows.append(dict(node=n,stop_id=node['stop_id'],label=node['label'],**agg,
            delta_mean_queue=agg['delta_passenger_min']/240,base_peak=old['peak'][n],scenario_peak=new['peak'][n]))
    csv_file('stop_hours.csv',hour_rows)
    csv_file('stops.csv',node_rows)
    offsets = {}
    for delay in (0,2,4):
        buckets = Counter()
        for r in trips:
            buckets[int((r['arrival']+60*delay)//3600)]+=r['weight']
        offsets[delay] = dict(hourly=dict(sorted(buckets.items())),in_window=sum(buckets[h] for h in HOURS))
    origins = Counter()
    dists = Counter()
    routes = Counter()
    depart = Counter()
    for r in trips:
        depart[int(r['start']//3600)] += r['weight']
        origins[r['building']] += r['weight']
        dists[r['old_dest']] += r['weight']
        routes[r['route']] += r['weight']
    old_first = Counter()
    for (uid, rid),w in old['original_mode'].items():
        old_first[rid] += w*source[uid]['weight']/old['mass'][uid]
    assert math.isclose(sum(old_first.values()),320)
    modes = {k:durations([r for r in trips if r['mode']==k]) for k in sorted(set(r['mode'] for r in trips))}
    delta = sum(r['delta_passenger_min'] for r in node_rows)
    order = sorted(node_rows,key=lambda row:row['delta_passenger_min'])
    result = dict(model=inp['model'],reference=inp['reference'],total_trips=inp['total_weight'],
                  chosen=320,modes=modes,access=durations(trips),reference_first_modes=old_first,
                  prior_destinations=dists,station_access_routes=routes,campus_departures_by_hour=depart,
                  arrival_time_offset_sensitivity_minutes=offsets,buildings=origins,
                  historical=load(SCENARIO),station_snap_m=inp['station_snap_m'],
                  queue_person_minutes={k:sum(r[k+'_passenger_min'] for r in node_rows) for k in ('base','scenario','delta')},
                  mean_network_queue_delta=delta/240,largest_decreases=order[:5],largest_increases=order[-5:][::-1],
                  checks=dict(per_source_weight_max_error=err,source_groups=len(old['mass']),
                              identical_event_schedule=old['signature'],event_count=new['events'],
                              base_fifo_checks=old['fifo_checks'],scenario_fifo_checks=new['fifo_checks'],
                              scenario_capacity_violations=new['report']['capacity_violations'],
                              baseline_unserved=old['report']['unserved_trip_weight'],
                              scenario_unserved=new['report']['unserved_trip_weight'],
                              station_arrivals_verified=sum(got.values()),
                              data_sha256={str(p.parent.name)+'/'+p.name:reference.base.sha(p) for p in
                               [BASELINE/'audit-regular-thu.json.gz',OUTPUT/'audit-regular-thu.json.gz',
                                OUTPUT/'assignments.json',HERE/'compare.py']}))
    save(HERE/'comparison.json',result)
    print('PASS',result['checks'])


if __name__=='__main__':
    main()
