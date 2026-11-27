import json,time,unittest
from pathlib import Path
from unittest.mock import patch
from travel_time import TravelTime,paired_arrival_time

class TravelTimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.network=json.loads((Path(__file__).parent/'data/network.json').read_text(encoding='utf-8'))
        cls.route=cls.network['routes'][0];cls.model=TravelTime()
        cls.i=next(i for i,s in enumerate(cls.route['stops']) if s['ars']=='21297')
        cls.j=next(i for i,s in enumerate(cls.route['stops']) if s['id']=='120000150' and i>cls.i)

    def test_official_culture_to_station_distance_does_not_include_osm_detour(self):
        p=self.model.geometry.leg(self.route,self.i,self.j)
        self.assertGreater(p['meters'],2000);self.assertLess(p['meters'],2600)

    def test_current_section_speed_does_not_add_an_extra_15_seconds_per_stop(self):
        now=time.time();sections={str(s['seq']):{'speed_kmh':20} for s in self.route['stops']}
        snap={'traffic':{self.route['id']:{'fetched_at':now,'sections':sections}}}
        p=self.model.estimate(self.route,self.i,self.j,now,snap,True)
        road=self.model.geometry.leg(self.route,self.i,self.j)
        self.assertEqual(p['seconds'],round(road['meters']/(20/3.6)))
        self.assertEqual(p['source'],'current_section_speed')

    def test_stale_speed_is_not_labeled_current(self):
        now=time.time();snap={'traffic':{self.route['id']:{'fetched_at':now-901,'sections':{}}}}
        p=self.model.estimate(self.route,self.i,self.j,now,snap,True)
        self.assertEqual(p['source'],'historical_section_speed');self.assertTrue(p['history_dates'])

    def test_measured_history_needs_independent_days_and_enough_records(self):
        now=time.time();key=f"{self.route['id']}:{self.i+1}:{self.j+1}"
        measured={'n':5,'days':2,'median_seconds':420,'p10_seconds':360,'p90_seconds':480}
        p=self.model.estimate(self.route,self.i,self.j,now,{'travel_history':{key:measured}},True)
        self.assertEqual(p['seconds'],420);self.assertEqual(p['source'],'measured_history')
        measured['days']=1
        self.assertNotEqual(self.model.estimate(self.route,self.i,self.j,now,{'travel_history':{key:measured}},True)['source'],'measured_history')

    def test_only_same_vehicle_time_aligned_arrival_differences_are_used(self):
        now=time.time();a={'vehicle_id':'v','provided_at':now,'departure_at':now+100};b={**a,'departure_at':now+520}
        self.assertEqual(paired_arrival_time(a,b,2300,now)['seconds'],420)
        self.assertIsNone(paired_arrival_time(a,{**b,'vehicle_id':'other'},2300,now))
        self.assertIsNone(paired_arrival_time(a,{**b,'provided_at':now-61},2300,now))
        self.assertIsNone(paired_arrival_time(a,{**b,'departure_at':now+101},2300,now))

if __name__=='__main__':unittest.main()
