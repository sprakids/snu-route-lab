from collections import Counter
import unittest
from departure import probabilities, shape

class DepartureProfileTests(unittest.TestCase):
    def test_peak_bounds_on_every_minute(self):
        for minute in range(1440):
            self.assertEqual(shape(minute)==1,900<=minute<=960)
        self.assertLess(shape(899),shape(900))
        self.assertLess(shape(961),shape(960))

    def test_probability_bounds_and_enrollment_weighted_mean_on_unequal_days(self):
        for weights in [Counter({615:10,915:300,1045:40}),Counter({645:530,920:22,1130:1})]:
            at=probabilities(weights)
            self.assertAlmostEqual(sum(at(m)*w for m,w in weights.items()),.5*sum(weights.values()))
            for m in range(1440):
                self.assertGreaterEqual(at(m),.45-1e-12)
                self.assertLessEqual(at(m),.55+1e-12)
            self.assertGreater(at(915),at(1035))

if __name__=='__main__':
    unittest.main()
