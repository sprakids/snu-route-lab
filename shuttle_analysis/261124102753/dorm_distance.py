"""Distance response for changing an initially vehicle-based dorm trip to walking."""
from math import exp, log
import hashlib

SHORT_RATE = .80
ONE_KM_RATE = .25
ONE_AND_HALF_KM_RATE = .04
DECAY = log(SHORT_RATE / ONE_KM_RATE)
EXPONENT = log(log(SHORT_RATE / ONE_AND_HALF_KM_RATE) / DECAY) / log(2)


def probability(meters):
    scaled_distance = max(0., meters - 500.) / 500.
    return SHORT_RATE * exp(-DECAY * scaled_distance ** EXPONENT)


def apply(bundle, catalog, day):
    paths = bundle['prepared']['common']['paths']
    assert len(paths) == catalog['original_path_count']
    paths.extend(catalog['added_paths'])
    routes = {(tuple(r['origin']),r['dorm']): r for r in catalog['routes']}
    plans = bundle['prepared']['plans'][day]
    converted = {}
    for i, p in enumerate(plans):
        uid = p[0]
        dest = bundle['destination_keys'][str(uid)]
        if not p[6] or dest not in ('dorm_ug','dorm_grad'):
            continue
        route = routes.get((tuple(paths[p[5][0]][0]), dest))
        if route is None:
            continue
        # Use the previous R's exact draw to isolate the effect of the distance curve.
        digest = hashlib.sha256(f'dorm-walk-v1/{uid}'.encode()).digest()
        if int.from_bytes(digest[:8],'big') / 2**64 < probability(route['meters']):
            seconds = route['seconds'] * bundle['walk_scales'][str(uid)]
            assert paths[route['path']][-1] == bundle['prepared']['common']['destinations'][dest]
            plans[i] = [*p[:5], [route['path'],seconds], []]
            converted[uid] = (p[3],route['path'],seconds)
    return converted


def metadata():
    return dict(destinations=['dorm_ug','dorm_grad'], denominator='initially vehicle-based dorm trips',
                curve='stretched exponential above 500 m', rate_through_500m=SHORT_RATE,
                rate_at_1000m=ONE_KM_RATE, rate_at_1500m=ONE_AND_HALF_KM_RATE,
                sampled={str(m): probability(m) for m in (0,500,800,1000,1500,2000,3000)})
