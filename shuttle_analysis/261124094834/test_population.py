import math
import unittest
from population import cap_daily_departures, DAILY_TRIP_LIMIT
from departure import apply_departures

def fixture(enrollment):
    events=[dict(weekday='월',building='A',end_minute=t,enrollment=n)
            for t,n in zip([720,915],enrollment)]
    plans=[[48*i+1,'A','dest',e['enrollment']/2,e['end_minute']*60,[i,180],[]] for i,e in enumerate(events)]
    data={'prepared':{'plans':{'월':plans},'expected':{'월':sum(enrollment)/2}}}
    changed={1:(plans[0][3],0,180)}
    profile=apply_departures(data,events,'월',changed)
    start=[p.copy() for p in plans]
    record=cap_daily_departures(data,'월',profile,changed)
    return plans,start,profile,record,changed

class DailyPopulationTests(unittest.TestCase):
    def test_under_budget_is_bit_identical(self):
        plans,start,profile,record,changed=fixture([10000,20000])
        self.assertEqual(plans,start)
        self.assertFalse(record['binding'])
        self.assertEqual(record['admitted'],15000)
    def test_binding_day_retains_peak_routes_and_total(self):
        plans,start,profile,record,changed=fixture([40000,40000])
        self.assertTrue(record['binding'])
        self.assertLessEqual(sum(p[3] for p in plans),DAILY_TRIP_LIMIT)
        self.assertAlmostEqual(record['admitted'],DAILY_TRIP_LIMIT,places=5)
        self.assertEqual(changed[1][0],plans[0][3])
        for old,new in zip(start,plans):
            self.assertEqual(old[:3]+old[4:],new[:3]+new[4:])
            self.assertAlmostEqual(new[3]/old[3],record['applied_factor'])
        peaks=profile['hourly_clock_rates']
        self.assertEqual(peaks['15'],peaks['16'])
        self.assertGreater(peaks['15'],peaks['12'])
        self.assertTrue(math.isclose(sum(r['immediate_trip_mass']+r['other_activity_mass']
            for r in profile['rate_by_class_end']),80000))

if __name__=='__main__':
    unittest.main()
