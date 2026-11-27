"""Official-coordinate integrity and honest building-to-walkway routing coverage."""
import hashlib,json,tempfile,time,unittest
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
import server
from routing import distance

ROOT=Path(__file__).parent
class CampusPlaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='snu-campus-places-')
        cls.patches=[patch.object(server,'SHARED',None),patch.object(server,'secret',return_value=''),
            patch.object(server,'saved_bus_key',return_value=None),patch.object(server,'RUNTIME',Path(cls.tmp.name)),
            patch('urllib.request.urlopen',side_effect=AssertionError('Offline building test')),
            patch('time.time',return_value=datetime(2026,11,9,16,10,tzinfo=server.KST).timestamp())]
        for p in cls.patches:p.start()
        cls.app=server.Application();cls.catalog=cls.app.campus_places
    @classmethod
    def tearDownClass(cls):
        for p in reversed(cls.patches):p.stop()
        cls.tmp.cleanup()

    def test_catalog_preserves_every_official_building_number_name_and_coordinate(self):
        source=json.loads((ROOT/'data/raw/campus_buildings_official.json').read_text(encoding='utf-8'))
        self.assertEqual(len(source['rows']),237);self.assertEqual(len(self.catalog.entries),237)
        official={r['bd_no']:r for r in source['rows']}
        self.assertEqual({b['official_building_id'] for b in self.catalog.entries},set(official))
        for b in self.catalog.entries:
            r=official[b['official_building_id']]
            self.assertEqual(b['number'],r['vil_dong_nm']);self.assertEqual(b['name'],r['inst_kor_nm'].strip())
            self.assertEqual((b['lat'],b['lon']),(float(r['lat_val']),float(r['lon_val'])))

    def test_all_237_origins_reach_all_four_destinations_on_directed_walkways(self):
        g=self.app.graph;reverse=defaultdict(list)
        for n,edges in g.edges.items():
            for m,*_ in edges:reverse[m].append(n)
        for dest in self.app.destinations:
            target=g.endpoint((dest['lat'],dest['lon']))[0];seen={target};stack=[target]
            while stack:
                for n in reverse[stack.pop()]:
                    if n not in seen:seen.add(n);stack.append(n)
            failures=[]
            for b in self.catalog.entries:
                p=b['routing_point'];e=g.endpoint((p['lat'],p['lon']))
                if not e or e[0] not in seen:failures.append(b['number'])
            self.assertEqual(failures,[],dest['id'])

    def test_inferred_access_is_a_mapped_outdoor_point_with_explicit_unmeasured_gap(self):
        for b in self.catalog.entries:
            access=b['access'];self.assertFalse(access['indoor_time_included']);self.assertFalse(access['unverified_connector_drawn'])
            if access['method']!='nearby_walkway_estimate':continue
            p=b['routing_point'];point=(p['lat'],p['lon'])
            self.assertFalse(self.app.graph.buildings.containing(point),b['number'])
            self.assertLessEqual(distance((b['lat'],b['lon']),point),100)
            self.assertIn('미확인',access['note']);self.assertIn('미포함',access['note'])

    def test_access_artifact_matches_the_current_graph_snapshot(self):
        for name,digest in self.catalog.data['graph_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT/'data'/name).read_bytes()).hexdigest(),digest)

    def test_requested_examples_and_inferred_access_reach_the_real_planner(self):
        for number,dest in [('38','snu-station'),('220','nakseongdae'),('73','dormitory')]:
            with self.subTest(building=number):
                b=next(x for x in self.catalog.entries if x['number']==number)
                r=self.app.plan({'origin_id':b['id'],'destination_id':dest,'departure_at':time.time(),'mode':'estimate','include_shuttle':False,'preset':'fast'})
                self.assertTrue(r['candidates']);self.assertEqual(r['origin_access']['building_id'],b['id'])
                self.assertIn(b['access']['note'],r['assumptions'])
                for c in r['candidates']:
                    self.assertAlmostEqual(c['total_seconds'],sum(l['seconds'] for l in c['legs']),delta=1)
                    if b['access']['method']=='nearby_walkway_estimate':
                        walk=next(l for l in c['legs'] if l['type']=='walk')
                        self.assertEqual(walk['geometry'][0],[b['routing_point']['lat'],b['routing_point']['lon']])

    def test_custom_coordinates_cannot_claim_the_official_access_override(self):
        b=self.catalog.entries[0]
        with self.assertRaises(ValueError):self.app.plan({'origin':{'id':b['id'],'lat':0,'lon':0},'destination_id':'snu-station'})

if __name__=='__main__':unittest.main()
