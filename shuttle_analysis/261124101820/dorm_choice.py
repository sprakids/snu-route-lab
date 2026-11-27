"""Additional initial walking choice on the V11 network for dorm-bound transit plans."""
from bisect import bisect_right
import hashlib
import math

DORMS = ('dorm_ug', 'dorm_grad')
DISTANCES = (500, 800, 1000, 1500, 2000, 3000)
SWITCH_PROBABILITY = (.30, .24, .15, .04, .015, .005)


def probability(meters):
    i = bisect_right(DISTANCES, meters)
    if not i:
        return SWITCH_PROBABILITY[0]
    if i == len(DISTANCES):
        return SWITCH_PROBABILITY[-1]
    a, b = DISTANCES[i-1:i+1]
    p, q = SWITCH_PROBABILITY[i-1:i+1]
    return p + (q-p)*(meters-a)/(b-a)


def build_catalog(bundle, daehak, pedestrian, network):
    common = bundle['prepared']['common']
    paths = common['paths'] + daehak['added_paths']
    ends = {d: tuple(common['destinations'][d]) for d in DORMS}
    pairs = {(tuple(paths[p[5][0]][0]), bundle['destination_keys'][str(p[0])])
             for plans in bundle['prepared']['plans'].values() for p in plans
             if p[6] and bundle['destination_keys'][str(p[0])] in DORMS}
    walker = pedestrian.MatrixWalker(network, sorted({origin for origin, _ in pairs} | set(ends.values())))
    lookup = {(tuple(path[0]), tuple(path[-1])): i for i, path in enumerate(paths) if path}
    rows, added, unavailable = [], [], []
    for origin, dorm in sorted(pairs):
        target = ends[dorm]
        route = walker.walk(origin, target)
        if route is None:
            unavailable.append([origin, dorm])
            continue
        key = origin, target
        if key not in lookup:
            start, end = walker.snaps[origin][0], walker.snaps[target][0]
            parents = network.tree(start)[1]
            chain = [end]
            while chain[-1] != start:
                chain.append(parents[chain[-1]][0])
            lookup[key] = len(paths) + len(added)
            added.append([list(origin), *[network.nodes[n] for n in reversed(chain)], list(target)])
        rows.append(dict(origin=origin, dorm=dorm, path=lookup[key], meters=route['meters'], seconds=route['seconds']))
    return dict(original_path_count=len(paths), routes=rows, added_paths=added, unavailable=unavailable)


def apply(bundle, catalog, day):
    paths = bundle['prepared']['common']['paths']
    assert len(paths) == catalog['original_path_count']
    paths.extend(catalog['added_paths'])
    lookup = {(tuple(row['origin']), row['dorm']): row for row in catalog['routes']}
    changed = {}
    plans = bundle['prepared']['plans'][day]
    for index, plan in enumerate(plans):
        uid = plan[0]
        dorm = bundle['destination_keys'][str(uid)]
        if not plan[6] or dorm not in DORMS:
            continue
        route = lookup.get((tuple(paths[plan[5][0]][0]), dorm))
        if route is None:
            continue
        draw = hashlib.sha256(f'dorm-walk-v1/{uid}'.encode()).digest()
        if int.from_bytes(draw[:8], 'big') / 2**64 < probability(route['meters']):
            seconds = route['seconds'] * bundle['walk_scales'][str(uid)]
            assert paths[route['path']][-1] == bundle['prepared']['common']['destinations'][dorm]
            plans[index] = [*plan[:5], [route['path'], seconds], []]
            changed[uid] = (plan[3], route['path'], seconds)
    return changed


def rates(bundle, day, changed):
    plans = bundle['prepared']['plans'][day]
    result = {}
    for dorm in DORMS:
        group = [p for p in plans if bundle['destination_keys'][str(p[0])] == dorm]
        total = math.fsum(p[3] for p in group)
        after = math.fsum(p[3] for p in group if not p[6])
        extra = math.fsum(p[3] for p in group if p[0] in changed)
        result[dorm] = dict(total=total, before=after-extra, after=after, additional=extra)
    return result
