"""Reconcile a completed case with its V11 event format and local benchmark."""
import math
import verify_walk_choice_core as core
from analyze_walk_choices import physical_waits, distribution
from verify_capacity_corrections import expected_roster

def snapshot(data, node, second):
    points = dict((r[0],r[1]) for r in data['queue_timeline'][node])
    at = max((t for t in points if t <= second), default=None)
    return points[at] if at is not None else 0.

def minute(data, node, second):
    states = {t:q for t,q,_ in data['queue_timeline'][node] if second < t < second+60}
    values = [snapshot(data,node,second), *states.values()]
    return [min(values),max(values)]

def measures(data):
    events = [e for e in data['events'] if e[1]==42 and e[0]==61200 and e[11]=='shuttle-daehak']
    if len(events)!=1:
        raise ValueError(f'Expected one 17:00 Daehak-dong service, found {len(events)}')
    e=events[0]
    return dict(queue_1659_minute=minute(data,42,61140), queue_after_1700=snapshot(data,42,61200),
                capacity=e[3], boarded=e[6], onboard=e[7], ready_left=e[10],
                other_minute_ranges={'admin_snu_1653':minute(data,1,60780),'culture_1655':minute(data,59,60900),
                                     'gate_1703':minute(data,62,61380)})

def validate(bundle, folder, day, service, converted):
    from candidate import load, base, V11, SIM
    did=base.DAYS[day]
    core.WORK=core.OUT=folder
    checked=core.check(bundle,service,day,did)
    audit=load(folder/f'audit-{service}-{did}.json.gz')
    roster=expected_roster(bundle,service,True)
    for e in audit['events']:
        rid, start, cap, _ = roster[e[2]]
        assert (rid,cap)==(e[11],e[3])
        assert abs(start+bundle['prepared']['common']['route_info'][rid]['offsets'][e[12]]-e[0])<1e-6
    walked=set()
    for s in audit['legs']:
        if s['id'] in converted:
            weight, pid, seconds=converted[s['id']]
            assert not s['unserved'] and len(s['legs'])==1
            leg=s['legs'][0]
            assert leg[0]==0 and leg[3]==pid and abs(leg[2]-leg[1]-seconds)<1e-5
            assert math.isclose(s['weight'],weight) and s['id'] not in walked
            walked.add(s['id'])
    assert walked==set(converted)
    assert not any(d['forced'] for d in audit['behavior_decisions'])
    all_stops=distribution(physical_waits(audit))
    del audit
    base.save(folder/'all_stop_waits.json',all_stops)
    data=load(folder/f'{service}-{did}.json')
    result=measures(data)
    checks={key:data['report'][key] for key in ('input_weight','final_weight','capacity_violations','unserved_trip_weight')}
    del data
    baseline=load(SIM/f'public/data/capacity_v11/{service}-{did}.json')
    old_validation=load(V11/f'analysis-{service}-{did}.json')
    return dict(status='verified', candidate=result, baseline=measures(baseline), invariants=checks,
                converted_walk_trips_checked=len(walked), core=checked,
                max_wait_min=max(r['max_continuous_wait_min'] for r in all_stops.values()),
                over20_weight=math.fsum(r['over_20_minute_weight'] for r in all_stops.values()),
                v11_max_wait_min=old_validation['maximum_continuous_wait_min'])

