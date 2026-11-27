"""Run the integrated weekday model. The default includes station 4411."""
import argparse
from collections import Counter, defaultdict
import math
import os
from pathlib import Path
import shutil
import sys
sys.dont_write_bytecode = True

from model import HERE, MODEL, DATA, INPUTS, DAYS, HOURS, REFERENCE, DEST, rail, reference, load, SAVE
from model import build_inputs, integrated_bundle
from verify_supply import check
from validate import measures
from analyze_walk_choices import physical_waits, distribution


def queue_areas(timelines):
    rows = []
    for steps in timelines:
        area = 0.
        for i,(start,n,_) in enumerate(steps):
            end = steps[i+1][0] if i+1 < len(steps) else 19*3600
            area += max(0., min(end,19*3600)-max(start,15*3600))*n/60
        rows.append(area)
    return rows


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
    fleet = lambda data: [(e[0],e[1],e[2],e[3],e[11],e[12]) for e in data['events']]
    assert fleet(replay) == fleet(old)
    expected = b['prepared']['expected'][day]
    rep = replay['report']
    assert math.isclose(expected, rep['input_weight'],abs_tol=1e-6) and expected<=30_000
    assert math.isclose(rep['final_weight'],expected,abs_tol=1e-6) and rep['capacity_violations']==0
    assert not with_rail or any(p[2]==DEST for p in replay['trips'])
    return dict(model=MODEL, status='verified', rail_included=with_rail, day=day, service=service,
        weekday_demand=expected, rail_target=assigned, station_arrivals=arrivals, access_person_minutes=access_minutes,
        initial=started, completed=finished, checks=verification['checks'], maximum_mass_error=verification['particle_mass_max_error'],
        unserved=rep['unserved_trip_weight'], capacity_violations=rep['capacity_violations'], identical_supply_events=len(old['events']),
        max_continuous_wait=max(r['max_continuous_wait_min'] for r in stops.values()),
        over20_weight=math.fsum(r['over_20_minute_weight'] for r in stops.values()),
        field=measures(replay), stop_person_minutes=queue_areas(replay['queue_timeline']))


def expose_replay(output, name):
    target = DATA/f'{name}.json.gz'
    if target.exists() and reference.base.sha(target) == reference.base.sha(output/f'{name}.json.gz'):
        return
    temp = target.with_suffix('.tmp')
    shutil.copyfile(output/f'{name}.json.gz', temp)
    os.replace(temp,target)


def run(day, service, with_rail=True, retry=False):
    name = f'{service}-{DAYS[day]}'
    case = HERE/('runs' if with_rail else 'controls')/name
    case.mkdir(parents=True, exist_ok=True)
    existing = sorted(case.glob('attempt-*/result.json'))
    if existing:
        result = load(existing[-1])
        assert result['model']==MODEL and result['rail_included']==with_rail and result['status']=='verified'
        if with_rail:
            expose_replay(existing[-1].parent,name)
        return result
    attempts = sorted(case.glob('attempt-*'))
    if attempts and not retry:
        raise RuntimeError(f'Check the existing attempt before retrying: {case}')
    output = case/f'attempt-{len(attempts)+1:02}'
    output.mkdir()
    b, patch, donors = integrated_bundle(day,with_rail)
    reference.engine.WORK = reference.engine.OUT = reference.base.OUT = output
    reference.engine.simulate(b,day,service)
    result = audit_case(b,day,service,output,patch,donors,with_rail)
    if with_rail:
        expose_replay(output,name)
    SAVE(output/'result.tmp',result)
    os.replace(output/'result.tmp',output/'result.json')
    return result


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--day',choices=DAYS,default='월')
    parser.add_argument('--service',choices=('regular','peak'),default='regular')
    parser.add_argument('--without-rail',action='store_true',help='matched comparison only')
    parser.add_argument('--prepare',action='store_true',help='rebuild the shared paths and weekday assignments')
    parser.add_argument('--new-attempt',action='store_true')
    args=parser.parse_args()
    if args.prepare:
        build_inputs()
    else:
        if not (INPUTS/'weekday_targets.json').exists():
            parser.error('Run --prepare before the first simulation.')
        res=run(args.day,args.service,not args.without_rail,args.new_attempt)
        print(MODEL,res['day'],res['service'],res['status'],res['rail_target'],flush=True)
