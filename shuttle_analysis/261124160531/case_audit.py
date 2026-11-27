import math
from collections import Counter, defaultdict
from timing_inputs import REFERENCE, MODEL, ref
from run_integrated import queue_areas, measures, physical_waits, distribution, DAYS, DEST, rail, load, SAVE
from verify_candidate import check

def audit_case(b, day, service, output, patch, donors, with_rail):
    did = DAYS[day]
    name = f'{service}-{did}'
    verification = check(b, service, day, did, output, donors)
    assert verification['status']=='PASS'
    common = b['prepared']['common']
    plans = b['prepared']['plans'][day]
    started = defaultdict(Counter)
    for p in plans:
        dest = b['destination_keys'][str(p[0])]
        started[dest]['total'] += p[3]
        if not p[6]:
            started[dest]['walk'] += p[3]
    ledger = load(output/f'audit-{name}.json.gz')
    vehicles = {e[2]:e[11] for e in ledger['events']}
    finished = defaultdict(Counter)
    arrivals = Counter()
    access_minutes = 0.
    for trip in ledger['legs']:
        dest = b['destination_keys'][str(trip['id'])]
        weight = trip['weight']
        if trip['unserved']:
            finished[dest]['unserved'] += weight
            continue
        rides = [vehicles[x[6]] for x in trip['legs'] if x[0]==3]
        mode = 'walk' if not rides else 'city' if any(not r.startswith('shuttle') for r in rides) else 'shuttle'
        finished[dest][mode] += weight
        if dest == DEST:
            assert trip['id'] in donors and tuple(common['paths'][trip['legs'][-1][3]][-1]) == rail.TARGET
            end = trip['legs'][-1][2]
            arrivals[int(end//3600)] += weight
            access_minutes += weight * (end-trip['start'])/60
    for dest in started:
        assert math.isclose(started[dest]['total'],sum(finished[dest].values()),abs_tol=1e-6)
    assigned = patch['station_demand'] if with_rail else 0.
    assert math.isclose(sum(arrivals.values())+finished.get(DEST,{}).get('unserved',0.),assigned,abs_tol=1e-6)
    stops = distribution(physical_waits(ledger))
    SAVE(output/'all_stop_waits.json',stops)
    del ledger
    replay = load(output/f'{name}.json')
    old = load(REFERENCE/'runs'/name/'attempt-01'/f'{name}.json')
    windows={vid:dep-opened for node,vid,opened,dep,cap in replay['door_windows']}
    signature=lambda e:(e[1],e[2],e[3],e[11],e[12])
    before={signature(e):e[0] for e in old['events']}
    after={signature(e):e[0] for e in replay['events']}
    assert len(before)==len(old['events']) and before.keys()==after.keys()
    for (node,vid,cap,rid,k),stamp in before.items():
        lead=windows.get(vid,0.) if rid=='shuttle-41841' and k==0 else 0.
        assert math.isclose(after[node,vid,cap,rid,k],stamp-lead,abs_tol=1e-6)
    expected = b['prepared']['expected'][day]
    rep = replay['report']
    assert math.isclose(expected, rep['input_weight'],abs_tol=1e-6) and expected<=30_000
    assert math.isclose(rep['final_weight'],expected,abs_tol=1e-6) and rep['capacity_violations']==0
    assert not with_rail or any(p[2]==DEST for p in replay['trips'])
    return dict(model=MODEL, status='verified', rail_included=with_rail, day=day, service=service,
        weekday_demand=expected, rail_target=assigned, station_arrivals=arrivals, access_person_minutes=access_minutes,
        initial=started, completed=finished, checks=verification['checks'], maximum_mass_error=verification['particle_mass_max_error'],
        unserved=rep['unserved_trip_weight'], capacity_violations=rep['capacity_violations'], verified_supply_events=len(before),
        max_continuous_wait=max(r['max_continuous_wait_min'] for r in stops.values()),
        over20_weight=math.fsum(r['over_20_minute_weight'] for r in stops.values()),
        field=measures(replay), stop_person_minutes=queue_areas(replay['queue_timeline']))


