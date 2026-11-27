"""Contract/regression tests for causality, units, live priority and integration."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import gzip
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'baseline_app'))
from empirical_transport import EmpiricalTransport, SCHEMA, KST
from extract_observations import extract
from candidate_runtime import ContinuityAdapter, TravelAdapter, common_gate_adapter, install_candidate
from continuity import Continuity
from routing import finish_candidate


TRAIN = datetime(2026, 11, 10, 15, tzinfo=KST).timestamp()
NOW = TRAIN+86400*2


def fixture():
    return {'schema': SCHEMA, 'model_id': 'R261116162001', 'dates': ['2026-11-10'], 'network_sha256': 'network',
            'headways': [{'r': 'a', 's': 1, 'h': 15, 'seconds': h} for h in [600, 900]*6],
            'rides': [{'r': 'a', 'a': 1, 'b': 2, 'h': 15, 'seconds': 120, 'trip': str(i)} for i in range(6)],
            'grade_counts': [{'r': 'a', 's': 2, 'h': 15, 'g': 2, 'n': 20}],
            'transitions': [{'r': 'a', 'a': 1, 'b': 2, 'h': 15, 'g0': 1, 'g1': 2, 'bucket': 1, 'trip': str(i)} for i in range(20)],
            'gate_events': [{'r': r, 'at': TRAIN+t, 'day': '2026-11-10', 'full': False}
                            for t in range(0, 2401, 600) for r, t in [('a', t), ('b', t+30)]],
            'persistence': []}


class Contracts(unittest.TestCase):
    def setUp(self):
        self.model = EmpiricalTransport(fixture())

    def test_no_future_history_in_time_specified_search(self):
        self.assertIsNone(self.model.ride_time('a', 1, 2, TRAIN-86400, NOW))
        self.assertIsNone(self.model.headway_wait('a', 1, NOW, TRAIN))
        self.assertIsNone(self.model.crowd('a', 2, TRAIN, NOW))

    def test_condition_on_elapsed_not_half_median(self):
        p = self.model.headway_wait('a', 1, NOW, NOW, last_passage=NOW-300)
        self.assertEqual(p['seconds'], 450)
        self.assertEqual(p['range_seconds'], [300, 600])
        self.assertFalse(p['nominal_queue_delay_included'])

    def test_random_arrival_variance_correction(self):
        p = self.model.headway_wait('a', 1, NOW, NOW)
        self.assertEqual(p['seconds'], (600**2+900**2)/(2*(600+900)))

    def test_no_unseen_future_anchor_and_unsupported_tail(self):
        self.assertIsNone(self.model.headway_wait('a', 1, NOW, NOW, last_passage=NOW+1))
        self.assertIsNone(self.model.headway_wait('a', 1, NOW, NOW, last_passage=NOW-1000))

    def test_direction_and_sequence_separate(self):
        self.assertIsNone(self.model.headway_wait('a', 2, NOW, NOW))
        self.assertIsNone(self.model.ride_time('a', 2, 1, NOW, NOW))
        self.assertIsNone(self.model.ride_time('other', 1, 2, NOW, NOW))

    def test_stale_observation_uses_history_not_observed_label(self):
        p = self.model.crowd('a', 2, NOW, NOW, grade=0, source_seq=1, observed_at=NOW-700)
        self.assertIsNone(p['observed_at'])
        self.assertFalse(p['numeric_capacity_estimated'])

    def test_transition_is_distribution_and_trip_weighted(self):
        p = self.model.crowd('a', 2, NOW, NOW, grade=1, source_seq=1, observed_at=NOW-240)
        self.assertAlmostEqual(sum(p['probabilities']), 1.)
        self.assertGreater(p['estimate'], 1)
        self.assertEqual(p['transition_trips'], 20)
        self.assertLessEqual(p['comparison_risk'], 3.)

    def test_joint_gate_preserves_bunching(self):
        p = self.model.gate_wait(['a', 'b'], NOW, NOW)
        self.assertGreater(p['seconds'], 250)  # Correlated 30s/570s gaps, not independent 200s.
        self.assertFalse(p['independent_route_phase_assumed'])
        self.assertFalse(p['guaranteed_boarding'])
        self.assertAlmostEqual(sum(p['route_probabilities'].values()), 1.)

    def test_gate_route_eligibility_and_full_flags(self):
        p = self.model.gate_wait(['a'], NOW, NOW)
        self.assertIsNone(p)  # Only four intervals, insufficient support.
        f = fixture()
        for x in f['gate_events']:
            if x['r'] == 'b':
                x['full'] = True
        self.assertIsNone(EmpiricalTransport(f).gate_wait(['a', 'b'], NOW, NOW))

    def test_raw_unknown_grade_zero_is_not_empty(self):
        network = {'routes': [{'id': 'a', 'stops': [{'seq': 1, 'lat': 37.46, 'lon': 126.95}]}]}
        v = {'route_id': 'a', 'id': 'bus', 'provided_at': TRAIN, 'section_order': '1',
             'lat': 37.46, 'lon': 126.95, 'crowd_code': '0', 'at_stop': True,
             'previous_observation': {'provided_at': TRAIN-20}}
        with tempfile.TemporaryDirectory(prefix='snu-empirical-test-') as tmp:
            path = Path(tmp)/'archive.gz'
            with gzip.open(path, 'wt', encoding='utf-8') as f:
                f.write(json.dumps({'at': TRAIN+10, 'vehicles': [v, v]})+'\n')
            d = extract(path, '2026-11-10', network)
        self.assertEqual(len(d['grades']), 0)
        self.assertEqual(len(d['passages']), 1)
        self.assertEqual(d['quality']['repeated_provider_timestamp'], 1)

    def test_fresh_observed_crowd_has_priority(self):
        route = {'id': 'a', 'stops': [{'seq': 1}, {'seq': 2}]}
        adapter = ContinuityAdapter(Continuity(), self.model, {'crowd'})
        p = adapter.predict_crowd(route, 0, NOW, NOW, {'provided_at': NOW-10, 'crowd_cost': 1}, 1, True)
        self.assertEqual(p['crowd_source'], 'observed')
        self.assertEqual(p['crowd_cost'], 1)

    def test_ride_does_not_add_dwell_twice_or_override_current_traffic(self):
        route = {'id': 'a', 'stops': [{'seq': 1}, {'seq': 2}]}
        base = SimpleNamespace(estimate=lambda *args: {'available': True, 'seconds': 400, 'source': 'prior'})
        transit = SimpleNamespace(now=lambda: NOW)
        adapter = TravelAdapter(base, self.model, transit, {'ride'})
        result = adapter.estimate(route, 0, 1, NOW)
        self.assertEqual(result['seconds'], 120)
        self.assertEqual(result['add_blanket_dwell_seconds'], 0)
        base.estimate = lambda *args: {'available': True, 'seconds': 180, 'current_segments': 1}
        self.assertEqual(adapter.estimate(route, 0, 1, NOW)['seconds'], 180)
        route['kind'] = 'shuttle'
        self.assertEqual(adapter.estimate(route, 0, 1, NOW)['seconds'], 180)

    def test_missing_geometry_and_future_training_use_fallback(self):
        route = {'id': 'a', 'stops': [{'seq': 1}, {'seq': 2}]}
        base = SimpleNamespace(estimate=lambda *args: {'available': False, 'seconds': 0})
        adapter = TravelAdapter(base, self.model, SimpleNamespace(now=lambda: NOW), {'ride'})
        self.assertFalse(adapter.estimate(route, 0, 1, NOW)['available'])

    def test_install_is_reversible_and_requires_network_match(self):
        old = SimpleNamespace()
        planner = SimpleNamespace(travel=old, transit=SimpleNamespace(continuity=old))
        with self.assertRaises(ValueError):
            install_candidate(planner, self.model, {'ride'}, 'wrong', patch_gate=False)
        undo = install_candidate(planner, self.model, {'ride'}, 'network', patch_gate=False)
        self.assertIsInstance(planner.travel, TravelAdapter)
        undo()
        self.assertIs(planner.travel, old)
        self.assertIs(planner.transit.continuity, old)

    def test_real_gate_candidate_total_and_queue_delay_stay_consistent(self):
        f = fixture()
        ids = ['100100250', '100100251']
        for e in f['gate_events']:
            e['r'] = ids[0] if e['r'] == 'a' else ids[1]
        model = EmpiricalTransport(f)
        routes, candidates = {}, []
        for rid in ids:
            routes[rid] = {'id': rid, 'stops': [{'id': '120000029', 'seq': 1}, {'id': '120000150', 'seq': 2}]}
            legs = [{'type': 'walk', 'seconds': 100, 'meters': 100}, {'type': 'board', 'seconds': 20},
                    {'type': 'wait', 'seconds': 200}, {'type': 'bus', 'route_id': rid, 'route_name': rid,
                    'station_id': '120000029', 'from_seq': 1, 'to_seq': 2, 'ready_at': NOW+120,
                    'seconds': 300, 'crowd_cost': None, 'crowd_risk': 1, 'arrival_source': 'estimate',
                    'crowd_estimate': 1, 'departure_at': NOW+320}]
            candidates.append(finish_candidate(rid, legs, NOW))
        def city_boarding(route, i, ready, base, live, **kwargs):
            return {**base, 'departure_at': base['departure_at']+60, 'city_wait': {'extra_wait_seconds': 60}}
        planner = SimpleNamespace(by_id=routes, transit=SimpleNamespace(now=lambda: NOW,
                                  in_service=lambda *args: True, city_boarding=city_boarding))
        run = common_gate_adapter(lambda c, *args: c, model, {'gate'})
        out = run(candidates, planner, NOW, True)[-1]
        self.assertEqual(out['id'], 'gate-first')
        self.assertEqual(out['total_seconds'], sum(l['seconds'] for l in out['legs']))
        self.assertEqual(out['arrival_at'], NOW+out['total_seconds'])
        self.assertEqual(out['legs'][-1]['city_wait']['extra_wait_seconds'], 60)
        # Neither source candidates nor their existing geometry/fields are mutated.
        self.assertEqual(candidates[0]['wait_seconds'], 200)


if __name__ == '__main__':
    unittest.main()
