import importlib.util
import json
import math
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from historical_forecast import HistoricalForecast,KST

ROOT=Path(__file__).resolve().parent

class HistoricalForecastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=HistoricalForecast()
        cls.network=json.loads((ROOT/'data/network.json').read_text(encoding='utf-8'))

    def at(self,day=9,hour=12,minute=0):
        return datetime(2026,11,day,hour,minute,tzinfo=KST).timestamp()

    def test_compact_export_matches_all_14245_frozen_weekday_values(self):
        source=ROOT.parent/'hybrid_prediction_2026-11-07/predictor.py'
        spec=importlib.util.spec_from_file_location('research_predictor',source)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        reference=module.FrozenPredictor(source.parent/'frozen_models.json')
        checked=0
        for row in self.model.profiles.values():
            rid,seq,a,b=self.model.payload['segments'][row[0]]
            for weekday in range(5):
                actual=self.model.point(rid,seq,a,b,self.at(9+weekday,row[1]))
                expected=reference.predict(f'202611{9+weekday:02d}',rid,seq,a,b,row[1])['weekday_history']
                self.assertTrue(actual['available']);self.assertAlmostEqual(actual['predicted_sum_load'],expected,delta=.00000051)
                checked+=1
        self.assertEqual(checked,14245)

    def test_weekend_and_hour_bounds_are_unknown_not_zero(self):
        rid,seq,a,b=self.model.payload['segments'][0]
        for when in (self.at(7),self.at(9,11),self.at(9,23)):
            result=self.model.point(rid,seq,a,b,when)
            self.assertFalse(result['available']);self.assertNotIn('predicted_sum_load',result)
        self.assertTrue(self.model.point(rid,seq,a,b,self.at(9,22,59))['available'])

    def test_kst_and_wrong_direction_do_not_silently_match(self):
        rid,seq,a,b=self.model.payload['segments'][0]
        self.assertEqual(self.model.point(rid,seq,a,b,self.at())['hour'],12)
        self.assertFalse(self.model.point(rid,seq,b,a,self.at())['available'])

    def test_repeated_endpoints_keep_their_sequence(self):
        groups={}
        for rid,seq,a,b in self.model.payload['segments']:groups.setdefault((rid,a,b),[]).append(seq)
        rid,a,b=next(k for k,v in groups.items() if len(v)>1)
        for seq in groups[(rid,a,b)]:
            point=self.model.point(rid,seq,a,b,self.at())
            index=self.model.segments[(rid,seq,a,b)]
            self.assertEqual(point['predicted_sum_load'],self.model.profiles[(index,12)][3][0])

    def test_actual_zero_forecast_is_available(self):
        model=deepcopy(self.model);rid,seq,a,b=model.payload['segments'][0]
        profile=model.profiles[(0,12)];profile[3][0]=0.
        self.assertTrue(model.point(rid,seq,a,b,self.at())['available'])
        self.assertEqual(model.point(rid,seq,a,b,self.at())['predicted_sum_load'],0.)

    def test_ride_entry_hours_partial_coverage_and_live_crowd_preserved(self):
        route=self.network['routes'][0]
        planner=SimpleNamespace(by_id={route['id']:route},ride_seconds=lambda r,i,j:(j-i)*120)
        candidate={'route_names':[route['name']],'score':4.5,'crowd_cost':None,'total_seconds':240,
                   'legs':[{'type':'bus','route_id':route['id'],'from_seq':route['stops'][0]['seq'],
                            'to_seq':route['stops'][2]['seq'],'seconds':240,'departure_at':self.at(9,22,59),
                            'crowd_cost':None,'crowd_label':'정보 없음'}]}
        plan={'candidates':[candidate]};self.model.attach(plan,planner)
        forecast=candidate['historical_forecast']
        self.assertTrue(forecast['partial']);self.assertEqual(forecast['matched_segments'],1)
        self.assertEqual(forecast['total_segments'],2)
        self.assertEqual(forecast['mean_sum_load'],forecast['segments'][0]['predicted_sum_load'])
        self.assertFalse(forecast['segments'][1]['available'])
        self.assertEqual(candidate['score'],4.5);self.assertIsNone(candidate['crowd_cost'])
        self.assertEqual(candidate['total_seconds'],240);self.assertIsNone(candidate['legs'][0]['crowd_cost'])

    def test_shuttle_is_not_given_city_bus_history(self):
        planner=SimpleNamespace(by_id={'shuttle-test':{'kind':'shuttle'}})
        c={'route_names':['셔틀'],'legs':[{'type':'bus','route_id':'shuttle-test'}]}
        self.model.attach({'candidates':[c]},planner)
        self.assertFalse(c['historical_forecast']['available'])
        self.assertEqual(c['historical_forecast']['shuttle_legs_without_history'],1)
        self.assertIsNone(c['historical_forecast']['mean_sum_load'])

    def test_all_current_network_links_have_exact_history_keys(self):
        keys={(r['id'],str(a['seq']),a['id'],b['id']) for r in self.network['routes']
              for a,b in zip(r['stops'],r['stops'][1:])}
        self.assertEqual(keys,set(self.model.segments))

if __name__=='__main__':unittest.main()
