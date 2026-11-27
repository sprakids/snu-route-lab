"""R261116170142: causal multi-day transport distributions and ordinal decisions."""
from collections import Counter, defaultdict
from functools import lru_cache
from datetime import datetime
import math
import statistics

from parent_transport import (EmpiricalTransport as ParentTransport, KST, hour,
                              quantile, summary)
SCHEMA = 'snu_empirical_transport_candidate_v2'


def minute(at):
    d = datetime.fromtimestamp(at, KST)
    return d.hour*60+d.minute+d.second/60


class EmpiricalTransport(ParentTransport):
    def __init__(self, profile):
        if isinstance(profile, str):
            import json
            with open(profile, encoding='utf-8') as stream:
                profile = json.load(stream)
        if profile.get('schema') != SCHEMA:
            raise ValueError('Unrecognized v2 transport profile')
        super().__init__({**profile, 'schema': 'snu_empirical_transport_candidate_v1'})
        self.data = profile
        self.settings = {'recent_weight': .35, 'miss_cost': 2., 'congested_memory_floor': True,
                         **profile.get('settings', {})}

    def meta(self):
        return {**super().meta(), 'method_version': 'causal_stop_profiles_v2',
                'weekday_effect_identified': False, 'training_day_count': len(self.data['dates']),
                'unit_of_support': 'vehicle trip, never passengers', 'new_provider_calls': 0}

    @staticmethod
    def cohort(rows, at, minimum=6):
        for radius, label in [(30, 'within_30_minutes'), (60, 'within_60_minutes'), (120, 'within_120_minutes')]:
            local = [x for x in rows if abs((minute(x['at']) if x.get('at') is not None else x['h']*60+30)-minute(at)) <= radius]
            if len(local) >= minimum:
                return local, 'same_direction_stop_'+label
        return (rows, 'same_direction_stop_pooled_hours') if len(rows) >= minimum else ([], 'insufficient_support')

    @staticmethod
    def causal_passages(rows, at, asof, eligible=None):
        cutoff = min(at, asof)
        result = []
        for p in rows or ():
            if eligible is not None and p.get('r') not in eligible:
                continue
            if (not isinstance(p.get('at'), (float, int)) or not math.isfinite(p['at']) or
                    not isinstance(p.get('seen'), (float, int)) or not math.isfinite(p['seen'])):
                continue
            if p['at'] <= p['seen'] <= cutoff and 0 <= cutoff-p['at'] <= 3600:
                result.append(p)
        unique = {(p.get('r'), p.get('s'), p['at']): p for p in result}
        return sorted(unique.values(), key=lambda x: x['at'])

    def _wait(self, rows, at, asof, last_passage, recent, joint=False):
        reference = last_passage if last_passage is not None and at-last_passage <= 1800 else at
        rows, cohort = self.cohort(rows, reference)
        if not rows:
            return None
        if last_passage is not None and (not math.isfinite(last_passage) or last_passage > min(at, asof)):
            return None
        values = [x['seconds'] for x in rows]
        recent = self.causal_passages(recent, at, asof)
        stamps = sorted({p['at'] for p in recent})
        gaps = [b-a for a, b in zip(stamps, stamps[1:]) if 15 <= b-a <= 3600][-3:]
        scale = 1.
        if len(gaps) >= 2 and statistics.median(values) > 0:
            ratio = max(.65, min(1.8, statistics.median(gaps)/statistics.median(values)))
            weight = min(.5, self.settings['recent_weight']*len(gaps)/3)
            scale = (1-weight)+weight*ratio
        values = [v*scale for v in values]
        elapsed = None if last_passage is None else at-last_passage
        result = self.residual(values, elapsed)
        lost_phase = result is None
        if result is None:
            # Unsupported tail: abandon exact phase, not an invented vehicle.
            result = self.residual(values, None)
        if result is None:
            return None
        return {**result, **self.meta(), 'cohort': cohort, 'headway': summary(values),
                'recent_intervals_used': len(gaps), 'recent_pace_scale': scale,
                'phase_support_lost': lost_phase, 'available': True,
                'source': 'joint_observed_gate_opportunity' if joint else 'observed_stop_headway_distribution',
                'nominal_queue_delay_included': False, 'confirmed_vehicle': False}

    def headway_wait(self, rid, seq, at, asof, *, last_passage=None, recent_passages=None):
        if not self.usable(at, asof):
            return None
        recent = [p for p in self.causal_passages(recent_passages, at, asof) if p.get('r') == rid and p.get('s') == seq]
        if recent:
            last_passage = max(p['at'] for p in recent)
        result = self._wait(self.heads[(rid, seq)], at, asof, last_passage, recent)
        return {**result, 'direction_key': [rid, seq]} if result else None

    def ride_time(self, rid, a, b, at, asof, *, recent_travel=None):
        result = super().ride_time(rid, a, b, at, asof)
        if result is None:
            return None
        cutoff = min(at, asof)
        recent = [x for x in recent_travel or () if x.get('r') == rid and x.get('a') == a and x.get('b') == b
                  and x.get('end', math.inf) <= x.get('known_at', -math.inf) <= cutoff
                  and 0 <= cutoff-x.get('end', -math.inf) <= 1800 and 0 < x.get('seconds', 0) <= 1800]
        unique = {x['trip']: x for x in recent}
        recent = sorted(unique.values(), key=lambda x: x['end'])[-5:]
        scale = 1.
        if len(recent) >= 3 and result['seconds'] > 0:
            ratio = max(.65, min(1.8, statistics.median(x['seconds'] for x in recent)/result['seconds']))
            weight = min(.5, self.settings['recent_weight']*len(recent)/5)
            scale = (1-weight)+weight*ratio
        return {**result, 'seconds': result['seconds']*scale,
                'range_seconds': [x*scale for x in result['range_seconds']],
                'recent_completed_trips_used': len(recent), 'recent_pace_scale': scale,
                'causal_cutoff': cutoff, 'add_blanket_dwell_seconds': 0}

    @lru_cache(maxsize=4096)
    def _crowd_prior(self, rid, target_seq, h):
        rows = self.counts[rid]
        local = [x for x in rows if x['s'] == target_seq and abs(x['h']-h) <= 1]
        rows = local if sum(x['n'] for x in local) >= 8 else [x for x in rows if abs(x['h']-h) <= 1]
        return tuple(sum(x['n'] for x in rows if x['g'] == k) for k in range(4))

    @lru_cache(maxsize=8192)
    def _transition(self, rid, source_seq, target_seq, h, grade, bucket):
        hops = target_seq-source_seq
        hop_bucket = 0 if hops <= 2 else 1 if hops <= 5 else 2
        rows = [x for x in self.trans[(rid, grade, bucket)]
                if (0 if x['b']-x['a'] <= 2 else 1 if x['b']-x['a'] <= 5 else 2) == hop_bucket]
        for label, subset in [('same_stop_hour', [x for x in rows if x['b'] == target_seq and abs(x['h']-h) <= 1]),
                              ('same_corridor_hour', [x for x in rows if abs(x['b']-target_seq) <= 2 and abs(x['h']-h) <= 1]),
                              ('same_route_hops', rows)]:
            trips = defaultdict(list)
            for x in subset:
                trips[x['trip']].append(x['g1'])
            n = len(trips)
            if n >= 6:
                counts = [sum(sum(g == k for g in gs)/len(gs) for gs in trips.values()) for k in range(4)]
                return tuple(counts), n, label
        return (0., 0., 0., 0.), 0, 'last_observation_support_fallback'

    def crowd(self, rid, target_seq, at, asof, *, grade=None, source_seq=None, observed_at=None):
        if not self.usable(at, asof):
            return None
        if grade is not None and (type(grade) not in (int, float) or grade not in (0, 1, 2, 3)):
            return None
        age = at-observed_at if observed_at is not None else None
        hops = target_seq-source_seq if source_seq is not None else None
        valid = (grade is not None and age is not None and 0 <= age <= 600 and
                 observed_at <= min(at, asof) and hops is not None and 0 <= hops <= 8)
        counts = self._crowd_prior(rid, target_seq, hour(at));n = sum(counts)
        if not valid and n < 8:
            return None
        probability = [(v+1)/(n+4) for v in counts]
        support, cohort = 0, 'historical_direction_time'
        if valid:
            bucket = 0 if age < 180 else 1 if age < 360 else 2
            values, support, cohort = self._transition(rid, source_seq, target_seq, hour(at), int(grade), bucket)
            persistence = [float(k == int(grade)) for k in range(4)]
            weight = support/(support+8.) if support else 0.
            probability = [weight*(values[k]/support if support else 0)+(1-weight)*persistence[k] for k in range(4)]
        def loss(k):
            return sum(p*abs(k-g)*(self.settings['miss_cost'] if k < 2 <= g else 1.) for g, p in enumerate(probability))
        decision = min(range(4), key=lambda k: (loss(k), k))
        conservative_memory = bool(valid and grade >= 2 and self.settings['congested_memory_floor'])
        if conservative_memory:
            decision = max(2, decision)
        mean = sum(k*p for k, p in enumerate(probability))
        sd = math.sqrt(sum((k-mean)**2*p for k, p in enumerate(probability)))
        return {**self.meta(), 'available': True, 'probabilities': probability, 'estimate': decision,
                'expected_grade': mean, 'estimate_kind': 'ordinal_decision',
                'congested_probability': probability[2]+probability[3], 'predicted_congested': decision >= 2,
                'comparison_risk': min(3., max(float(decision), mean+min(1., .5*sd+.15))),
                'cohort': cohort, 'transition_trips': support, 'history_records': n,
                'observed_at': observed_at if valid else None, 'source': 'empirical_ordinal_transition_estimate',
                'congested_memory_floor_used': conservative_memory,
                'memory_policy': 'Do not declare a known congested vehicle clear without fresh evidence within10min.',
                'numeric_capacity_estimated': False, 'loss_false_negative_multiplier': self.settings['miss_cost']}

    @lru_cache(maxsize=32)
    def _gate_groups(self, eligible):
        grouped = defaultdict(list)
        for x in self.data['gate_events']:
            if x['r'] in eligible and x['full'] is not True:
                grouped[(x['day'], x['at'])].append(x)
        groups = [{'day': d, 'at': at, 'routes': sorted({x['r'] for x in xs}),
                   'batch_vehicles': len({x.get('trip', (x['r'], x['at'])) for x in xs})}
                  for (d, at), xs in sorted(grouped.items())]
        return [{'day': a['day'], 'at': a['at'], 'h': hour(a['at']), 'seconds': b['at']-a['at'],
                 'routes': b['routes'], 'batch_vehicles': b['batch_vehicles']}
                for a, b in zip(groups, groups[1:]) if a['day'] == b['day'] and 0 < b['at']-a['at'] <= 3600]

    def gate_wait(self, eligible_routes, at, asof, *, last_passage=None, recent_passages=None):
        if not self.usable(at, asof):
            return None
        eligible = tuple(sorted(set(eligible_routes)))
        recent = [x for x in self.causal_passages(recent_passages, at, asof, eligible) if x.get('full') is not True]
        if recent:
            last_passage = max(x['at'] for x in recent)
        rows = self._gate_groups(eligible)
        result = self._wait(rows, at, asof, last_passage, recent, True)
        if result is None:
            return None
        reference = last_passage if last_passage is not None and at-last_passage <= 1800 else at
        rows, _ = self.cohort(rows, reference)
        elapsed = result['conditioned_elapsed_seconds'];scale = result['recent_pace_scale'];weights = Counter()
        for x in rows:
            w = float(x['seconds']*scale > elapsed) if elapsed is not None else x['seconds']*scale
            for rid in x['routes']:
                weights[rid] += w/len(x['routes'])
        total = sum(weights.values())
        if not total:
            return None
        return {**result, 'route_probabilities': {r: w/total for r, w in weights.items()},
                'independent_route_phase_assumed': False, 'guaranteed_boarding': False,
                'known_full_filtered': True, 'actual_student_queue_observed': False,
                'simultaneous_vehicle_groups': sum(x['batch_vehicles'] > 1 for x in rows),
                'capacity_of_simultaneous_vehicles_inferred': False}


def make_profile(derived_days, extracted_days, model_id, network_sha256, settings=None):
    result = {'schema': SCHEMA, 'model_id': model_id, 'dates': sorted(x['day'] for x in derived_days),
              'network_sha256': network_sha256,
              'source_sha256_by_day': {x['day']: x['source_sha256'] for x in derived_days},
              'settings': settings or {'recent_weight': .35, 'miss_cost': 2., 'congested_memory_floor': True}}
    for key in ['headways', 'rides', 'transitions', 'gate_events', 'persistence']:
        result[key] = [x for d in derived_days for x in d[key]]
    grades = Counter((x['r'], x['s'], hour(x['at']), x['grade']) for day in extracted_days for x in day['grades'])
    result['grade_counts'] = [{'r': r, 's': s, 'h': h, 'g': g, 'n': n} for (r, s, h, g), n in sorted(grades.items())]
    result['limits'] = ['Stop-flag detections can miss buses; these are not exact dispatch headways.',
                        'Two weekdays do not establish separate weekday effects.',
                        'No continuous shuttle archive exists in the current training input.',
                        'Congested memory protection is a conservative decision rule, not observed occupancy.']
    return result
