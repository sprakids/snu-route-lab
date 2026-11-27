"""A dated, opt-in transport candidate. Counts never become seats or student queues."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import json
import math
import statistics

KST = timezone(timedelta(hours=9))
SCHEMA = 'snu_empirical_transport_candidate_v1'


def hour(at):
    return datetime.fromtimestamp(at, KST).hour


def quantile(values, p):
    values = sorted(values)
    return values[max(0, math.ceil(p * len(values)) - 1)]


def summary(values):
    mean = statistics.mean(values)
    return {'n': len(values), 'mean_seconds': mean, 'median_seconds': statistics.median(values),
            'p10_seconds': quantile(values, .1), 'p90_seconds': quantile(values, .9),
            'cv': statistics.pstdev(values) / mean if mean else 0.}


def period_distance(a, b):
    return abs(a - b)  # No wrap across collection shutdown/midnight.


class EmpiricalTransport:
    def __init__(self, profile):
        if isinstance(profile, str):
            with open(profile, encoding='utf-8') as stream:
                profile = json.load(stream)
        if profile.get('schema') != SCHEMA:
            raise ValueError('Unrecognized transport profile')
        self.data = profile
        self.model_id = profile['model_id']
        self.heads, self.rides, self.trans, self.counts = (defaultdict(list) for _ in range(4))
        for x in profile['headways']:
            self.heads[(x['r'], x['s'])].append(x)
        for x in profile['rides']:
            self.rides[(x['r'], x['a'], x['b'])].append(x)
        for x in profile['transitions']:
            self.trans[(x['r'], x['g0'], x['bucket'])].append(x)
        for x in profile['grade_counts']:
            self.counts[x['r']].append(x)

    def usable(self, at, asof):
        cut = datetime.fromtimestamp(min(at, asof), KST).date().isoformat()
        target = datetime.fromtimestamp(at, KST)
        same_daytype = all((datetime.fromisoformat(day).weekday() < 5) == (target.weekday() < 5)
                           for day in self.data['dates'])
        return (bool(self.data['dates']) and all(day < cut for day in self.data['dates']) and
                same_daytype and 680 <= target.hour*60+target.minute <= 1390)

    def meta(self):
        return {'model_id': self.model_id, 'training_dates': self.data['dates'],
                'weekday_effect_identified': False,
                'time_basis': 'KST', 'calibrated_student_wait': False,
                'operating_model_replaced': False, 'shuttle_empirical_history': False}

    @staticmethod
    def cohort(rows, at, minimum=6):
        local = [x for x in rows if period_distance(x['h'], hour(at)) <= 1]
        if len(local) >= minimum:
            return local, 'same_direction_stop_three_hour_window'
        return (rows, 'same_direction_stop_pooled_hours') if len(rows) >= minimum else ([], 'insufficient_support')

    @staticmethod
    def residual(values, elapsed=None):
        if elapsed is not None:
            tail = [v-elapsed for v in values if v > elapsed]
            if len(tail) < 5:
                return None
            result = summary(tail)
            return {**result, 'seconds': result['mean_seconds'],
                    'range_seconds': [result['p10_seconds'], result['p90_seconds']],
                    'conditioned_elapsed_seconds': elapsed, 'residual_basis': 'empirical_survival_given_last_passage'}
        # Uniform time sampling within historical intervals, preserving length bias.
        # This is time-to-vehicle, not a queue wait for synchronized class cohorts.
        total = sum(values)
        if not total:
            return None
        def q(p):
            low, high = 0., max(values)
            for _ in range(32):
                mid = (low+high)/2
                survival = sum(max(0., v-mid) for v in values)/total
                if survival > 1-p:
                    low = mid
                else:
                    high = mid
            return (low+high)/2
        return {'seconds': sum(v*v for v in values)/(2*total), 'n': len(values),
                'range_seconds': [q(.1), q(.9)], 'conditioned_elapsed_seconds': None,
                'residual_basis': 'random_arrival_residual_not_student_queue'}

    def headway_wait(self, rid, seq, at, asof, *, last_passage=None):
        if not self.usable(at, asof):
            return None
        rows, cohort = self.cohort(self.heads[(rid, seq)], at)
        if not rows:
            return None
        elapsed = None
        if last_passage is not None:
            if not math.isfinite(last_passage) or last_passage > min(at, asof):
                return None
            elapsed = at-last_passage
        values = [x['seconds'] for x in rows]
        estimate = self.residual(values, elapsed)
        if estimate is None:
            return None
        return {**estimate, **self.meta(), 'cohort': cohort, 'headway': summary(values),
                'available': True, 'source': 'observed_stop_headway_distribution',
                'nominal_queue_delay_included': False, 'direction_key': [rid, seq]}

    def ride_time(self, rid, a, b, at, asof):
        if not self.usable(at, asof) or a >= b:
            return None
        rows, cohort = self.cohort(self.rides[(rid, a, b)], at, 5)
        if not rows:
            return None
        result = summary([x['seconds'] for x in rows])
        return {**result, **self.meta(), 'seconds': result['median_seconds'], 'available': True,
                'range_seconds': [result['p10_seconds'], result['p90_seconds']],
                'cohort': cohort, 'source': 'observed_directed_stop_passage_time',
                'stop_and_signal_delays_may_be_included': True, 'add_blanket_dwell_seconds': 0,
                'range_kind': 'historical_observation_spread_not_confidence_interval',
                'unique_trips': len({x['trip'] for x in rows})}

    def crowd(self, rid, target_seq, at, asof, *, grade=None, source_seq=None, observed_at=None):
        if not self.usable(at, asof):
            return None
        if grade is not None and (type(grade) not in (int, float) or grade not in (0, 1, 2, 3)):
            return None
        age = at-observed_at if observed_at is not None else None
        hops = target_seq-source_seq if source_seq is not None else None
        valid_last = (grade is not None and age is not None and observed_at <= min(at, asof)
                      and hops is not None and 0 <= hops <= 8 and 0 <= age <= 600)
        prior_rows = self.counts[rid]
        local = [x for x in prior_rows if x['s'] == target_seq and abs(x['h']-hour(at)) <= 1]
        prior_rows = local if sum(x['n'] for x in local) >= 8 else [x for x in prior_rows if abs(x['h']-hour(at)) <= 1]
        counts = [sum(x['n'] for x in prior_rows if x['g'] == k) for k in range(4)]
        n = sum(counts)
        if not valid_last and n < 8:
            return None
        probability = [(v+1)/(n+4) for v in counts]
        cohort, support = 'historical_direction_time', 0
        if valid_last:
            bucket = 0 if age < 180 else 1 if age < 360 else 2
            rows = self.trans[(rid, int(grade), bucket)]
            hop_bucket = 0 if hops <= 2 else 1 if hops <= 5 else 2
            candidates = [x for x in rows if (0 if x['b']-x['a'] <= 2 else 1 if x['b']-x['a'] <= 5 else 2) == hop_bucket]
            local = [x for x in candidates if x['b'] == target_seq and abs(x['h']-hour(at)) <= 1]
            candidates = local if len({x['trip'] for x in local}) >= 6 else candidates
            support = len({x['trip'] for x in candidates})
            persistence = [float(k == int(grade)) for k in range(4)]
            if support >= 6:
                # Weight each trip equally; repeated sections do not create more agents.
                by_trip = defaultdict(list)
                for row in candidates:
                    by_trip[row['trip']].append(row['g1'])
                hist = [sum(sum(g == k for g in gs)/len(gs) for gs in by_trip.values()) for k in range(4)]
                w = support/(support+12.)
                probability = [w*hist[k]/support+(1-w)*persistence[k] for k in range(4)]
                cohort = 'same_vehicle_grade_stop_age_transition'
            else:
                probability = persistence
                cohort = 'last_observation_support_fallback'
        mean = sum(k*p for k, p in enumerate(probability))
        sd = math.sqrt(sum((k-mean)**2*p for k, p in enumerate(probability)))
        return {**self.meta(), 'available': True, 'probabilities': probability, 'estimate': mean,
                'congested_probability': probability[2]+probability[3],
                'comparison_risk': min(3., mean+min(1., .5*sd+.15)),
                'cohort': cohort, 'transition_trips': support, 'history_records': n,
                'observed_at': observed_at if valid_last else None, 'source': 'empirical_ordinal_transition_estimate',
                'numeric_capacity_estimated': False}

    @lru_cache(maxsize=32)
    def _joint_intervals(self, eligible):
        events = [x for x in self.data['gate_events'] if x['r'] in eligible and x['full'] is not True]
        events.sort(key=lambda x: (x['at'], x['r']))
        return [{'seconds': b['at']-a['at'], 'r': b['r'], 'h': hour(a['at']), 'at': a['at']}
                for a, b in zip(events, events[1:]) if a['day'] == b['day'] and 0 <= b['at']-a['at'] <= 3600]

    def gate_wait(self, eligible_routes, at, asof, *, last_passage=None):
        if not self.usable(at, asof):
            return None
        rows, cohort = self.cohort(self._joint_intervals(tuple(sorted(set(eligible_routes)))), at)
        if not rows or (last_passage is not None and last_passage > min(at, asof)):
            return None
        elapsed = None if last_passage is None else at-last_passage
        estimate = self.residual([x['seconds'] for x in rows], elapsed)
        if estimate is None:
            return None
        weights = Counter()
        for x in rows:
            # Knowing the last event removes the random-arrival length bias.
            weights[x['r']] += (float(x['seconds'] > elapsed) if elapsed is not None else x['seconds'])
        total = sum(weights.values())
        if not total:
            return None
        return {**estimate, **self.meta(), 'cohort': cohort, 'source': 'joint_observed_gate_opportunity',
                'route_probabilities': {r: w/total for r, w in weights.items()},
                'headway': summary([x['seconds'] for x in rows]),
                'independent_route_phase_assumed': False, 'guaranteed_boarding': False,
                'known_full_filtered': True, 'actual_student_queue_observed': False}


def make_profile(derived, extracted, model_id, network_sha256):
    grades = Counter((x['r'], x['s'], hour(x['at']), x['grade']) for x in extracted['grades'])
    return {'schema': SCHEMA, 'model_id': model_id, 'dates': [derived['day']],
            'network_sha256': network_sha256, 'source_sha256': derived['source_sha256'],
            **{k: derived[k] for k in ['headways', 'rides', 'transitions', 'gate_events', 'persistence']},
            'grade_counts': [{'r': r, 's': s, 'h': h, 'g': g, 'n': n} for (r, s, h, g), n in sorted(grades.items())],
            'limits': ['One training weekday cannot identify weekday effects.',
                       'Stop detections are interval-censored, not boarding completion times.',
                       'Ordinal grades are not passenger counts or remaining seats.',
                       'No shuttle continuous archive exists in this input.',
                       'No observed student queue waits are fitted here.']}
