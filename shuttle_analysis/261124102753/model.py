"""One weekday demand pool, including access to Gwanaksan (SNU) station 4411."""
from collections import Counter, defaultdict
from pathlib import Path
import hashlib
import math
import sys
import dorm_distance

HERE = Path(__file__).resolve().parent
MODEL = 'R261124102753'
EXPERIMENT = HERE.parent / 'sillim_r320_experiment_2026-11-24'
sys.path.insert(0, str(EXPERIMENT))
import experiment as rail

reference = rail.reference
load = rail.load
SAVE = reference.base.save
PACK = reference.base.packed
DAYS = reference.base.DAYS
HOURS = (15, 16, 17, 18)
REFERENCE = rail.REFERENCE
DEST = rail.DEST
DATA = HERE / 'viewer-data'
INPUTS = HERE / 'inputs'


def base_bundle(day):
    b = reference.load_v11()
    common = b['prepared']['common']
    reference.configure(common)
    changed, _ = reference.apply_choice(b, load(reference.PARENT/'walk_catalog.json'), day, reference.WALK_SHARE)
    common['dorm_choice'] = dorm_distance.metadata()
    changed.update(dorm_distance.apply(b, load(REFERENCE/'dorm_paths.json.gz'), day))
    profile = reference.apply_departures(b, reference.class_events(load(reference.COURSES)), day, changed)
    reference.cap_daily_departures(b, day, profile, changed)
    expected = REFERENCE/'runs'/f'regular-{DAYS[day]}'/'attempt-01'/'departure_profile.json'
    assert profile == load(expected)
    return b


def demand_candidates(b, day, common):
    plans = b['prepared']['plans'][day]
    source = [p for p in plans if b['destination_keys'][str(p[0])] in ('snu', 'nak')
              and 13*3600 <= p[4] < 19*3600]
    walks, options = rail.build_options(b, source)
    candidates = defaultdict(list)
    for p in source:
        start = tuple(common['paths'][p[5][0]][0])
        for (mode, (eta, route)) in rail.proposals(start, p[4], b['walk_scales'][str(p[0])],
                                                    walks, options[start]).items():
            if 15*3600 <= eta < 19*3600:
                hour = int(eta//3600)
                rank = hashlib.sha256(f'sillim-320/{mode}/{hour}/{p[0]}'.encode()).digest()
                candidates[mode, hour].append((rank, p, start, eta, route))
    return walks, candidates


def rail_plan(common, walks, shape_cache, origin, original, uid, weight, route, factor, alternatives):
    access_to = rail.TARGET
    paths = common['paths']
    stages = []
    if route:
        rid, board, alight, node, access_to, end, duration, *_ = route
        leave, seconds, _ = walks.path(end, rail.TARGET)
        ride_key = (rid, board, alight)
        if ride_key not in shape_cache:
            segments = common['route_info'][rid]['segments'][board:alight]
            shape_cache[ride_key] = len(paths)
            paths.append([xy for seg in segments for xy in paths[seg]])
        wait_key = ('wait', node)
        if wait_key not in shape_cache:
            shape_cache[wait_key] = len(paths)
            paths.append([access_to, access_to])
        stages.append(dict(rid=rid, board=board, alight=alight, ride_path=shape_cache[ride_key],
                           wait_path=shape_cache[wait_key], ride_seconds=duration,
                           next_walk=[leave,seconds*factor], choice_pool_locked=True))
        if math.isfinite(walks.time(access_to, rail.TARGET)):
            pid, sec, meters = walks.path(access_to, rail.TARGET)
            alternatives[f'{node}|{DEST}'] = [dict(kind='walk', name='관악산역까지 도보', walk=[pid,sec],
                                                    walk_meters=meters, stages=[])]
    pid, sec, _ = walks.path(origin,access_to)
    return [uid, original[1], DEST, weight, original[4], [pid, sec*factor], stages]


def build_inputs():
    INPUTS.mkdir(exist_ok=True)
    DATA.mkdir(exist_ok=True)
    card = load(rail.SCENARIO)
    observed = next(s for s in card['scenarios'] if s['scenario'] == 'base')
    shares = {}
    extra_paths = []
    summary = {}
    for day in '목월화수금':
        b = base_bundle(day)
        common = b['prepared']['common']
        paths = common['paths']
        base_count = len(paths)
        paths.extend(extra_paths)
        first_new = len(paths)
        walks, candidates = demand_candidates(b, day, common)
        next_id = max(map(int, b['walk_scales'])) + 1
        used, replacements, alternatives, shapes = set(), [], {}, {}
        strata = []
        for mode in ('city', 'first_rail'):
            for hour, anchor in zip(HOURS, observed['hourly_reference_counts'], strict=True):
                group = candidates[mode,hour]
                available = math.fsum(p[3] for _,p,*_ in group)
                city_anchor = card['student_share_assumption']*card['core_bus_connections'][str(hour)]
                thursday = city_anchor if mode == 'city' else anchor-city_anchor
                if day == '목':
                    shares[mode,hour] = thursday/available
                target = thursday if day == '목' else available * shares[mode,hour]
                left = target
                strata.append(dict(mode=mode, hour=hour, eligible=available, target=target,
                                   thursday_share=shares[mode,hour]))
                for _, p, start, eta, route in sorted(group,key=lambda row:row[0]):
                    if left <= 1e-8:
                        break
                    donor = p[0]
                    if donor in used:
                        continue
                    used.add(donor)
                    weight = min(left,p[3])
                    left -= weight
                    uid = donor
                    if p[3]-weight > 1e-8:
                        uid = next_id
                        next_id += 1
                    plan = rail_plan(common, walks, shapes, start, p, uid, weight, route,
                                     b['walk_scales'][str(donor)], alternatives)
                    replacements.append(dict(donor=donor, original_destination=p[2],
                                             expected_hour=hour, predicted_arrival=eta, plan=plan))
                if abs(left)>1e-7:
                    raise ValueError(f'Insufficient source demand: {day} {mode} {hour} ({left})')
        extra_paths.extend(paths[first_new:])
        mass = math.fsum(item['plan'][3] for item in replacements)
        assert math.isclose(mass,math.fsum(row['target'] for row in strata),abs_tol=1e-7)
        if day == '목':
            previous = load(EXPERIMENT/'run/assignments.json')
            assert [(r['id'],r['donor'],r['weight']) for r in previous] == [
                (r['plan'][0],r['donor'],r['plan'][3]) for r in replacements]
        PACK(INPUTS/f'{DAYS[day]}.json.gz',dict(model=MODEL, weekday=day, base_paths=base_count,
             original_hash=rail.fingerprint(b['prepared']['plans'][day]), replacements=replacements,
             alternatives=alternatives, strata=strata, station_demand=mass))
        summary[day] = dict(station_demand=mass, strata=strata)
        rail.Walks.path.cache_clear()
        rail.Walks.time.cache_clear()
        del walks, b, common, paths
    common = load(REFERENCE/'common.json.gz')
    assert len(common['paths']) == base_count
    common['paths'].extend(extra_paths)
    common['destinations'][DEST] = list(rail.TARGET)
    common['candidate_id'] = MODEL
    common['data_version'] = MODEL
    common['dorm_choice'] = dorm_distance.metadata()
    common['rail_access'] = dict(station='4411',destination=DEST, hours=list(HOURS),reference_date=card['date'],
                                 event='station marker arrival, proxy for fare gate entry', targets=summary)
    common['source_note'] += ' 기숙사 차량 계획의 도보 전환 확률은 500m 이내 80%, 1km 25%, 1.5km 4%. 신림선 관악산(서울대)역 접근을 포함. 목요일 카드자료 기반 320건, 나머지 평일은 적격 수요에 비례한 추정.'
    PACK(DATA/'common.json.gz',common)
    SAVE(INPUTS/'weekday_targets.json',summary)


def integrated_bundle(day, with_rail=True):
    b = base_bundle(day)
    prepared = b['prepared']
    common = prepared['common']
    patch = load(INPUTS/f'{DAYS[day]}.json.gz')
    plans = prepared['plans'][day]
    assert patch['model'] == MODEL and patch['weekday'] == day
    assert rail.fingerprint(plans) == patch['original_hash']
    shared = load(DATA/'common.json.gz')
    assert common['paths'] == shared['paths'][:patch['base_paths']]
    common['paths'] = shared['paths']
    if not with_rail:
        return b, patch, {}
    common['destinations'][DEST] = list(rail.TARGET)
    b['alternatives'].update(patch['alternatives'])
    indices = {p[0]: i for i,p in enumerate(plans)}
    original = {p[0]: p[3] for p in plans}
    donors = {}
    for assignment in patch['replacements']:
        uid, _, _, weight, start, *_ = plan = assignment['plan']
        donor = assignment['donor']
        i = indices[donor]
        source = plans[i]
        assert source[2] in ('snu','nak') and plan[1]==source[1] and start==source[4]
        if uid == donor:
            assert math.isclose(weight,source[3],abs_tol=1e-8)
            plans[i] = plan
        else:
            assert str(uid) not in b['walk_scales'] and 0<weight<source[3]
            plans[i] = [*source[:3],source[3]-weight,*source[4:]]
            plans.append(plan)
        b['walk_scales'][str(uid)] = b['walk_scales'][str(donor)]
        b['destination_keys'][str(uid)] = DEST
        donors[uid] = donor
    mass = Counter()
    for p in plans:
        mass[donors.get(p[0],p[0])] += p[3]
    assert mass.keys()==original.keys() and max(abs(v-original[k]) for k,v in mass.items())<1e-7
    return b, patch, donors
