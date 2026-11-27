from copy import deepcopy
from types import SimpleNamespace
import unittest
from test_empirical_transport import fixture, NOW, TRAIN
from empirical_transport import EmpiricalTransport
from recent_history import TransportHistory
from evaluate_candidate import classification_metrics
from candidate_runtime import prevent_duplicate_full_risk


class CausalHistoryTests(unittest.TestCase):
    def test_joint_full_filter_does_not_charge_full_risk_twice(self):
        pool = {'departure_at': NOW+180, 'city_wait': {'headway_seconds': 300,
                'simulation_delay_scale_policy': 'absolute_audited_clock',
                'simulation': {'available': True, 'extra_wait_seconds': 30},
                'extra_wait_seconds': 180, 'empirical_full_risk': {'available': True}}}
        corrected = prevent_duplicate_full_risk(pool, NOW, {'known_full_filtered': True})
        self.assertEqual(corrected['departure_at'], NOW+30)
        self.assertEqual(corrected['city_wait']['extra_wait_seconds'], 30)
        self.assertFalse(corrected['city_wait']['empirical_full_risk']['available'])
        self.assertEqual(pool['departure_at'], NOW+180)
        self.assertEqual(prevent_duplicate_full_risk(pool, NOW, {'known_full_filtered': False}), pool)
    def test_every_arm_uses_identical_crowd_classification_threshold(self):
        rows = [{'truth': g, 'candidate': p, 'baseline': p, 'persistence': p,
                 'candidate_probability': .99, 'baseline_probability': .01}
                for g, p in [(0, 0), (1, 1.5), (2, 1.49), (3, 2)]]
        m = classification_metrics(rows)
        self.assertEqual(m['candidate_congestion_miss_rate'], .5)
        self.assertEqual(m['candidate_congestion_miss_rate'], m['baseline_congestion_miss_rate'])
        self.assertEqual(m['candidate_false_positive_rate'], m['persistence_false_positive_rate'])
    def test_future_and_uncaptured_passages_do_not_change_forecast(self):
        model = EmpiricalTransport(fixture())
        rows = [{'r': 'a', 's': 1, 'at': NOW-1000+i*300, 'seen': NOW-999+i*300} for i in range(4)]
        expected = model.headway_wait('a', 1, NOW, NOW, recent_passages=rows)
        future = rows+[{'r': 'a', 's': 1, 'at': NOW+10, 'seen': NOW+11},
                       {'r': 'a', 's': 1, 'at': NOW-5, 'seen': NOW+10}]
        self.assertEqual(expected, model.headway_wait('a', 1, NOW, NOW, recent_passages=future))

    def test_recent_completed_trips_adjust_traffic_causally(self):
        model = EmpiricalTransport(fixture())
        rows = [{'r': 'a', 'a': 1, 'b': 2, 'end': NOW-500+i*100, 'known_at': NOW-490+i*100,
                 'seconds': 240, 'trip': str(i)} for i in range(5)]
        p = model.ride_time('a', 1, 2, NOW, NOW, recent_travel=rows)
        self.assertGreater(p['seconds'], 120)
        self.assertEqual(p['recent_completed_trips_used'], 5)
        future = [{'r': 'a', 'a': 1, 'b': 2, 'end': NOW+100, 'known_at': NOW+101,
                   'seconds': 900, 'trip': 'future'}]
        self.assertEqual(p, model.ride_time('a', 1, 2, NOW, NOW, recent_travel=rows+future))
        bad = [{**r, 'known_at': r['end']-10} for r in rows]
        self.assertEqual(model.ride_time('a', 1, 2, NOW, NOW, recent_travel=bad)['seconds'], 120)
        malformed = [{'r': 'a', 'a': 1, 'b': 2, 'end': NOW-100, 'known_at': None, 'seconds': 250, 'trip': 'bad'}, {}]
        self.assertEqual(model.ride_time('a', 1, 2, NOW, NOW, recent_travel=malformed)['seconds'], 120)

    def test_known_congestion_is_not_silently_cleared_between_polls(self):
        f = fixture()
        f['transitions'] = [{**x, 'g0': 2, 'g1': 0} for x in f['transitions']]
        p = EmpiricalTransport(f).crowd('a', 2, NOW, NOW, grade=2, source_seq=1, observed_at=NOW-240)
        self.assertGreaterEqual(p['estimate'], 2)
        self.assertTrue(p['congested_memory_floor_used'])
        self.assertLess(p['expected_grade'], p['estimate'])

    def test_simultaneous_routes_are_not_erased_by_zero_headway(self):
        f = fixture()
        f['gate_events'] = [{'r': r, 'at': TRAIN+t, 'day': '2026-11-10', 'full': False, 'trip': r+str(t)}
                            for t in range(0, 4801, 600) for r in ['a', 'b']]
        p = EmpiricalTransport(f).gate_wait(['a', 'b'], NOW+2400, NOW+2400)
        self.assertAlmostEqual(p['route_probabilities']['a'], .5)
        self.assertAlmostEqual(p['route_probabilities']['b'], .5)
        self.assertFalse(p['capacity_of_simultaneous_vehicles_inferred'])

    def test_snapshot_stop_events_are_once_per_vehicle_trip(self):
        routes = [{'id': 'a', 'stops': [{'id': 's1', 'seq': 1, 'lat': 37.46, 'lon': 126.95},
                                       {'id': 's2', 'seq': 2, 'lat': 37.461, 'lon': 126.95}]}]
        h = TransportHistory(routes)
        def snapshot(at, seq, lat):
            return {'captured_at': at+5, 'vehicles': [{'route_id': 'a', 'id': 'bus', 'section_order': str(seq),
                'provided_at': at, 'at_stop': True, 'lat': lat, 'lon': 126.95,
                'previous_observation': {'provided_at': at-20}, 'full_known': True, 'full': False}]}
        h.update(snapshot(NOW-240, 1, 37.46), NOW)
        h.update(snapshot(NOW-220, 1, 37.46), NOW)
        h.update(snapshot(NOW-100, 2, 37.461), NOW)
        self.assertEqual(len(h.passages), 2)
        self.assertEqual(len(h.travel), 1)
        self.assertEqual(h.travel[0]['seconds'], 140)
        self.assertEqual(h.travel[0]['known_at'], NOW-95)
        h.update(snapshot(NOW+100, 1, 37.46), NOW)
        self.assertEqual(len(h.passages), 2)
        h.update(snapshot(NOW+100, 1, 37.46), NOW+200)
        self.assertEqual(len(h.passages), 3)


if __name__ == '__main__':
    unittest.main()
