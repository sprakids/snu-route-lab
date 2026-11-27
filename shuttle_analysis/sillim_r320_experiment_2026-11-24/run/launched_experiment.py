"""Thursday finite-capacity counterfactual for station 4411. No production writes."""
import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REFERENCE = ROOT / '261124101820'
sys.path.insert(0, str(REFERENCE))
import run as reference

MODEL = 'R261124101959'
DAY = '목'
SERVICE = 'regular'
TARGET = (37.468964, 126.945242)
DEST = 'gwanaksan_4411'
SCENARIO = ROOT / 'sillim_ridership_2026-11-24/scenario_320.json'
SCOPE = ROOT / 'seoul_boardings_2026-11-10/stop_scope.json'
GRAPH = reference.SIM / 'model_snapshot/app/data/walking_osm.json'
BASELINE = REFERENCE / 'runs/regular-thu/attempt-01'
OUTPUT = HERE / 'run'
save = reference.base.save
load = reference.load


def prepared():
    bundle = reference.load_v11()
    reference.configure(bundle['prepared']['common'])
    changed, _ = reference.apply_choice(bundle, load(reference.PARENT / 'walk_catalog.json'), DAY, reference.WALK_SHARE)
    changed.update(reference.dorm_choice.apply(bundle, load(REFERENCE / 'dorm_paths.json.gz'), DAY))
    profile = reference.apply_departures(bundle, reference.class_events(load(reference.COURSES)), DAY, changed)
    reference.cap_daily_departures(bundle, DAY, profile, changed)
    assert profile == load(BASELINE / 'departure_profile.json')
    return bundle


def point(stop):
    return (stop['lat'], stop['lon'])


class Walks:
    def __init__(self, points, paths):
        mod = reference.base.module('sillim_walk', reference.SIM / 'model_snapshot/engine/simulate_stop_inflow.py')
        self.graph = mod.WalkingGraph(load(GRAPH))
        for n, edges in self.graph.edges.items():
            self.graph.edges[n] = [(other, meters / (.7 if steps else 4.8 / 3.6), meters, steps)
                                   for other, _, meters, steps in edges]
        self.snaps = mod.MatrixWalker(self.graph, points).snaps
        self.paths = paths

    @lru_cache(maxsize=None)
    def time(self, a, b):
        if a == b:
            return 0.
        start, gap_a = self.snaps[a]
        end, gap_b = self.snaps[b]
        if max(gap_a, gap_b) > 110:
            return math.inf
        return self.graph.tree(start)[0].get(end, math.inf) + (gap_a + gap_b) / (4.8 / 3.6)

    @lru_cache(maxsize=None)
    def path(self, a, b):
        seconds = self.time(a, b)
        assert math.isfinite(seconds)
        start, _ = self.snaps[a]
        end, _ = self.snaps[b]
        parents = self.graph.tree(start)[1]
        chain = [end]
        while chain[-1] != start:
            chain.append(parents[chain[-1]][0])
        line = [a, *(self.graph.nodes[n] for n in reversed(chain)), b]
        meters = sum(reference.base.distance(p, q) for p, q in zip(line, line[1:]))
        self.paths.append(line)
        return len(self.paths)-1, seconds, meters


def build_options(bundle, plans):
    p = bundle['prepared']
    c = p['common']
    nodes = c['nodes']
    core = {s['stop_id'] for s in load(SCOPE)['stops'] if s['zone'] == 'campus_core'}
    origins = {tuple(c['paths'][plan[5][0]][0]) for plan in plans}
    idx = {n['id']:i for i,n in enumerate(nodes)}
    services = []
    ends = set()
    for rid, info in c['route_info'].items():
        city = info.get('city', False)
        if not city and rid not in ('shuttle-41946', 'shuttle-41914'):
            continue
        route = p['routes'][rid]
        clocks = (reference.engine.planned_departures(info['plan']) if city
                  else reference.base.dispatches(rid, SERVICE))
        clocks = sorted(t + info.get('origin_to_modeled_first_stop_seconds', 0) - info['offsets'][info['anchor']]
                        for t in clocks)
        stops = route['stops']
        for b, entry in enumerate(stops[:info['n']]):
            key = f'{rid}|{b}'
            node = bundle['city_node_lookup'].get(key) if city else idx.get(key)
            if node is None or (city and entry['id'] not in core) or not entry.get('board_allowed', True):
                continue
            choices = []
            for j in range(b+1, min(b+info['n'], len(stops))):
                end = point(stops[j])
                ride = info['offsets'][j]-info['offsets'][b]
                if stops[j].get('alight_allowed', True) and ride <= 25*60 and reference.base.distance(end, TARGET) <= 850:
                    choices.append((j, end, ride))
                    ends.add(end)
            if choices:
                services.append((rid,b,node,point(nodes[node]),choices,[t+info['offsets'][b] for t in clocks],city))
    walks = Walks([*origins,*ends,*(point(n) for n in nodes),TARGET], c['paths'])
    valid = []
    for rid,b,node,entry,choices,clocks,city in services:
        for j,end,ride in choices:
            leave = walks.time(end, TARGET)
            if leave <= 12*60:
                valid.append((rid,b,j,node,entry,end,ride,leave,clocks,city))
    options = {}
    for start in sorted(origins):
        options[start] = []
        for row in valid:
            entry = row[4]
            if reference.base.distance(start, entry) > 1000:
                continue
            access = walks.time(start, entry)
            if access <= 15*60:
                options[start].append((access,row))
    return walks, options


def proposals(start, depart, factor, walks, choices):
    # For probable linked city trips require a campus city boarding. For first-paid
    # rail trips compare walking all the way and a free campus shuttle.
    best = {'first_rail':(depart+factor*walks.time(start,TARGET), None), 'city':(math.inf,None)}
    for access, row in choices:
        rid,b,j,node,entry,end,ride,leave,clocks,city = row
        i = bisect_left(clocks, depart+access*factor+20.)
        if i == len(clocks):
            continue
        eta = clocks[i] + ride + leave*factor
        group = 'city' if city else 'first_rail'
        if eta < best[group][0]:
            best[group] = (eta, row)
    return best


def fingerprint(obj):
    return hashlib.sha256(json.dumps(obj, separators=(',',':'),sort_keys=True).encode()).hexdigest()


def assign(bundle):
    pdata = bundle['prepared']
    c = pdata['common']
    paths = c['paths']
    original_paths = len(paths)
    plans = pdata['plans'][DAY]
    before = {p[0]:(p[1],p[4],p[3]) for p in plans}
    baseline_fingerprint = fingerprint(plans)
    source = [(i,p) for i,p in enumerate(plans) if bundle['destination_keys'][str(p[0])] in ('snu','nak')
              and 13*3600 <= p[4] < 19*3600]
    walks, options = build_options(bundle, [p for _,p in source])
    data = load(SCENARIO)
    base = next(s for s in data['scenarios'] if s['scenario']=='base')
    candidates = defaultdict(list)
    for i,p in source:
        orig = tuple(paths[p[5][0]][0])
        for g,(eta,row) in proposals(orig,p[4],bundle['walk_scales'][str(p[0])],walks,options[orig]).items():
            if 15*3600 <= eta < 19*3600:
                h = int(eta//3600)
                rank = hashlib.sha256(f'sillim-320/{g}/{h}/{p[0]}'.encode()).digest()
                candidates[g,h].append((rank,i,orig,eta,row))
    # Keep each donor exclusive, even if its two mode forecasts fall in different hours.
    # A fractional boundary group leaves its original remainder in place.
    used = set()
    new_ids = max(map(int,bundle['walk_scales'])) + 1
    donor_of = {}
    selected = []
    shapes = {}
    def add_shape(key, line):
        if key not in shapes:
            shapes[key] = len(paths)
            paths.append(line)
        return shapes[key]
    c['destinations'][DEST] = list(TARGET)
    for group in ('city','first_rail'):
        for hour, target in zip(data['hours'],base['hourly_reference_counts']):
            paid = data['student_share_assumption']*data['core_bus_connections'][str(hour)]
            left = paid if group=='city' else target-paid
            for _, i, start, eta, row in sorted(candidates[group,hour],key=lambda item:item[0]):
                if left <= 1e-8:
                    break
                plan = plans[i]
                if i in used:
                    continue
                used.add(i)
                old_uid = plan[0]
                original_dest = bundle['destination_keys'][str(old_uid)]
                amount = min(left,plan[3])
                left -= amount
                uid = old_uid
                partial = plan[3]-amount > 1e-8
                if partial:
                    uid = new_ids
                    new_ids += 1
                    plans[i] = [*plan[:3],plan[3]-amount,*plan[4:]]
                factor = bundle['walk_scales'][str(old_uid)]
                bundle['walk_scales'][str(uid)] = factor
                bundle['destination_keys'][str(uid)] = DEST
                donor_of[uid] = old_uid
                stages = []
                access_to = TARGET
                rid = None
                if row:
                    rid,b,j,node,entry,end,ride,leave,_,_ = row
                    access_to = entry
                    leave_id, _, _ = walks.path(end,TARGET)
                    info = c['route_info'][rid]
                    ride_path = add_shape((rid,b,j),[xy for seg in info['segments'][b:j] for xy in paths[seg]])
                    wait_path = add_shape(('wait',node),[entry,entry])
                    stages = [dict(rid=rid,board=b,alight=j,ride_path=ride_path,wait_path=wait_path,
                                   ride_seconds=ride,next_walk=[leave_id,leave*factor],choice_pool_locked=True)]
                    if math.isfinite(walks.time(entry,TARGET)):
                        pid,sec,meters = walks.path(entry,TARGET)
                        bundle['alternatives'][f'{node}|{DEST}'] = [
                            dict(kind='walk',name='관악산역까지 도보',walk=[pid,sec],walk_meters=meters,stages=[])]
                pid,sec,_ = walks.path(start,access_to)
                new_plan = [uid,plan[1],DEST,amount,plan[4],[pid,sec*factor],stages]
                if partial:
                    plans.append(new_plan)
                else:
                    plans[i] = new_plan
                selected.append(dict(id=uid,donor=old_uid,building=plan[1],old_dest=original_dest,
                    weight=amount,start=plan[4],expected_hour=hour,forecast_marker_time=eta,stratum=group,
                    route=rid, board=row[1] if row else None, alight=row[2] if row else None))
            assert abs(left)<1e-7,(group,hour,left)
    restored = Counter()
    for p in plans:
        donor = donor_of.get(p[0],p[0])
        assert (p[1],p[4]) == before[donor][:2]
        restored[donor] += p[3]
    assert set(restored)==set(before) and max(abs(v-before[k][2]) for k,v in restored.items())<1e-7
    assert math.isclose(sum(s['weight'] for s in selected),320)
    assert all(math.isclose(sum(s['weight'] for s in selected if s['expected_hour']==h),n) for h,n in zip(data['hours'],base['hourly_reference_counts']))
    reference.base.packed(OUTPUT/'added_paths.json.gz',dict(first_index=original_paths,paths=paths[original_paths:]))
    save(OUTPUT/'assignments.json',selected)
    receipts = {str(f.relative_to(ROOT)):reference.base.sha(f) for f in [
        SCENARIO,SCOPE,GRAPH,REFERENCE/'run.py',REFERENCE/'dorm_paths.json.gz',BASELINE/'case.json',
        BASELINE/'departure_profile.json',Path(reference.engine.__file__),Path(__file__)]}
    save(OUTPUT/'input_check.json',dict(reference=reference.MODEL,model=MODEL,day=DAY,service=SERVICE,
         total_weight=math.fsum(restored.values()),donor_weights_preserved=len(restored),
         station_snap_m=walks.snaps[TARGET][1],original_plan_hash=baseline_fingerprint,
         scenario_plan_hash=fingerprint(plans),supply_hash=fingerprint(c['route_info']),files=receipts))


def run_experiment():
    OUTPUT.mkdir(exist_ok=False)
    b = prepared()
    assign(b)
    reference.engine.WORK = reference.engine.OUT = reference.base.OUT = OUTPUT
    reference.engine.simulate(b, DAY, SERVICE)
    from validate import core
    core.WORK = core.OUT = OUTPUT
    save(OUTPUT/'independent_checks.json',core.check(b,SERVICE,DAY,'thu'))


if __name__ == '__main__':
    run_experiment()
