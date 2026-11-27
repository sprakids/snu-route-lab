"""Paired V12 experiment on upper-engineering class-to-departure time."""
import argparse
from collections import defaultdict
import contextlib
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
V12 = HERE.parent / '261125170855'
sys.path.insert(0, str(V12))
import simulate as official

UPPER = {'300', '301', '302'}
MODEL = 'R' + HERE.name


def treatment(bundle, day, donors, cap, all_upper_delay=False):
    timing = official.prior.timing
    courses = timing.ref.ref.class_events(timing.ref.load(timing.ref.ref.COURSES))
    plans = bundle['prepared']['plans'][day]
    strata = defaultdict(lambda: defaultdict(float))
    # Start from a byte-identical V12 departure plan; replace only the coefficient
    # of the existing extended-stay draw for eligible upper-campus trips.
    for i, plan in enumerate(plans):
        parent = donors.get(plan[0], plan[0])
        course = courses[(parent - 1) // 48]
        building = str(course['building'])
        end = course['end_minute']
        assert building == plan[1] and day == course['weekday']
        zone = 'upper' if building in UPPER else 'other'
        counter = strata[end, zone]
        counter['mass'] += plan[3]
        counter['v12_lag_min_mass'] += (plan[4] / 60 - end) * plan[3]
        if zone == 'other' or end > 1080:
            continue
        if all_upper_delay:
            shift = 30
        else:
            if timing.uniform(f'trip/{parent}') >= timing.STAY_RATE:
                continue
            shift = (cap - 90) * timing.uniform(f'extended-activity/{parent}')
            assert min(0, cap - 90) <= shift <= max(0, cap - 90)
        plans[i] = [*plan[:4], plan[4] + 60 * shift, *plan[5:]]
        counter['affected'] += plan[3]
        counter['delta_min_mass'] += shift * plan[3]
    return [dict(end_minute=end, zone=zone, **counts) for (end, zone), counts in sorted(strata.items())]


def run(day, service, cap, all_upper_delay=False):
    if all_upper_delay and (cap != 90 or day != 'thu'):
        raise ValueError('The all-upper sensitivity uses the V12 90-minute setting on Thursday.')
    variant = 'allplus30' if all_upper_delay else f'upper{cap}'
    key = f'{service}-{day}'
    folder = HERE / 'runs' / variant / key
    folder.mkdir(parents=True, exist_ok=True)
    if (folder/'summary.json').is_file():
        return
    read, save = official.field.read, official.field.save_json
    baseline = read(V12/'runs/candidate'/key/'summary.json')
    weekday = official.prior.DAYS[day]
    bundle, _, donors, _ = official.prior.timing.inputs(weekday, service)
    official.spread_release(bundle, weekday, donors, official.prior.timing)
    official.apply_stays(bundle, weekday, donors, official.prior.timing, 90)
    assert official.signature(bundle, weekday, True) == baseline['departure_identity']
    strata = treatment(bundle, weekday, donors, cap, all_upper_delay)
    assert official.signature(bundle, weekday, False) == baseline['identity']
    bundle.update(terminal_service_treatment=True, single_line=True,
                  transitions=read(V12/'terminal_transitions.json'))
    common = bundle['prepared']['common']
    common['candidate_id'] = common['data_version'] = MODEL
    engine = official.engine
    engine.WORK = engine.OUT = engine.base.OUT = folder
    with (folder/'run.log').open('w', encoding='utf-8') as log, contextlib.redirect_stdout(log):
        data = engine.simulate(bundle, weekday, service)
    valid = official.check(bundle, service, weekday, day, folder, donors)
    assert valid['status'] == 'PASS'
    original = read(V12/'viewer-data'/f'{key}.json.gz')
    def inventory(replay):
        return sorted((e[0], e[1], e[2], e[3], e[11], e[12]) for e in replay['events'])
    assert inventory(data) == inventory(original)
    assert list(map(tuple, data['terminal_presence'])) == list(map(tuple, original['terminal_presence']))
    audit = read(folder/f'audit-{key}.json.gz')
    waits = official.prior.distribution(official.prior.physical_waits(audit))
    save(folder/'all_stop_waits.json', waits)
    report = data['report']
    assert all(math.isclose(report[k], baseline['daily'], abs_tol=1e-6) for k in ('input_weight', 'final_weight'))
    summary = dict(model=MODEL, condition=variant, service=service, day=day, strata=strata,
                   daily=report['input_weight'], identity=baseline['identity'],
                   departure_identity=official.signature(bundle, weekday, True), checks=valid['checks'],
                   unserved=report['unserved_trip_weight'], capacity_violations=report['capacity_violations'],
                   max_continuous_wait=max(r['max_continuous_wait_min'] for r in waits.values()),
                   over20_weight=sum(r['over_20_minute_weight'] for r in waits.values()),
                   **official.prior.metrics(data, audit, common, day))
    if day == 'tue':
        node = common['hot_nodes']['admin_daehak']
        t = official.field.seconds('15:18')
        summary['town_vehicle_ranges'] = []
        for n, vid, area, op, dep, clock in data['terminal_presence']:
            if n == node and op < t+60 and dep > t:
                curve = official.field.Curve([[s, load] for s, _, v, _, load, _ in data['preboard_events'] if v==vid])
                summary['town_vehicle_ranges'].append(dict(vehicle=vid, **curve.stats(max(op,t), min(dep,t+60))))
    save(folder/'summary.tmp', summary)
    (folder/'summary.tmp').replace(folder/'summary.json')
    print(key, variant, 'PASS', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('day', choices=official.prior.DAYS)
    parser.add_argument('service', choices=('peak','regular'))
    parser.add_argument('cap', choices=(60,90,120), type=int)
    parser.add_argument('--all-plus-30', action='store_true')
    args = parser.parse_args()
    run(args.day, args.service, args.cap, args.all_plus_30)
