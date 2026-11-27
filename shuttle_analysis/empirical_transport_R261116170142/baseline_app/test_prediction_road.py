import unittest,json,time,tempfile
from pathlib import Path
from prediction import crowd_evidence
from road_geometry import RoadGeometry,Buildings,length,point_at,meters
from routing import WalkingGraph,rank_candidates,PRESETS
from shuttle import parked_admin_departure,KST
from datetime import datetime

class PredictionRoadTests(unittest.TestCase):
    def test_age_boundaries_and_zero_is_unknown(self):
        now=10000
        for age,source in [(90,'observed'),(91,'last_observation_estimate'),(600,'last_observation_estimate'),(601,'unavailable')]:
            x=crowd_evidence({'crowd_code':'4','provided_at':now-age},now)
            self.assertEqual(x['crowd_source'],source)
            if age>90:self.assertIsNone(x['crowd_cost'])
        self.assertEqual(crowd_evidence({'crowd_code':'0','provided_at':now},now)['crowd_risk'],3)
        self.assertEqual(crowd_evidence({'crowd_code':'4','provided_at':now-600},now)['crowd_risk'],2)

    def test_unknown_is_penalized_without_labeling_it_observed(self):
        r=rank_candidates([{'id':'unknown','total_seconds':100,'walk_m':10,'transfers':0,'crowd_cost':None},
            {'id':'known','total_seconds':100,'walk_m':10,'transfers':0,'crowd_cost':1}],PRESETS['comfort'])
        self.assertGreater(r['effective_weights']['crowd'],0)
        self.assertEqual(r['candidates'][0]['id'],'known')
        self.assertIsNone(r['candidates'][1]['crowd_cost'])

    def test_progress_follows_corner_and_stale_points_disappear(self):
        g=RoadGeometry();poly=[[37.46,126.95],[37.46,126.951],[37.461,126.951]]
        g.routes={'r':{'source':'test directed road','segments':[{'geometry':poly}]}}
        raw={'route_id':'r','lat':37.46,'lon':126.95,'section_order':'1','provided_at':1000,'speed_mps':5}
        p=g.match_vehicle(raw,1020)
        self.assertAlmostEqual(p['lon'],126.951,places=5)
        self.assertGreater(p['lat'],37.46)
        self.assertIsNone(g.match_vehicle(raw,1601))
        self.assertIsNone(g.match_vehicle({**raw,'section_order':''},1000))

    def test_missing_road_is_not_a_straight_line(self):
        g=RoadGeometry();g.routes={'x':{'segments':[None]}}
        self.assertIsNone(g.leg({'id':'x'},0,1))

    def test_building_wall_blocks_connector(self):
        b=Buildings({'buildings':[{'id':1,'polygon':[[0,0],[0,1],[1,1],[1,0]],'entrances':[]}]})
        self.assertTrue(b.blocked([.5,-.1],[.5,1.1]))
        self.assertFalse(b.blocked([-.1,-.1],[-.1,1.1]))

    def test_inside_building_requires_mapped_exit(self):
        payload={'elements':[{'type':'node','id':1,'lat':37.46,'lon':126.95},{'type':'node','id':2,'lat':37.46,'lon':126.951},
            {'type':'way','id':10,'nodes':[1,2],'tags':{'highway':'footway'}}]}
        building={'id':1,'polygon':[[37.46005,126.9502],[37.46005,126.9508],[37.4605,126.9508],[37.4605,126.9502]],'entrances':[]}
        g=WalkingGraph(payload,{'buildings':[building]})
        self.assertIsNone(g.walk((37.4602,126.9505),(37.46,126.951)))
        self.assertIsNone(g.walk((37.461,126.9505),(37.46,126.951))) # >30m connector

    def test_parked_admin_uses_timetable_and_no_fixed_30_second_departure(self):
        ready=datetime(2026,11,9,17,0,tzinfo=KST).timestamp();p=parked_admin_departure(ready)
        self.assertEqual(p['departure_at']-ready,150)
        self.assertIn('시나리오',p['prediction_note'])
        self.assertIsNone(parked_admin_departure(datetime(2026,11,7,17,0,tzinfo=KST).timestamp()))
        ready=datetime(2026,11,9,21,12,tzinfo=KST).timestamp();p=parked_admin_departure(ready)
        self.assertEqual(datetime.fromtimestamp(p['departure_at'],KST).strftime('%H:%M'),'21:40')

    def test_all_city_segments_have_connected_road_geometry(self):
        network=json.loads((Path(__file__).parent/'data/network.json').read_text(encoding='utf-8'));g=RoadGeometry()
        for route in network['routes']:
            for i in range(len(route['stops'])-1):
                path=g.leg(route,i,i+1)
                self.assertIsNotNone(path,(route['id'],i));self.assertGreaterEqual(len(path['geometry']),2)

if __name__=='__main__':unittest.main()
