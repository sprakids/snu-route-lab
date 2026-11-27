from copy import deepcopy
import unittest
from test_empirical_transport import fixture, NOW
from empirical_transport import EmpiricalTransport
from parent_transport import EmpiricalTransport as ParentTransport
from review_runtime import ReviewModel


class ReviewRuntimeTests(unittest.TestCase):
    def model(self):
        f = fixture()
        for e in f['gate_events']:
            e.update(s=1, stop_id='120000029')
        parent = {**f, 'schema': 'snu_empirical_transport_candidate_v1', 'model_id': 'R-parent'}
        return ReviewModel(EmpiricalTransport(f), ParentTransport(parent),
                           {'shadow_enabled_components': ['headway', 'crowd', 'gate']})

    def test_rejected_ride_retains_empirical_parent_not_legacy_distance(self):
        m = self.model()
        result = m.ride_time('a', 1, 2, NOW, NOW, recent_travel=[])
        self.assertEqual(result['seconds'], 120)
        self.assertEqual(result['model_id'], 'R-parent')
        self.assertTrue(result['retained_parent_component'])

    def test_wrong_stop_does_not_reset_gate_phase(self):
        m = self.model()
        gate = [{'r': 'a', 's': 1, 'stop_id': '120000029', 'at': NOW-200, 'seen': NOW-199, 'full': False}]
        expected = m.gate_wait(['a', 'b'], NOW, NOW, recent_passages=gate)
        irrelevant = {'r': 'a', 's': 9, 'stop_id': 'another', 'at': NOW-10, 'seen': NOW-9, 'full': False}
        self.assertEqual(expected, m.gate_wait(['a', 'b'], NOW, NOW, recent_passages=gate+[irrelevant]))

    def test_simultaneous_full_vehicle_does_not_hide_unflagged_opportunity(self):
        m = self.model()
        a = {'r': 'a', 's': 1, 'stop_id': '120000029', 'at': NOW-200, 'seen': NOW-199, 'full': False, 'trip': '1'}
        b = {**a, 'full': True, 'trip': '2'}
        first = m.gate_wait(['a', 'b'], NOW, NOW, recent_passages=[a, b])
        second = m.gate_wait(['a', 'b'], NOW, NOW, recent_passages=[b, a])
        self.assertEqual(first, second)


if __name__ == '__main__':
    unittest.main()
