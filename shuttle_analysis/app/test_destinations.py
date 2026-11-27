"""Four UI destinations must resolve to official stops and traversable routes."""
import tempfile,time,unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
import server

class DestinationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='snu-destination-tests-')
        cls.patches=[patch.object(server,'SHARED',None),patch.object(server,'secret',return_value=''),
            patch.object(server,'saved_bus_key',return_value=None),patch.object(server,'RUNTIME',Path(cls.tmp.name)),
            patch('urllib.request.urlopen',side_effect=AssertionError('Offline destination test')),
            patch('time.time',return_value=datetime(2026,11,9,16,10,tzinfo=server.KST).timestamp())]
        for p in cls.patches:p.start()
        cls.app=server.Application()
    @classmethod
    def tearDownClass(cls):
        for p in reversed(cls.patches):p.stop()
        cls.tmp.cleanup()
    def test_four_targets_use_existing_official_stop_coordinates(self):
        ids={'snu-station':'120000150','nakseongdae':'120900119','daehak-town':'120000056','dormitory':'120900161'}
        self.assertEqual({d['id'] for d in self.app.destinations},set(ids))
        for d in self.app.destinations:
            stop=self.app.stops[ids[d['id']]]
            self.assertEqual((d['lat'],d['lon']),(stop['lat'],stop['lon']))
        self.assertIn('학부생활관',self.app.destinations[-1]['detail'])
    def test_every_target_has_connected_walking_and_transit_options(self):
        for dest in self.app.destinations:
            with self.subTest(destination=dest['id']):
                result=self.app.plan({'origin_id':'snu-410','destination_id':dest['id'],'departure_at':time.time(),
                    'mode':'estimate','preset':'fast','include_shuttle':True})
                self.assertGreater(len(result['candidates']),0)
                self.assertTrue(any(not c['route_names'] for c in result['candidates']))
                self.assertTrue(any(c['route_names'] for c in result['candidates']))
                for c in result['candidates']:
                    self.assertAlmostEqual(c['total_seconds'],sum(l['seconds'] for l in c['legs']),delta=1)
                    for l in c['legs']:
                        if l['type'] in ('walk','bus') and l['seconds']>0:self.assertGreaterEqual(len(l.get('geometry',[])),2)

if __name__=='__main__':unittest.main()
