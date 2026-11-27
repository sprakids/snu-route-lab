"""Fixed-date comparison. No fitting or tuning in evaluation; no network calls."""
from collections import defaultdict
from bisect import bisect_right
from pathlib import Path
import math
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'baseline_app'))
from continuity import Continuity
from travel_time import TravelTime
from gate_service import uniform_first
from extract_observations import campus_keys, clock
from empirical_transport import EmpiricalTransport


class FrozenTransit:
    """Both arms get the same observed passage; no ETA/queue truth is invented."""
    def __init__(self, at, previous=None):
        self.at, self.cache = at, {}
        if previous:
            self.cache[(previous['r'], previous['s'])] = {'last_values': [
                {'provided_at': previous['seen'], 'departure_at': previous['at']}]}

    def now(self):
        return self.at

    def interval(self, route, when):
        return route['interval_minutes']

    def in_service(self, route, when):
        return True  # Evaluation windows already lie between two observed events.


def metric(rows, candidate='candidate', baseline='baseline'):
    if not rows:
        return {'n': 0, 'available': False}
    errors = {k: [r[k]-r['truth'] for r in rows] for k in [candidate, baseline]}
    result = {'n': len(rows), 'available': True,
              'candidate_mae': statistics.mean(abs(e) for e in errors[candidate]),
              'baseline_mae': statistics.mean(abs(e) for e in errors[baseline]),
              'candidate_bias': statistics.mean(errors[candidate]),
              'baseline_bias': statistics.mean(errors[baseline]),
              'unique_trips_or_stop_clusters': len({r['cluster'] for r in rows}),
              'empirical_coverage': sum(r.get('covered', True) for r in rows)/len(rows)}
    groups = defaultdict(list)
    for r in rows:
        groups[r['cluster']].append(r)
    result['cluster_macro_candidate_mae'] = statistics.mean(statistics.mean(abs(r[candidate]-r['truth']) for r in rs) for rs in groups.values())
    result['cluster_macro_baseline_mae'] = statistics.mean(statistics.mean(abs(r[baseline]-r['truth']) for r in rs) for rs in groups.values())
    result['mae_improvement_fraction'] = 1-result['candidate_mae']/result['baseline_mae'] if result['baseline_mae'] else None
    return result


def compare(profile, extracted, derived, network):
    started = time.perf_counter()
    model = EmpiricalTransport(profile)
    continuity, travel = Continuity(), TravelTime()
    by_id = {r['id']: r for r in network['routes']}
    index = {(r['id'], s['seq']): i for r in network['routes'] for i, s in enumerate(r['stops'])}
    campus = campus_keys(network)
    by_stop = defaultdict(list)
    for p in extracted['passages']:
        if (p['r'], p['s']) in campus:
            by_stop[(p['r'], p['s'])].append(p)
    rows = {'headway': [], 'ride': [], 'crowd': [], 'gate': []}
    # Every two minutes inside fully bracketed observed intervals. These are
    # opportunities, not independent people and not a class-specific queue sample.
    for (rid, seq), events in sorted(by_stop.items()):
        events.sort(key=lambda p: p['at'])
        times = [p['at'] for p in events]
        if len(events) < 2:
            continue
        for at in range(math.ceil(times[0]/120)*120, int(times[-1]), 120):
            j = bisect_right(times, at)
            if j == 0 or j >= len(events) or not 15 <= events[j]['at']-events[j-1]['at'] <= 3600:
                continue
            previous = next((p for p in reversed(events[:j]) if p['seen'] <= at), None)
            if previous is None:
                continue
            route = by_id[rid]
            baseline = continuity.service(FrozenTransit(at, previous), route, index[(rid, seq)], at, live=True)
            if baseline is None:
                continue
            base = baseline['departure_at']-at
            estimate = model.headway_wait(rid, seq, at, at, last_passage=previous['at'])
            point = estimate['seconds'] if estimate else base
            rows['headway'].append({'r': rid, 's': seq, 'at': at, 'truth': events[j]['at']-at,
                                    'baseline': base, 'registered_half_headway': route['interval_minutes']*30,
                                    'candidate': point, 'covered': bool(estimate), 'cluster': rid+':'+str(seq)})
    for sample in derived['rides']:
        rid, a, b = sample['r'], sample['a'], sample['b']
        if (rid, a) not in campus:
            continue
        base = travel.estimate(by_id[rid], index[(rid, a)], index[(rid, b)], sample['at'], {}, False)
        if not base.get('available'):
            continue
        p = model.ride_time(rid, a, b, sample['at'], sample['at'])
        rows['ride'].append({'r': rid, 'a': a, 'b': b, 'at': sample['at'], 'truth': sample['seconds'],
                             'baseline': base['seconds'], 'candidate': p['seconds'] if p else base['seconds'],
                             'covered': bool(p), 'cluster': sample['trip']})
    for sample in derived['transitions']:
        rid, a, b = sample['r'], sample['a'], sample['b']
        if (rid, b) not in campus:
            continue
        # Previous label is supplied at its actual capture time, before target.
        asof = sample['source_seen']
        base = continuity.predict_crowd(by_id[rid], index[(rid, b)], sample['at'], asof,
                                        {'provided_at': sample['source_at'], 'crowd_cost': sample['g0']}, a, True)
        p = model.crowd(rid, b, sample['at'], asof, grade=sample['g0'], source_seq=a, observed_at=sample['source_at'])
        point = p['estimate'] if p else base['crowd_estimate']
        if point is None or base['crowd_estimate'] is None:
            continue
        rows['crowd'].append({'r': rid, 's': b, 'at': sample['at'], 'bucket': sample['bucket'],
                              'truth': sample['g1'], 'baseline': base['crowd_estimate'], 'candidate': point,
                              'persistence': sample['g0'], 'covered': bool(p), 'cluster': sample['trip'],
                              'candidate_congested': (p['congested_probability'] >= .5) if p else base['crowd_estimate'] >= 2,
                              'baseline_congested': base['crowd_estimate'] >= 2})
    events = [x for x in derived['gate_events'] if x['full'] is not True]
    events.sort(key=lambda p: (p['at'], p['r']))
    times = [p['at'] for p in events]
    eligible = sorted({x['r'] for x in profile['gate_events']})
    if len(events) >= 2 and eligible:
        for at in range(math.ceil(times[0]/120)*120, int(times[-1]), 120):
            j = bisect_right(times, at)
            if j == 0 or j >= len(events) or not 0 < times[j]-times[j-1] <= 3600:
                continue
            previous = next((p for p in reversed(events[:j]) if p['seen'] <= at), None)
            if previous is None:
                continue
            hs = [continuity.headway(r, next(s['seq'] for s in by_id[r]['stops'] if s['id'] == '120000029'),
                                     at, at, by_id[r]['interval_minutes']*60)[0] for r in eligible]
            base, probabilities = uniform_first(hs)
            p = model.gate_wait(eligible, at, at, last_passage=previous['at'])
            rows['gate'].append({'r': 'joint_gate', 'at': at, 'truth': times[j]-at, 'baseline': base,
                                 'candidate': p['seconds'] if p else base, 'covered': bool(p),
                                 'cluster': clock(at).strftime('%H')})
    report = {component: metric(values) for component, values in rows.items()}
    report['headway']['registered_half_headway'] = metric(rows['headway'], baseline='registered_half_headway')
    c = rows['crowd']
    if c:
        positive = [r for r in c if r['truth'] >= 2]
        report['crowd'].update({'persistence_comparison': metric(c, baseline='persistence'),
                                'congested_labels': len(positive),
                                'candidate_congestion_miss_rate': sum(not r['candidate_congested'] for r in positive)/len(positive) if positive else None,
                                'baseline_congestion_miss_rate': sum(not r['baseline_congested'] for r in positive)/len(positive) if positive else None})
    for component, values in rows.items():
        report[component]['by_route'] = {r: metric([x for x in values if x['r'] == r]) for r in sorted({x['r'] for x in values})}
    result = {'date': extracted['day'], 'metrics': report, 'quality': extracted['quality'],
              'elapsed_seconds': time.perf_counter()-started, 'new_provider_calls': 0,
              'operating_model_replaced': False,
              'baseline_scope': 'Frozen local Continuity/TravelTime and independent-uniform gate; no live shared operations/ETAs or actual queue labels',
              'sample_unit': 'correlated prediction targets, not independent travelers or queue observations'}
    return result, rows


def acceptance(report):
    accepted = {}
    for name, m in report['metrics'].items():
        ok = bool(m.get('available') and m.get('empirical_coverage', 0) >= .1 and
                  m['candidate_mae'] < m['baseline_mae'] and
                  m['cluster_macro_candidate_mae'] <= m['cluster_macro_baseline_mae'])
        if name == 'headway':
            ok = ok and m['registered_half_headway'].get('candidate_mae', math.inf) < m['registered_half_headway'].get('baseline_mae', 0)
        if name == 'crowd':
            ok = (ok and m.get('congested_labels', 0) >= 20 and
                  m['persistence_comparison']['candidate_mae'] < m['persistence_comparison']['baseline_mae'] and
                  m['candidate_congestion_miss_rate'] <= m['baseline_congestion_miss_rate'])
        accepted[name] = bool(ok)
    return accepted
