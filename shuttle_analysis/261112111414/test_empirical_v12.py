import copy,unittest
from empirical_v12 import Evidence,api_grade,ordinal_grade
from v12_supply import invert_passage,stop_times

def example():
    return {'training_dates':['2026-11-10'],'route_sequences':{'A':[10,11,12]},'missing_crowd_routes':['B'],
      'headways':{'A|10|17':{'seconds':[60,60,120,120,240]}},'headway_periods':{},
      'segment_samples':{'A|10|11|17':{'seconds':[40,50,60,70,80]}},
      'grades':{'A|10|17':{'counts':[1,0,0,0]}},
      'transitions':{'A|10|11|17':{'counts':[[0,0,2,0],[0,0,0,0],[0,0,0,0],[0,0,0,0]]}},
      'full_flags':{'A|10|17':{'known_n':4,'full_n':1}}}

class EvidenceBoundary(unittest.TestCase):
    def test_api_unknown_zero_and_normalized_known_zero_are_distinct(self):
        self.assertIsNone(api_grade(0));self.assertEqual(api_grade(3),0);self.assertEqual(ordinal_grade(0),0)
        self.assertIsNone(api_grade(None));self.assertEqual(api_grade(6),3)
    def test_transition_probabilities_change_discomfort_without_changing_physical_times(self):
        data=example();e=Evidence(data);times=[61200.,61260.,61380.];old=times[:]
        exposure,context=e.context('A',0,2,times[0],times)
        self.assertEqual(exposure,120.);self.assertEqual(times,old)
        self.assertEqual(context['full_flag_probability'],.25);self.assertTrue(context['ordinal_grade_is_not_occupancy_count'])
    def test_missing_grade_is_none_not_observed_empty_bus(self):
        e=Evidence(example());e.data['route_sequences']['B']=[1,2]
        exposure,context=e.context('B',0,1,61200.,[61200.,61260.])
        self.assertIsNone(exposure);self.assertEqual(context['initial_grade_n'],0)
        self.assertIsNone(context['full_flag_probability']);self.assertIn('missing',context['crowd_source'])
    def test_headway_second_moment_reference_is_labeled_not_queue_wait(self):
        e=Evidence(example());_,context=e.context('A',0,1,61200.,[61200.,61260.])
        self.assertAlmostEqual(context['random_arrival_empty_queue_wait_reference_seconds'],78.)
        self.assertTrue(context['reference_is_not_personal_queue_wait'])
    def test_missing_transition_row_retains_probability_mass(self):
        d=example();d['grades']['A|10|17']['counts']=[0,1,0,0]
        exposure,_=Evidence(d).context('A',0,2,61200.,[61200.,61260.,61380.]);self.assertEqual(exposure,0.)
    def test_anchor_passage_is_inverted_not_copied_as_departure(self):
        route={'stops':[{'seq':1},{'seq':2},{'seq':3}],'segment_profiles':{'0':[[0,200000,[30.,70.]]]}}
        start,error,actual=invert_passage(route,1000,2)
        self.assertEqual((start,error,actual),(900.,0.,1000.));self.assertEqual(stop_times(route,start)[2],1000.)
    def test_uncertainty_is_empirical_range_not_confidence_interval(self):
        e=Evidence(example());s=e.time_spread('A',10,11,61200.)
        self.assertEqual((s['n'],s['p10_seconds'],s['p90_seconds']),(5,40,80))

if __name__=='__main__':unittest.main()
