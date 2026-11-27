import json,time,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import server

class ArrivalPreviewTests(unittest.TestCase):
    def setUp(self):
        self.network=json.loads((Path(__file__).parent/'data/network.json').read_text(encoding='utf-8'))
        self.transit=server.Transit(self.network)
        self.transit.shuttle=SimpleNamespace(routes=[])
        self.route=self.network['routes'][0];self.seq=self.route['stops'][0]['seq']

    def test_arrival_refresh_does_not_collect_positions(self):
        def fill(pair):
            self.transit.cache[(self.route['id'],self.seq)]={'fetched_at':time.time(),'values':[{'departure_at':time.time()+222,'provided_at':time.time(),'vehicle_id':'fixture-only'}]}
        with patch.object(self.transit,'fetch_arrivals',side_effect=fill),patch.object(self.transit,'position',side_effect=AssertionError('No position call allowed')):
            result=self.transit.arrival_preview([{'route_id':self.route['id'],'seq':self.seq}])
        self.assertEqual(result['position_calls_triggered'],0)
        self.assertEqual(result['stops'][0]['values'][0]['vehicle_id'],'fixture-only')

    def test_invalid_or_unbounded_stops_are_rejected(self):
        for targets in (None,[{}],['invalid'],[{'route_id':'unknown','seq':1}],[{}]*5):
            with self.assertRaises(ValueError):self.transit.arrival_preview(targets)

if __name__=='__main__':unittest.main()
