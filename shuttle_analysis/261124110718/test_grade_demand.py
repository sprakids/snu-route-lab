import math
import unittest
from unittest.mock import patch

import grade_demand as model


class GradePreferenceTest(unittest.TestCase):
    def profile(self, height, reverse=False):
        points=[(0.,0.),(100.,0.)]
        if reverse:
            points.reverse()
        with patch.object(model,'horizontal',lambda a,b: abs(b[0]-a[0])),patch.object(model,'elevation',height):
            model.segment.cache_clear()
            try:
                return model.segment(*points)
            finally:
                model.segment.cache_clear()

    def test_grade_anchors_leave_the_physical_length_direction_independent(self):
        heights=lambda x,y:x*.10
        up,cost_up=self.profile(heights)
        down,cost_down=self.profile(heights,True)
        self.assertAlmostEqual(up,math.hypot(100.,10.))
        self.assertAlmostEqual(down,up)
        self.assertAlmostEqual(cost_up/up,2.)
        self.assertAlmostEqual(cost_down/down,.75)
        self.assertEqual(self.profile(lambda x,y:17.),(100.,100.))

    def test_midroute_hill_counts_in_both_directions_with_equal_endpoint_elevations(self):
        physical,cost=self.profile(lambda x,y:.10*min(x,100.-x))
        self.assertAlmostEqual(cost,physical*(2.+.75)/2)

    def test_zero_length_and_extreme_grades(self):
        self.assertEqual(model.segment((37.45,126.95),(37.45,126.95)),(0.,0.))
        self.assertEqual(model.multiplier(-.55),.5)
        self.assertEqual(model.multiplier(.55),3.)


if __name__=='__main__':
    unittest.main()
