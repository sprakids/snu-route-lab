"""Compare completed research replays with field records. No engine imports or runs."""
import argparse
import csv
import gzip
import hashlib
import json
import math
from bisect import bisect_right
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent.parent
OLD, NEW = '261124110718', '261124160531'
SERVICES = ('regular', 'peak')
DAYS = ('mon', 'tue', 'wed', 'thu', 'fri')
NODES = ('admin_snu', 'admin_daehak')


def read(path):
    with (gzip.open if path.suffix == '.gz' else open)(path, 'rt', encoding='utf-8-sig') as handle:
        return json.load(handle)


def file_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf8')


def write_csv(name, rows):
    with (HERE / name).open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def seconds(hhmm):
    h, m = map(int, hhmm.split(':'))
    return h * 3600 + m * 60


def hhmm(t):
    return f'{int(t)//3600:02d}:{int(t)//60%60:02d}'


class Curve:
    def __init__(self, rows):
        # Replays export the post-event state. Only the last update at a timestamp has duration.
        levels = {}
        previous = -math.inf
        for t, value, *_ in rows:
            assert t >= previous and value >= -1e-5, (t, previous, value)
            previous = t
            levels[t] = max(0., value)
        self.times = list(levels)
        self.levels = list(levels.values())

    def at(self, time):
        i = bisect_right(self.times, time)
        return self.levels[i-1] if i else 0.

    def stats(self, a, b, target=None):
        interior = self.times[bisect_right(self.times, a):bisect_right(self.times, b)]
        boundaries = [a, *(t for t in interior if t < b), b]
        spans = [(v-u, self.at(u)) for u, v in zip(boundaries, boundaries[1:])]
        def average(fn):
            return math.fsum(dt*fn(value) for dt, value in spans)/(b-a)
        out = dict(mean=average(lambda x:x), minimum=min(v for _, v in spans),
                   maximum=max(v for _, v in spans))
        if target is not None:
            lo, hi = target
            out['expected_abs_error'] = average(lambda x:max(lo-x, x-hi, 0.))
        return out


def field_records():
    records = []
    files = {}
    def source(date, filename):
        p = BASE / f'field_observations_2026-11-{date}' / filename
        files[p.relative_to(BASE).as_posix()] = file_hash(p)
        return read(p)
    for filename in ('queue_admin_snu_1653.json', 'queue_culture_1655.json', 'queue_snu_gate_1703.json'):
        r = source('09', filename)
        span = r.get('reported_queue_people_range') or [r['reported_queue_people']]*2
        records.append((r['observation_id'], 'mon', r['simulation_stop_key'], r['reported_time'], 'outside', span))
    r = source('10', 'queue_admin_snu_1523.json')
    records.append((r['observation_id'], 'tue', r['simulation_stop_key'], r['reported_queue_join_time'],
                    'outside', [r['people']['preferred_reported_outside_queue_count_including_observer']]*2))
    wait = r['durations']
    personal = dict(wait_seconds=wait['reported_pure_queue_wait_seconds'],
                    onboard_seconds=wait['reported_seconds_from_end_of_queue_wait_to_departure'],
                    combined_seconds=wait['derived_seconds_from_queue_join_to_departure'])
    immediate = source('23', 'boarding_admin_snu_1220_immediate.json')
    residual = source('23', 'full_departure_admin_daehak_1659.json')
    assert immediate['boarding_experience']['reported_wait_seconds'] is None
    for o in source('24', 'admin_shuttle_counts_1352_1518.json')['observations']:
        outside = o['measurement'] == 'outside_vehicle_boarding_queue'
        records.append((o['observation_id'], 'tue', 'admin_snu' if outside else 'admin_daehak',
                        o['time'], 'outside' if outside else 'onboard', [o['count_people']]*2))
    arrival_boarding = source('25', 'boarding_admin_snu_1600.json')
    records.append((arrival_boarding['observation_id'], 'wed', arrival_boarding['simulation_stop_key'],
                    arrival_boarding['reported_time'], 'outside', [arrival_boarding['outside_queue_before_boarding']]*2))
    return dict(records=records, files=files, personal=personal,
                immediate_id=immediate['observation_id'], immediate_time=immediate['reported_time'],
                residual_id=residual['observation_id'], residual_time=residual['reported_departure_time'],
                residual_count=residual['queue_observation']['reported_queue_people'],arrival_boarding=arrival_boarding)


def weighted(samples):
    if not samples:
        return None
    values = sorted(samples)
    mass = math.fsum(w for _, w in values)
    def quantile(q):
        cum = 0.
        for x, w in values:
            cum += w
            if cum >= q*mass:
                return x
        return values[-1][0]
    return dict(minimum=values[0][0], p10=quantile(.1), median=quantile(.5), p90=quantile(.9),
                maximum=values[-1][0], mean=math.fsum(x*w for x, w in values)/mass)


def riders(audit, events, node, start):
    by_vehicle = {(r[1], r[2]):r for r in events if r[1] == node}
    assert len(by_vehicle) == sum(r[1] == node for r in events)
    seen = []
    for w in audit['wait_audit']:
        entry = w['physical_stop_entry']
        if w['node'] != node or not start <= entry < start+60 or w['outcome'] != 'boarded':
            continue
        e = by_vehicle[(node, w['vehicle'])]
        wait, onboard = w['end']-entry, e[0]-w['end']
        assert min(wait, onboard) >= -1e-6
        seen.append((w['weight'], wait, onboard))
    return dict(boarded_mass=math.fsum(w for w, *_ in seen),
                outside_s=weighted([(s,w) for w,s,_ in seen]),
                onboard_s=weighted([(s,w) for w,_,s in seen]),
                combined_s=weighted([(x+y,w) for w,x,y in seen]),
                same_minute_boards_mass=math.fsum(w['weight'] for w in audit['wait_audit']
                    if w['node']==node and w['outcome']=='boarded' and start <= w['physical_stop_entry'] <= w['end'] < start+60))


def onboard_series(replay, node):
    rows = replay['onboard_wait_timeline']
    return Curve(rows[node] if isinstance(rows, list) else rows[str(node)])


def boarding_detail(replay, audit, key, node, curve, mark):
    departures = [e for e in replay['events'] if e[1]==node]
    if key == 'residual':
        same = [e for e in departures if mark <= e[0] < mark+60]
        # If the observation minute has no departure, choose the nearest scheduled phase, explicitly labelled.
        relevant = same or [min(departures, key=lambda e:min(abs(mark-e[0]), abs(mark+60-e[0])))]
    else:
        relevant = [e for e in departures if mark <= e[0] < mark+60]
    return [dict(time=e[0], time_matched=mark<=e[0]<mark+60, vehicle=e[2], capacity=e[3], boarded=e[6],
                 departing_load=e[7], compatible_left=e[8], event_physical_left=e[10],
                 ledger_outside_after=math.fsum(w['weight'] for w in audit['wait_audit']
                     if w['node']==node and w['arrival']<=e[0]<w['end']),
                 map_outside_after=curve.at(e[0])) for e in relevant]


def joined_trip_departures(replay, node, joined, durations):
    start = joined + durations['combined_seconds']
    end = start + 60
    doors = {vid:(opens, dep) for n,vid,opens,dep,_ in replay.get('door_windows',[]) if n==node}
    return [dict(departure=e[0],vehicle=e[2],opened=doors[e[2]][0] if e[2] in doors else None)
            for e in replay['events'] if e[1]==node and start<=e[0]<end]


def overlap(a, b, start, end):
    return max(0., min(b,end) - max(a,start))


def audit_counts(audit, replay, node, kind, a, b, public_mean):
    # An independent calculation integrates the time spent by people rather than the queue curve.
    if kind == 'outside':
        exposure = math.fsum(w['weight']*overlap(a,b,w['arrival'],w['end'])
                             for w in audit['wait_audit'] if w['node']==node)
    else:
        exposure = math.fsum(mass*overlap(a,b,t,dep)
                             for t,n,_,mass,_,dep in replay['preboard_events'] if n==node)
    mean = exposure/(b-a)
    # Public outdoor event timestamps are rounded to milliseconds and mass to 6 decimals.
    assert abs(public_mean-mean)<0.005,(node,kind,a,b,public_mean,mean)
    return mean


def summarize(model, evidence):
    folder = BASE / model
    source_files = dict(evidence['files'])
    def load(path):
        source_files[path.relative_to(BASE).as_posix()] = file_hash(path)
        return read(path)
    common = load(folder/'viewer-data/common.json.gz')
    assert common['candidate_id'] == 'R'+model
    hot = common['hot_nodes']
    count_rows, windows, episodes, checks = [], [], [], []
    for day in DAYS:
        for service in SERVICES:
            key = f'{service}-{day}'
            matches = sorted((folder/'runs'/key).glob('attempt-*/result.json'))
            results = [(path, read(path)) for path in matches]
            path, result = next((p, r) for p, r in reversed(results) if r.get('status')=='verified')
            source_files[path.relative_to(BASE).as_posix()] = file_hash(path)
            assert result['model']=='R'+model and result['day']==dict(zip(DAYS, '월화수목금'))[day] and result['service']==service
            checks.append(dict(model=model, service=service, day=day, demand=result['weekday_demand'],
                max_wait_min=result['max_continuous_wait'], over20_mass=result['over20_weight'],
                capacity_violations=result['capacity_violations'], unserved=result['unserved'],
                network_outside_person_min_1500_1900=math.fsum(result['stop_person_minutes']),
                admin_snu_outside_person_min_1500_1900=result['stop_person_minutes'][hot['admin_snu']],
                admin_daehak_outside_person_min_1500_1900=result['stop_person_minutes'][hot['admin_daehak']]))
            if not any(row[1] == day for row in evidence['records']):
                continue
            # Use a verified attempt's matching replay to avoid reading files being published by the producer.
            replay = load(path.parent / f'{key}.json.gz')
            audit = load(path.parent / f'audit-{key}.json.gz')
            assert replay['event_columns'][10] == 'physical_queue_left'
            assert len(replay['events']) == len(audit['events'])
            curves = {k:Curve(replay['queue_timeline'][hot[k]]) for k in (*NODES,'city_120000195','city_gate')}
            onboard = {k:onboard_series(replay, hot[k]) for k in NODES} if model == NEW else {}
            for obsid, weekday, k, ts, kind, target in evidence['records']:
                if day != weekday:
                    continue
                curve = curves[k] if kind == 'outside' else onboard.get(k)
                t = seconds(ts)
                stats = (curve.stats(t,t+60,target) if curve is not None else
                         dict(mean=None,minimum=None,maximum=None,expected_abs_error=None))
                independent_mean = audit_counts(audit,replay,hot[k],kind,t,t+60,stats['mean']) if curve else None
                if kind=='onboard' and curve is not None:
                    # The 17 people were counted in a single bus. Verify the node aggregate matches one bus.
                    relevant = [(vid,start,dep) for n,vid,start,dep,_ in replay['door_windows']
                                if n==hot[k] and overlap(t,t+60,start,dep)>0]
                    assert len(relevant) == 1, relevant
                    assert any(e[2]==relevant[0][0] and e[1]==hot[k] and abs(e[4]-e[5])<1e-6
                               for e in replay['events'])
                count_rows.append(dict(observation=obsid,model=model,service=service,stop=k,time=ts,metric=kind,
                                       observed_low=target[0],observed_high=target[1],ledger_mean=independent_mean,**stats))
                if obsid == evidence['arrival_boarding']['observation_id']:
                    node=hot[k]
                    if 'door_windows' in replay:
                        arrivals = sorted({op for n,_,op,_,_ in replay['door_windows'] if n==node})
                    else:
                        arrivals = sorted({e[0] for e in replay['events'] if e[1]==node})
                    episodes.append(dict(model=model,service=service,kind='arriving_vehicle_1600',
                        observation=obsid,boardable_arrivals_in_minute=[op for op in arrivals if t<=op<t+60],
                        opening_before=max(op for op in arrivals if op<t),
                        opening_after=min(op for op in arrivals if op>=t+60)))
            if day == 'tue':
                trips = audit['legs']
                departures = {}
                for a,b in [('14:48','15:48'),('15:00','15:16'),('15:16','15:19')]:
                    lo,hi=seconds(a),seconds(b)
                    departures[a+'-'+b] = math.fsum(r['weight'] for r in trips if lo<=r['start']<hi)
                episodes.append(dict(model=model,service=service,kind='campus_departures',departures_by_window=departures))
                for width, num_bins in [(60,61),(300,12),(3600,1)]:
                    for i in range(num_bins):
                        t = seconds('14:48')+i*width
                        for k in NODES:
                            for kind, curve in [('outside',curves[k]),('onboard',onboard.get(k))]:
                                stats = curve.stats(t,t+width) if curve is not None else dict(mean=None,minimum=None,maximum=None)
                                if width==3600 and curve is not None:
                                    audit_counts(audit,replay,hot[k],kind,t,t+width,stats['mean'])
                                windows.append(dict(model=model,service=service,stop=k,metric=kind,start=hhmm(t),
                                                    end_exclusive=hhmm(t+width),bin_seconds=width,**stats))
                episodes.append(dict(model=model,service=service,kind='individual_1523',
                    compatible_departures=joined_trip_departures(replay,hot['admin_snu'],seconds('15:23'),evidence['personal']),
                    **riders(audit,replay['events'],hot['admin_snu'],seconds('15:23'))))
            if day == 'mon':
                t = seconds(evidence['residual_time'])
                episodes.append(dict(model=model,service=service,kind='residual',departures=boarding_detail(
                    replay,audit,'residual',hot['admin_daehak'],curves['admin_daehak'],t)))
                t = seconds(evidence['immediate_time'])
                episodes.append(dict(model=model,service=service,kind='immediate',
                    **riders(audit,replay['events'],hot['admin_snu'],t),
                    departures=boarding_detail(replay,audit,'immediate',hot['admin_snu'],curves['admin_snu'],t),
                    queue=curves['admin_snu'].stats(t,t+60)))
            del audit, replay
    return dict(model=model,source_sha256=source_files,minute_counts=count_rows,windows=windows,episodes=episodes,checks=checks)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model', choices=[OLD,NEW], required=True)
    args=parser.parse_args()
    save_json(HERE / f'R{args.model}.json',summarize(args.model,field_records()))


if __name__=='__main__':
    main()
