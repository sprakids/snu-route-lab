"""V12 two-factor sensitivity for upper-campus departures and first boarding choice."""
from bisect import bisect_left
from collections import Counter, defaultdict
import argparse
import contextlib
from functools import lru_cache
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
V12 = HERE.parent / '261125170855'
sys.path.insert(0, str(V12))
import simulate as official

UPPER = {'300', '301', '302'}
TARGET = '120000173'
RAIL = 'gwanaksan_4411'
E = official.engine
timing = official.prior.timing
read, save = official.field.read, official.field.save_json


def first_target(plan, common):
    if not plan[6]:
        return False
    first = plan[6][0]
    stops = common['city_route_stops'].get(first['rid'])
    return bool(stops and stops[first['board']]['id'] == TARGET)


def route_choices(bundle, plans, day, service):
    common = bundle['prepared']['common']
    scales = bundle['walk_scales']
    destinations = bundle['destination_keys']
    groups = defaultdict(list)
    for i, p in enumerate(plans):
        dest = destinations[str(p[0])]
        if p[1] in UPPER and dest != RAIL:
            point = tuple(common['paths'][p[5][0]][0])
            groups[p[1], point, dest, int(p[4]//1800)].append(i)

    @lru_cache(maxsize=None)
    def clocks(rid, board):
        info = common['route_info'][rid]
        times = E.planned_departures(info['plan']) if info.get('city') else E.base.dispatches(rid, service)
        offset = info.get('origin_to_modeled_first_stop_seconds',0.) + info['offsets'][board] - info['offsets'][info['anchor']]
        return sorted(t+offset for t in times if t+offset <= E.END)

    def viable(t, donor, ratio):
        t += donor[5][1]*ratio
        for s in donor[6]:
            schedule = clocks(s['rid'], s['board'])
            i = bisect_left(schedule,t+20)
            if i == len(schedule):
                return False
            offsets = common['route_info'][s['rid']]['offsets']
            t = schedule[i]+offsets[s['alight']]-offsets[s['board']]+s['next_walk'][1]*ratio
        return t <= E.END

    changes = {}
    for group in groups.values():
        donors = [plans[i] for i in group if first_target(plans[i], common)]
        if not donors or len(donors) == len(group):
            continue
        p0 = sum(p[3] for p in donors)/sum(plans[i][3] for i in group)
        # Raising odds p/(1-p) twofold requires converting p/(1+p)
        # of those who originally chose a different first boarding point or mode.
        for i in group:
            p = plans[i]
            if first_target(p, common) or timing.uniform(f'upper-choice/{day}/{p[0]}') >= p0/(1+p0):
                continue
            options = []
            for d in donors:
                ratio = scales[str(p[0])]/scales[str(d[0])]
                if viable(p[4], d, ratio):
                    options.append((d,ratio))
            if not options:
                continue
            ticket = timing.uniform(f'upper-route/{day}/{p[0]}')*sum(d[3] for d,_ in options)
            for d,ratio in options:
                ticket -= d[3]
                if ticket <= 0:
                    break
            path,seconds = d[5]
            changes[i] = ([path,seconds*ratio], E.scaled_stages(d[6],ratio))
    return changes


def generation(plans, course_ids, courses, destinations):
    # Leave the rail experiment's reserved population untouched. Balance within
    # each destination and scheduled class-end hour so regional growth alone is tested.
    mass = Counter()
    for i,p in enumerate(plans):
        mass[course_ids[i]] += p[3]
    proposed, donors = Counter(), Counter()
    details = []
    for i,p in enumerate(plans):
        course_id = course_ids[i]
        course = courses[course_id]
        prob = mass[course_id]/course['enrollment']
        assert 0 < prob <= 1+1e-8
        dest = destinations[str(p[0])]
        cell = (course['end_minute']//60, dest)
        gain = 0.
        if dest != RAIL:
            if p[1] in UPPER:
                gain = p[3]*(2/(1+prob)-1)
                proposed[cell] += gain
            else:
                donors[cell] += p[3]
        details.append((cell,gain))
    out = []
    for p,(cell,gain) in zip(plans,details):
        amount = min(proposed[cell], donors[cell]*(1-1e-8))
        if gain:
            weight = p[3]+gain*amount/proposed[cell]
        elif p[1] not in UPPER and donors[cell] and cell[1] != RAIL:
            weight = p[3]*(1-amount/donors[cell])
        else:
            weight = p[3]
        assert weight > 0
        out.append(weight)
    return out


def inputs(day_code, service, variant):
    weekday = official.prior.DAYS[day_code]
    bundle,_,donors,_ = timing.inputs(weekday, service)
    official.spread_release(bundle,weekday,donors,timing)
    official.apply_stays(bundle,weekday,donors,timing,90)
    reference = read(V12/'runs/candidate'/f'{service}-{day_code}'/'summary.json')
    assert official.signature(bundle,weekday,True) == reference['departure_identity']
    plans = bundle['prepared']['plans'][weekday]
    common = bundle['prepared']['common']
    dest = bundle['destination_keys']
    courses = timing.ref.ref.class_events(timing.ref.load(timing.ref.ref.COURSES))
    ids = [(donors.get(p[0],p[0])-1)//48 for p in plans]
    changes = route_choices(bundle,plans,weekday,service) if variant in ('choice','both') else {}
    weights = generation(plans,ids,courses,dest) if variant in ('origin','both') else [p[3] for p in plans]
    cells = Counter()
    class_mass = Counter()
    stats = Counter()
    upper_ids = set()
    for i,p in enumerate(plans):
        w = weights[i]
        c = courses[ids[i]]
        assert c['weekday'] == weekday and str(c['building']) == p[1]
        class_mass[ids[i]] += w
        cells[c['end_minute']//60,dest[str(p[0])]] += w-p[3]
        candidate = [*p[:3],w,p[4],*changes.get(i,p[5:])]
        if p[1] in UPPER:
            upper_ids.add(p[0])
            stats['upper_v12'] += p[3]
            stats['upper_r'] += w
            stats['first_target_v12'] += p[3]*first_target(p,common)
            stats['first_target_r'] += w*first_target(candidate,common)
        if i in changes:
            assert first_target(candidate,common) and not first_target(p,common)
            assert common['paths'][p[5][0]][0] == common['paths'][candidate[5][0]][0]
            stats['switch_weight'] += w
        if dest[str(p[0])] == RAIL:
            assert candidate == list(p)
        plans[i] = candidate
    assert max(abs(x) for x in cells.values()) < 1e-6
    assert all(m <= courses[k]['enrollment']+1e-6 for k,m in class_mass.items())
    bundle.update(terminal_service_treatment=True, single_line=True, transitions=read(V12/'terminal_transitions.json'))
    common['candidate_id'] = common['data_version'] = 'R'+HERE.name
    return bundle, donors, stats, upper_ids, reference


def realized(audit,common,upper_ids):
    counts = Counter()
    for person in audit['legs']:
        if person['id'] not in upper_ids:
            continue
        w = person['weight']
        counts['upper_mass'] += w
        vehicles = [leg for leg in person['legs'] if leg[0]==3]
        def is_target(leg):
            node = common['nodes'][leg[4]]
            return node.get('city') and node.get('stop_id') == TARGET
        if vehicles and is_target(vehicles[0]):
            counts['first_board_mass'] += w
        if any(is_target(leg) for leg in vehicles):
            counts['ever_board_mass'] += w
    return counts


def run(day,service,variant):
    key = f'{service}-{day}'
    folder = HERE/'runs'/variant/key
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/'summary.json').exists():
        return
    weekday = official.prior.DAYS[day]
    bundle,donors,stats,upper_ids,base = inputs(day,service,variant)
    common = bundle['prepared']['common']
    E.WORK = E.OUT = E.base.OUT = folder
    with (folder/'run.log').open('w',encoding='utf-8') as log, contextlib.redirect_stdout(log):
        data = E.simulate(bundle,weekday,service)
    valid = official.check(bundle,service,weekday,day,folder,donors)
    assert valid['status']=='PASS'
    baseline = read(V12/'viewer-data'/f'{key}.json.gz')
    def supply(d):
        return sorted((e[0],e[1],e[2],e[3],e[11],e[12]) for e in d['events'])
    assert supply(data)==supply(baseline)
    assert list(map(tuple,data['terminal_presence']))==list(map(tuple,baseline['terminal_presence']))
    audit = read(folder/f'audit-{key}.json.gz')
    result = realized(audit,common,upper_ids)
    original = realized(read(V12/'runs/candidate'/key/f'audit-{key}.json.gz'),common,upper_ids)
    assert abs(result['upper_mass']-stats['upper_r'])<1e-6 and abs(original['upper_mass']-stats['upper_v12'])<1e-6
    waits = official.prior.distribution(official.prior.physical_waits(audit))
    save(folder/'all_stop_waits.json',waits)
    rpt = data['report']
    assert all(abs(rpt[k]-base['daily'])<1e-6 for k in ('input_weight','final_weight'))
    summary = dict(day=day,service=service,condition=variant,daily=base['daily'],design=stats,
                   upper_actual=result,upper_actual_v12=original,checks=valid['checks'],
                   over20_weight=sum(r['over_20_minute_weight'] for r in waits.values()),
                   max_continuous_wait=max(r['max_continuous_wait_min'] for r in waits.values()),
                   unserved=rpt['unserved_trip_weight'], capacity_violations=rpt['capacity_violations'],
                   **official.prior.metrics(data,audit,common,day))
    if day=='tue':
        n=common['hot_nodes']['admin_daehak']
        t=official.field.seconds('15:18')
        summary['town_vehicle_ranges']=[]
        for node,vid,area,op,dep,clock in data['terminal_presence']:
            if node==n and op<t+60 and dep>t:
                curve=official.field.Curve([[s,w] for s,_,v,_,w,_ in data['preboard_events'] if v==vid])
                summary['town_vehicle_ranges'].append(dict(vehicle=vid,**curve.stats(max(op,t),min(dep,t+60))))
    save(folder/'summary.tmp',summary)
    (folder/'summary.tmp').replace(folder/'summary.json')
    print(day,service,variant, 'PASS',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('day',choices=official.prior.DAYS)
    parser.add_argument('service',choices=('peak','regular'))
    parser.add_argument('variant',choices=('origin','choice','both'))
    args=parser.parse_args()
    run(args.day,args.service,args.variant)
