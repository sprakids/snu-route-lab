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
from parent_transport import EmpiricalTransport as ParentTransport
import json


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


def classification_metrics(rows):
    positive = [r for r in rows if r['truth'] >= 2]
    negative = [r for r in rows if r['truth'] < 2]
    result = {'congested_labels': len(positive), 'noncongested_labels': len(negative),
              'common_classification_rule': 'published ordinal estimate >=1.5 for every arm'}
    for arm in ['candidate', 'baseline', 'persistence']:
        result[arm+'_congestion_miss_rate'] = statistics.mean(r[arm] < 1.5 for r in positive) if positive else None
        result[arm+'_false_positive_rate'] = statistics.mean(r[arm] >= 1.5 for r in negative) if negative else None
    return result


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
    result['candidate_p90_absolute_error'] = sorted(abs(e) for e in errors[candidate])[math.ceil(.9*len(rows))-1]
    intervals = [r for r in rows if r.get('range_seconds') is not None]
    result['observation_spread_coverage'] = (statistics.mean(r['range_seconds'][0] <= r['truth'] <= r['range_seconds'][1] for r in intervals)
                                            if intervals else None)
    return result


def compare(profile, extracted, derived, network):
    started = time.perf_counter()
    model = EmpiricalTransport(profile)
    parent_profile = json.loads((ROOT.parent/'empirical_transport_261116162001/artifacts/profile.json').read_text(encoding='utf-8'))
    parent = ParentTransport(parent_profile)
    same_data = ParentTransport({**profile, 'schema': 'snu_empirical_transport_candidate_v1'})
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
            recent = [p for p in events[:j] if p['seen'] <= at and at-p['at'] <= 3600]
            estimate = model.headway_wait(rid, seq, at, at, last_passage=previous['at'], recent_passages=recent)
            before = parent.headway_wait(rid, seq, at, at, last_passage=previous['at'])
            ablated = same_data.headway_wait(rid, seq, at, at, last_passage=previous['at'])
            point = round(estimate['seconds']) if estimate else round(before['seconds']) if before else base
            rows['headway'].append({'r': rid, 's': seq, 'at': at, 'truth': events[j]['at']-at,
                                    'baseline': round(before['seconds']) if before else base, 'legacy': base,
                                    'same_data_parent': round(ablated['seconds']) if ablated else base,
                                    'registered_half_headway': route['interval_minutes']*30,
                                    'range_seconds': estimate['range_seconds'] if estimate else None,
                                    'candidate': point, 'covered': bool(estimate), 'cluster': rid+':'+str(seq)})
    completed = defaultdict(list)
    for x in derived['rides']:
        completed[(x['r'], x['a'], x['b'])].append(x)
    for values in completed.values():
        values.sort(key=lambda x: x['known_at'])
    for sample in derived['rides']:
        rid, a, b = sample['r'], sample['a'], sample['b']
        if (rid, a) not in campus:
            continue
        base = travel.estimate(by_id[rid], index[(rid, a)], index[(rid, b)], sample['at'], {}, False)
        if not base.get('available'):
            continue
        history = completed[(rid, a, b)]
        known = [x for x in history if x['known_at'] <= sample['at'] and sample['at']-x['end'] <= 1800 and x['trip'] != sample['trip']][-5:]
        p = model.ride_time(rid, a, b, sample['at'], sample['at'], recent_travel=known)
        before = parent.ride_time(rid, a, b, sample['at'], sample['at'])
        ablated = same_data.ride_time(rid, a, b, sample['at'], sample['at'])
        rows['ride'].append({'r': rid, 'a': a, 'b': b, 'at': sample['at'], 'truth': sample['seconds'],
                             'baseline': round(before['seconds']) if before else base['seconds'],
                             'legacy': base['seconds'], 'same_data_parent': round(ablated['seconds']) if ablated else base['seconds'],
                             'candidate': round(p['seconds']) if p else round(before['seconds']) if before else base['seconds'],
                             'range_seconds': p['range_seconds'] if p else None,
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
        before = parent.crowd(rid, b, sample['at'], asof, grade=sample['g0'], source_seq=a, observed_at=sample['source_at'])
        ablated = same_data.crowd(rid, b, sample['at'], asof, grade=sample['g0'], source_seq=a, observed_at=sample['source_at'])
        point = p['estimate'] if p else base['crowd_estimate']
        if point is None or base['crowd_estimate'] is None:
            continue
        rows['crowd'].append({'r': rid, 's': b, 'at': sample['at'], 'bucket': sample['bucket'],
                              'truth': sample['g1'], 'baseline': round(before['estimate'], 3) if before else base['crowd_estimate'],
                              'legacy': base['crowd_estimate'], 'same_data_parent': round(ablated['estimate'], 3) if ablated else base['crowd_estimate'],
                              'candidate': point,
                              'persistence': sample['g0'], 'covered': bool(p), 'cluster': sample['trip'],
                              'candidate_congested': point >= 1.5,
                              'baseline_congested': (round(before['estimate'], 3) if before else base['crowd_estimate']) >= 1.5,
                              'candidate_probability': p['congested_probability'] if p else float(point >= 1.5),
                              'baseline_probability': before['congested_probability'] if before else float(base['crowd_estimate'] >= 1.5)})
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
            recent = [x for x in events[:j] if x['seen'] <= at and at-x['at'] <= 3600]
            p = model.gate_wait(eligible, at, at, last_passage=previous['at'], recent_passages=recent)
            before = parent.gate_wait(eligible, at, at, last_passage=previous['at'])
            ablated = same_data.gate_wait(eligible, at, at, last_passage=previous['at'])
            rows['gate'].append({'r': 'joint_gate', 'at': at, 'truth': times[j]-at, 'baseline': base,
                                 'legacy': base, 'same_data_parent': round(ablated['seconds']) if ablated else base,
                                 'candidate': round(p['seconds']) if p else round(before['seconds']) if before else base,
                                 'range_seconds': p['range_seconds'] if p else None,
                                 'cluster': clock(at).strftime('%H')})
            rows['gate'][-1]['baseline'] = round(before['seconds']) if before else base
    report = {component: metric(values) for component, values in rows.items()}
    report['headway']['registered_half_headway'] = metric(rows['headway'], baseline='registered_half_headway')
    c = rows['crowd']
    if c:
        positive = [r for r in c if r['truth'] >= 2]
        negative = [r for r in c if r['truth'] < 2]
        report['crowd'].update({'persistence_comparison': metric(c, baseline='persistence'),
                                'congested_labels': len(positive),
                                'candidate_congestion_miss_rate': sum(not r['candidate_congested'] for r in positive)/len(positive) if positive else None,
                                'baseline_congestion_miss_rate': sum(not r['baseline_congested'] for r in positive)/len(positive) if positive else None,
                                'persistence_congestion_miss_rate': sum(r['persistence'] < 1.5 for r in positive)/len(positive) if positive else None,
                                'candidate_false_positive_rate': sum(r['candidate_congested'] for r in negative)/len(negative) if negative else None,
                                'baseline_false_positive_rate': sum(r['baseline_congested'] for r in negative)/len(negative) if negative else None,
                                'persistence_false_positive_rate': sum(r['persistence'] >= 1.5 for r in negative)/len(negative) if negative else None,
                                'candidate_positive_mae': statistics.mean(abs(r['candidate']-r['truth']) for r in positive) if positive else None,
                                'persistence_positive_mae': statistics.mean(abs(r['persistence']-r['truth']) for r in positive) if positive else None,
                                'candidate_brier': statistics.mean((r['candidate_probability']-int(r['truth'] >= 2))**2 for r in c),
                                'baseline_brier': statistics.mean((r['baseline_probability']-int(r['truth'] >= 2))**2 for r in c),
                                'common_classification_rule': 'published ordinal estimate >=1.5 in EVERY arm; label categories>=2'})
        report['crowd'].update(classification_metrics(c))
    for component, values in rows.items():
        report[component]['by_route'] = {r: metric([x for x in values if x['r'] == r]) for r in sorted({x['r'] for x in values})}
        report[component]['same_data_parent_comparison'] = metric(values, baseline='same_data_parent')
        report[component]['legacy_comparison'] = metric(values, baseline='legacy')
    result = {'date': extracted['day'], 'metrics': report, 'quality': extracted['quality'],
              'elapsed_seconds': time.perf_counter()-started, 'new_provider_calls': 0,
              'operating_model_replaced': False,
              'baseline_scope': 'Direct parent R261116162001 primary; same-two-day-data v1 algorithm ablation and frozen local legacy secondary. No actual student/shuttle queues.',
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
            ok = (ok and m.get('congested_labels', 0) >= 20 and m.get('noncongested_labels', 0) >= 20 and
                  m['persistence_comparison']['candidate_mae'] < m['persistence_comparison']['baseline_mae'] and
                  m['candidate_congestion_miss_rate'] <= min(m['baseline_congestion_miss_rate'], m['persistence_congestion_miss_rate']) and
                  m['candidate_false_positive_rate'] <= min(m['baseline_false_positive_rate'], m['persistence_false_positive_rate'])+.02 and
                  m['candidate_positive_mae'] <= m['persistence_positive_mae']+.02)
        else:
            ok = ok and abs(m.get('candidate_bias', math.inf)) <= abs(m.get('baseline_bias', 0))+1
        accepted[name] = bool(ok)
    return accepted
