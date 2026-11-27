"""Regression: leaving before preparation must not create an impossible packet."""
import unittest
from queue_readiness import ready_status,has_ready_entry

def visit(end,ready=120,ticket=1,outcome='switched'):
    return {'end':end,'ready':ready,'ticket':ticket,'outcome':outcome}

class ReadinessTests(unittest.TestCase):
    def test_early_departure_is_not_ready(self):
        row=visit(100,ticket=None)
        self.assertFalse(has_ready_entry(row,1000))
        self.assertEqual(row['end'],100)
        self.assertEqual(row['ready'],120)
    def test_valid_abandonment_keeps_original_exit(self):
        self.assertTrue(has_ready_entry(visit(130),1000))
    def test_instant_ready_boarding_counts(self):
        self.assertTrue(has_ready_entry(visit(120,outcome='boarded'),1000))
    def test_instant_no_ticket_visit_does_not_count(self):
        self.assertFalse(has_ready_entry(visit(120,ticket=None),1000))
    def test_beyond_window_is_separate(self):
        self.assertEqual(ready_status(visit(150),100),'after_window_ready_weight')
    def test_impossible_boarding_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'boarded_without_ready_fifo_entry'):
            has_ready_entry(visit(100,ticket=None,outcome='boarded'),1000)

if __name__=='__main__':unittest.main()
