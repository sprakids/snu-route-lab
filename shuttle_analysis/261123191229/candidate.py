"""R261123191229: apply a destination-specific initial walking choice to V11 plans."""
from collections import defaultdict
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import math
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SIM = HERE.parent / 'simulation_viewer_2026-11-07'
V11 = SIM / 'peak_pair_correction_2026-11-10'
BASE_ID = '261110162302'
MODEL_ID = 'R261123191229'
sys.path[:0] = [str(V11), str(SIM)]
import capacity_model as base
import engine

def load(path):
    if path.suffix == '.gz':
        with gzip.open(path, 'rt', encoding='utf8') as stream:
            return json.load(stream)
    return json.loads(path.read_bytes())

def load_v11():
    manifest = load(V11 / 'independent_verification.json')
    assert manifest['status'] == 'PASS'
    for name, key in [('engine.py', 'model_sha256'), ('prepared.json.gz', 'prepared_sha256'),
                      ('capacity_policy.py', 'capacity_policy_sha256')]:
        assert base.sha(V11 / name) == manifest[key]
    assert manifest['model_sha256'] == '987c5280b19ad977039881dd5fb9856d054ba47cd7f5173b5f1085cbaf0802d3'
    assert manifest['prepared_sha256'] == '08d92c334000990d00c843a51efe9cdb49ca145291421f4cd39b56dbb8492852'
    assert Path(engine.__file__).resolve() == V11 / 'engine.py'
    return load(V11 / 'prepared.json.gz')

def eligible(plan, bundle):
    return (bundle['destination_keys'][str(plan[0])] == 'daehak' and bool(plan[6])
            and plan[6][0]['rid'] == 'shuttle-daehak' and plan[6][0]['board'] == 0)

def build_catalog(bundle):
    common = bundle['prepared']['common']
    paths = common['paths']
    home = tuple(common['destinations']['daehak'])
    origins = sorted({tuple(paths[p[5][0]][0]) for plans in bundle['prepared']['plans'].values()
                      for p in plans if eligible(p, bundle)})
    pedestrian = base.module('v11_pedestrian', SIM / 'model_snapshot/engine/simulate_stop_inflow.py')
    graph = pedestrian.WalkingGraph(load(SIM / 'model_snapshot/app/data/walking_osm.json'))
    walker = pedestrian.MatrixWalker(graph, [*origins, home])
    existing = {tuple(path[0]): i for i, path in enumerate(paths) if path and tuple(path[-1]) == home}
    added = []
    rows = []
    for origin in origins:
        walk = walker.walk(origin, home)
        if not walk:
            raise ValueError(f'Unroutable pedestrian origin: {origin}')
        if origin in existing:
            pid = existing[origin]
        else:
            start = walker.snaps[origin][0]
            end = walker.snaps[home][0]
            parents = graph.tree(start)[1]
            chain = [end]
            while chain[-1] != start:
                chain.append(parents[chain[-1]][0])
            path = [list(origin), *[graph.nodes[n] for n in reversed(chain)], list(home)]
            pid = len(paths) + len(added)
            added.append(path)
        rows.append(dict(origin=origin, path=pid, meters=walk['meters'], seconds=walk['seconds']))
    return dict(base_id=BASE_ID, original_path_count=len(paths), routes=rows, added_paths=added)

def target_probabilities(weights, target):
    # The intercept sets a scenario mean in the eligible pool. No queue counts enter it.
    if target in (0, 1):
        return {m: target for m in weights}
    distances = {m: max(0, m-500)/1000 for m in weights}
    lo, hi = -50., max(distances.values()) + 50.
    mass = math.fsum(weights.values())
    for _ in range(64):
        mid = (lo+hi)/2
        probs = {m: 1/(1+math.exp(d-mid)) for m, d in distances.items()}
        if math.fsum(weights[m]*p for m,p in probs.items()) < target*mass:
            lo = mid
        else:
            hi = mid
    return {m: 1/(1+math.exp(d-(lo+hi)/2)) for m,d in distances.items()}

def apply_choice(bundle, catalog, day, target):
    if not 0 <= target <= 1:
        raise ValueError('target must range from 0 to 1')
    prepared = bundle['prepared']
    paths = prepared['common']['paths']
    assert len(paths) == catalog['original_path_count']
    paths.extend(catalog['added_paths'])
    routes = {tuple(r['origin']):r for r in catalog['routes']}
    plans = prepared['plans'][day]
    candidates = []
    weights = defaultdict(float)
    for index, plan in enumerate(plans):
        if eligible(plan, bundle):
            route = routes[tuple(paths[plan[5][0]][0])]
            weights[route['meters']] += plan[3]
            candidates.append((index, plan, route))
    probs = target_probabilities(weights, target)
    converted = {}
    total_walk_before = math.fsum(p[3] for p in plans if not p[6] and bundle['destination_keys'][str(p[0])]=='daehak')
    destination_mass = math.fsum(p[3] for p in plans if bundle['destination_keys'][str(p[0])]=='daehak')
    for index, plan, route in candidates:
        draw = int.from_bytes(hashlib.sha256(f'{MODEL_ID}/first-walk/{plan[0]}'.encode()).digest()[:8], 'big')/2**64
        if draw < probs[route['meters']]:
            uid = plan[0]
            duration = route['seconds'] * bundle['walk_scales'][str(uid)]
            plans[index] = [*plan[:5], [route['path'], duration], []]
            converted[uid] = (plan[3], route['path'], duration)
    source_mass = math.fsum(weights.values())
    moved = math.fsum(r[0] for r in converted.values())
    return converted, dict(eligible_mass=source_mass, target=target, realized_fraction=moved/source_mass,
                           converted_mass=moved, destination_mass=destination_mass,
                           first_daehak_shuttle_fraction=(source_mass-moved)/destination_mass,
                           walk_only_fraction=(total_walk_before+moved)/destination_mass)

def prepare_catalog():
    b = load_v11()
    catalog = build_catalog(b)
    common = load(SIM / 'public/data/capacity_v11/common.json')
    assert common['paths'] == b['prepared']['common']['paths']
    common['paths'].extend(catalog['added_paths'])
    common['candidate_id'] = MODEL_ID
    common['base_simulation'] = 'capacity_v11'
    base.packed(HERE / 'common.json.gz', common)
    base.save(HERE / 'walk_catalog.json', catalog)
    print('Verified routing catalog:', len(catalog['routes']), 'origins;', len(catalog['added_paths']), 'additional paths')

def run_case(day, service, weather, rate):
    if rate is None:
        rate = 45 if weather == 'rain' else 50
    if not 0 <= rate <= 100:
        raise ValueError('rate must range from 0 to 100 percent')
    output = HERE/'runs'/f'{weather}-{rate}-{service}-{base.DAYS[day]}'
    b = load_v11()
    catalog = load(HERE/'walk_catalog.json')
    converted, selection = apply_choice(b, catalog, day, rate/100)
    output.mkdir(parents=True, exist_ok=False)
    engine.WORK = engine.OUT = base.OUT = output
    base.save(output/'case.json', dict(model_id=MODEL_ID, base_id=BASE_ID, weather=weather, selection=selection,
                                     day=day, service=service, code_sha256=base.sha(__file__),
                                     catalog_sha256=base.sha(HERE/'walk_catalog.json')))
    data = engine.simulate(b, day, service)
    del data
    from validate import validate
    summary = validate(b, output, day, service, converted)
    base.save(output/'result.json', dict(selection=selection, **summary))

if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--prepare', action='store_true')
    cli.add_argument('--day', choices=list(base.DAYS), default='월')
    cli.add_argument('--service', choices=['regular','peak'], default='regular')
    cli.add_argument('--weather', choices=['dry','rain'], default='dry')
    cli.add_argument('--rate', type=int, help='scenario override, percent of originally direct shuttle group')
    args = cli.parse_args()
    if args.prepare:
        prepare_catalog()
    else:
        run_case(args.day, args.service, args.weather, args.rate)

