"""Capacity-corrected university shuttle R candidate with the V11 event engine."""
import argparse
from pathlib import Path
import os
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / '261123191229'
sys.path.insert(0, str(PARENT))
from candidate import apply_choice, base, engine, load, load_v11
from validate import validate

MODEL = 'R261124094645'
ROUTE = 'shuttle-daehak'
CAPACITY = 44
EVIDENCE = {'route_id': ROUTE, 'max_passengers_per_vehicle': CAPACITY,
            'reported_by': 'user confirmed on 2026-11-24: 대학동행도 승객 44명',
            'tender': '20231243066-001, 붙임5 제3노선 및 붙임6 제3노선, 44인승 이상',
            'walk_assignment_parent': 'R261123191229', 'engine_base': 'V11 261110162302'}

def configure(common):
    info = common['route_info'][ROUTE]
    if info.get('capacity_periods'):
        raise ValueError('Review route-specific overrides before applying the corrected capacity')
    info['capacity'] = CAPACITY
    common['daehak_capacity'] = EVIDENCE
    common['candidate_id'] = MODEL

def write_common():
    common = load(PARENT/'common.json.gz')
    configure(common)
    base.packed(HERE/'common.json.gz', common)

def run(day, service, weather, rate, new_attempt=False):
    name = f'{weather}-{rate}-{service}-{base.DAYS[day]}'
    location = HERE/'runs'/name
    location.mkdir(parents=True, exist_ok=True)
    existing = sorted(location.glob('attempt-*/result.json'))
    if existing:
        saved = load(existing[-1])
        if saved['model_id'] != MODEL or saved['status'] != 'verified':
            raise ValueError(f'Invalid result: {existing[-1]}')
        return saved
    attempts = sorted(location.glob('attempt-*'))
    if attempts and not new_attempt:
        raise RuntimeError(f'Started case {name} already exists. Inspect before using --new-attempt.')
    out = location/f'attempt-{len(attempts)+1:02}'
    out.mkdir()
    bundle = load_v11()
    configure(bundle['prepared']['common'])
    converted, selection = apply_choice(bundle, load(PARENT/'walk_catalog.json'), day, rate/100)
    bundle['prepared']['common']['home_walk_trial_rate'] = rate
    base.save(out/'case.json', dict(model_id=MODEL, case=name, weekday=day, service=service, weather=weather,
                  evidence=EVIDENCE, selection=selection, engine_sha256=base.sha(engine.__file__),
                  source_sha256=base.sha(__file__), initial_choice_sha256=base.sha(PARENT/'candidate.py'),
                  validator_sha256=base.sha(PARENT/'validate.py'), walk_catalog_sha256=base.sha(PARENT/'walk_catalog.json')))
    engine.WORK = engine.OUT = base.OUT = out
    engine.simulate(bundle, day, service)
    result = validate(bundle, out, day, service, converted)
    assert result['candidate']['capacity'] == CAPACITY
    assert result['invariants']['capacity_violations'] == 0
    assert abs(result['invariants']['input_weight'] - result['invariants']['final_weight']) < 1e-5
    result.update(model_id=MODEL, case=name, selection=selection, capacity=CAPACITY)
    base.save(out/'result.tmp', result)
    os.replace(out/'result.tmp', out/'result.json')
    return result

if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--common', action='store_true')
    cli.add_argument('--day', choices=base.DAYS, default='월')
    cli.add_argument('--service', choices=('regular','peak'), default='regular')
    cli.add_argument('--weather', choices=('dry','rain'), default='dry')
    cli.add_argument('--rate', type=int, choices=range(101), metavar='0..100',
                     help='percent of originally direct shuttle riders, zero for V11 with corrected capacity')
    cli.add_argument('--new-attempt', action='store_true')
    args = cli.parse_args()
    if args.common:
        write_common()
    else:
        rate = args.rate if args.rate is not None else (45 if args.weather=='rain' else 50)
        summary = run(args.day,args.service,args.weather,rate,args.new_attempt)
        print(summary['model_id'], summary['case'], summary['status'], summary['candidate'],flush=True)
