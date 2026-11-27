import copy,unittest
from segment_calibration import collect_training,estimate,profile_at

class CalibrationBoundary(unittest.TestCase):
    def test_changing_check_day_cannot_change_training_estimates(self):
        rows=[{'day':'2026-11-10','route':'A','from_seq':2,'to_seq':3,'hour':17,'seconds':[50,60,70,80,90]},
              {'day':'2026-11-11','route':'A','from_seq':2,'to_seq':3,'hour':17,'seconds':[1]}]
        original=collect_training(rows);changed=copy.deepcopy(rows);changed[1]['seconds']=[900]*100
        self.assertEqual(original,collect_training(changed))
        self.assertEqual(estimate(original['A',2,3,17],100,30),(70.,'training_adjacent_detected_stop_median'))
    def test_missing_observations_keep_prior_instead_of_zero_time(self):
        self.assertEqual(estimate([],95,20),(95.,'preserved_insufficient_training_intervals'))
        self.assertEqual(estimate([1,2,3,4],95,20)[0],95)
    def test_physical_minimum_and_direction_are_preserved(self):
        self.assertEqual(estimate([1]*5,95,20)[0],20)
        rows=[{'day':'2026-11-10','route':'A','from_seq':3,'to_seq':2,'hour':17,'seconds':[50]*10},
              {'day':'2026-11-10','route':'A','from_seq':2,'to_seq':4,'hour':17,'seconds':[50]*10}]
        self.assertEqual(collect_training(rows),{})
    def test_segment_entry_half_open_clock_boundary(self):
        route={'segment_profiles':{'2':[[0,43200,[50]],[43200,50000,[100]]]}}
        self.assertEqual(profile_at(route,43199.99),[50]);self.assertEqual(profile_at(route,43200),[100])
    def test_malformed_training_duration_fails(self):
        rows=[{'day':'2026-11-10','route':'A','from_seq':2,'to_seq':3,'hour':17,'seconds':[float('nan')]}]
        with self.assertRaises(AssertionError):collect_training(rows)

if __name__=='__main__':unittest.main()
