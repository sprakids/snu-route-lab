import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from automatic_queue import AutomaticQueue
from calculation_context import calculation_context
from city_operations import CityOperations,validate_operations
from city_wait import project,profile
from continuity import Continuity
from queue_model_sync import LatestQueueModel,FEED
from queue_release import OPERATIONS_ALGORITHM,SCHEMA,compatibility,content_digest,digest,encode,release_time,stamp_model,validate
from shuttle_timetable import KST
from travel_time import TravelTime

ROOT=Path(__file__).parent

def at(clock='2026-11-10T16:59:30'):
    return datetime.fromisoformat(clock).replace(tzinfo=KST).timestamp()

def fixture():
    network_raw=(ROOT/'data/network.json').read_bytes();network=json.loads(network_raw)
    spec={'schema':'snu_city_operations_v1','revision':'test_operations_v8',
        'network_sha256':digest(network_raw),'coverage_start_seconds':40800,'coverage_end_seconds':83400,
        'weekdays':list(range(5)),'source_dates':['2026-11-09'],'transfer_estimate':True,
        'includes_destination_dwell':True,'dwell_added_separately':False,'routes':{}}
    for route in network['routes']:
        spec['routes'][route['id']]={'stops':[{k:s[k] for k in ('id','seq')} for s in route['stops'][:3]],
            'departures':{str(d):[61080,61170,61800,62220] for d in range(5)},
            'segment_profiles':{str(d):[[0,61200,[60,60]],[61200,172800,[120,120]]] for d in range(5)}}
    return spec,network,network_raw

def release_data(spec):
    data=json.loads((ROOT/'data/auto_queue_inputs.json').read_bytes())
    data['city_operations']=spec
    data['city_wait'].update(delay_scale_policy='absolute_audited_clock',operation_revision=spec['revision'])
    return stamp_model(data,datetime(2026,11,10,10,1,tzinfo=KST))

class OperationsClockTests(unittest.TestCase):
    def setUp(self):
        self.spec,self.network,self.raw=fixture();self.route=self.network['routes'][0]
        self.ops=CityOperations(self.spec,'261110100100')

    def test_actual_contract_mapping_and_unsafe_clocks(self):
        validate_operations(self.spec,self.network,digest(self.raw))
        mutations=[lambda x:x.update(network_sha256='0'*64),lambda x:x.update(dwell_added_separately=True),
            lambda x:x['routes'][self.route['id']]['stops'][1].update(id='wrong-direction'),
            lambda x:x['routes'][self.route['id']]['segment_profiles']['0'][1].__setitem__(0,61201),
            lambda x:x['routes'][self.route['id']]['segment_profiles']['0'][0][2].__setitem__(0,float('nan')),
            lambda x:x['routes'][self.route['id']]['departures']['0'].reverse()]
        for mutate in mutations:
            data=copy.deepcopy(self.spec);mutate(data)
            with self.assertRaises(ValueError):validate_operations(data,self.network,digest(self.raw))

    def test_entry_clock_crosses_the_hour_and_never_adds_dwell_twice(self):
        # 16:59:30 + 60s enters the second segment after 17:00:00.
        self.assertEqual(self.ops.timeline(self.route['id'],1)[2][1],61350)
        travel=TravelTime();travel.operations=lambda:self.ops
        value=travel.estimate(self.route,0,2,at(),{},False)
        self.assertEqual(value['seconds'],180)
        self.assertEqual(value['source'],'weekday_transfer_operations')
        self.assertEqual(value['model_id'],'261110100100')

    def test_irregular_next_opportunity_keeps_exact_clock(self):
        ready=at('2026-11-10T16:59:40')
        value=self.ops.service(self.route,0,ready)
        self.assertEqual(value['departure_at'],at('2026-11-10T17:10:00'))
        value=self.ops.service(self.route,1,at('2026-11-10T17:00:00'))
        self.assertEqual(value['departure_at'],at('2026-11-10T17:00:30'))

    def test_phase_conditioning_and_full_service_skip_use_the_same_calendar(self):
        ready=at('2026-11-10T16:59:40')
        value=self.ops.service(self.route,0,ready,anchor=at('2026-11-10T16:58:30'))
        self.assertEqual(value['departure_at'],at('2026-11-10T17:00:00'))
        self.assertTrue(value['phase_conditioned'])
        value=self.ops.service(self.route,0,ready,blocked=[at('2026-11-10T17:10:00')])
        self.assertEqual(value['departure_at'],at('2026-11-10T17:17:00'))

    def test_uncovered_routes_times_and_weekends_do_not_extrapolate(self):
        for clock in ('2026-11-14T17:00:00','2026-11-10T23:20:00','2026-11-10T10:00:00'):
            self.assertIsNone(self.ops.service(self.route,0,at(clock)))
        self.assertIsNone(self.ops.service(self.route,3,at()))
        self.assertIsNone(self.ops.segment_seconds(self.route,2,at()))

    def test_all_five_weekdays_use_transferred_data(self):
        for day in range(9,14):
            value=self.ops.service(self.route,0,at(f'2026-11-{day:02}T16:59:40'))
            self.assertIsNotNone(value)
            self.assertTrue(value['operations']['transfer_estimate'])
            self.assertFalse(value['operations']['observed_operations'])

    def test_fresh_speed_and_multiday_completed_time_remain_priorities(self):
        travel=TravelTime();travel.operations=lambda:self.ops;now=at()
        sections={str(s['seq']):{'speed_kmh':20} for s in self.route['stops']}
        snapshot={'traffic':{self.route['id']:{'fetched_at':now,'sections':sections}}}
        with patch('time.time',return_value=now):
            value=travel.estimate(self.route,0,2,now,snapshot,True)
        self.assertEqual(value['source'],'current_section_speed')
        self.assertEqual(value['city_operations_segments'],0)
        pair=f'{self.route["id"]}:1:3'
        value=travel.estimate(self.route,0,2,now,{'travel_history':{pair:{'n':5,'days':2,'median_seconds':390,'p10_seconds':300,'p90_seconds':500}}},True)
        self.assertEqual(value['source'],'measured_history');self.assertEqual(value['seconds'],390)

    def test_historical_service_cannot_read_current_arrival_anchor(self):
        ready=at('2026-11-10T16:59:40')
        model=SimpleNamespace(operations=self.ops)
        transit=SimpleNamespace(now=lambda:ready,automatic_queue=model,in_service=lambda r,t:True,
            interval=lambda r,t:r['interval_minutes'],cache={(self.route['id'],1):{'values':[
                {'provided_at':ready-1,'departure_at':at('2026-11-10T16:58:30')}]}})
        old=Continuity().service(transit,self.route,0,ready,live=False)
        live=Continuity().service(transit,self.route,0,ready,live=True)
        self.assertEqual(old['departure_at'],at('2026-11-10T17:10:00'))
        self.assertEqual(live['departure_at'],at('2026-11-10T17:00:00'))
        self.assertIsNone(live['vehicle_id']);self.assertIsNone(live['provided_at'])
        self.assertFalse(old['arrival_forecast']['phase_conditioned'])

    def test_pooled_weekend_dates_cannot_override_a_transferred_weekday_clock(self):
        travel=TravelTime();travel.operations=lambda:self.ops;now=at()
        learned={'weekday':1,'hour':16,'dates':['2026-11-08','2026-11-09'],'cohort':'pooled_hour',
            'sections':{str(s['seq']):{'speed_kmh':20,'days':2} for s in self.route['stops']}}
        snapshot={'historical_traffic':{self.route['id']:learned}}
        value=travel.estimate(self.route,0,2,now,snapshot,False)
        self.assertEqual(value['source'],'weekday_transfer_operations');self.assertEqual(value['seconds'],180)
        learned['dates']=['2026-10-27','2026-11-03']
        value=travel.estimate(self.route,0,2,now,snapshot,False)
        self.assertEqual(value['source'],'historical_section_speed');self.assertEqual(value['city_operations_segments'],0)

class OperationsReleaseTests(unittest.TestCase):
    def setUp(self):
        self.spec,self.network,self.network_raw=fixture();self.data=release_data(self.spec)

    def test_new_clock_requires_new_reader_and_keeps_the_base_shuttle_contract(self):
        base=json.loads((ROOT/'data/auto_queue_inputs.json').read_bytes())
        self.assertEqual(self.data['model']['algorithm_id'],OPERATIONS_ALGORITHM)
        self.assertEqual(compatibility(self.data),compatibility(base))
        validate(self.data,compatibility(base))
        path=ROOT/'test_fixtures/queue_release_v3_contract.py'
        spec=importlib.util.spec_from_file_location('old_queue_contract_for_test',path)
        old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        with self.assertRaisesRegex(ValueError,'algorithm'):old.validate(self.data,compatibility(base))

    def test_mismatched_queue_and_operations_revision_are_rejected(self):
        self.data['city_wait']['operation_revision']='different'
        with self.assertRaisesRegex(ValueError,'operations_fifo_clock'):validate(self.data,compatibility(self.data))

    def test_v8_fifo_delay_is_absolute_and_not_scaled_by_headway_again(self):
        route=self.network['routes'][0];key=f'{route["id"]}:1';now=at('2026-11-10T16:00:00')
        self.data['city_wait']['profiles']['1:'+key]=[[960,120,1,50,0]]
        self.data['city_wait']['services'][key]['reference_headway_seconds']=600
        model=AutomaticQueue(None,data=self.data)
        transit=SimpleNamespace(now=lambda:now,in_service=lambda r,t:True,interval=lambda r,t:7)
        value=project(model,transit,route,0,now,{'departure_at':now+60},False,history={},headway=1200)
        self.assertEqual(value['city_wait']['extra_wait_seconds'],120)
        self.assertEqual(value['city_wait']['simulation_delay_scale_policy'],'absolute_audited_clock')

    def test_weekday_reference_headways_do_not_use_the_last_written_day(self):
        city=self.data['city_wait'];key=next(iter(city['services']))
        city['services'][key]['reference_headway_by_weekday']={str(day):600+day*60 for day in range(5)}
        self.assertEqual(profile(city,key,at('2026-11-10T16:00:00'))['reference_headway_seconds'],660)

    def test_atomic_model_refresh_pins_wait_and_travel_for_one_calculation(self):
        def pack(data):
            name=data['model']['id'];meta={'model_id':name,'published_at':release_time(name).isoformat(),
                'algorithm_id':data['model']['algorithm_id'],'compatibility_sha256':compatibility(data),'content_sha256':content_digest(data)}
            data['release']=meta;raw=encode(data)
            return {'schema':SCHEMA,**meta,'bytes':len(raw),'sha256':digest(raw),'payload_path':f'/routing-model/releases/{name}.json'},raw
        feed,raw=pack(self.data);current=[feed,raw];clock=[at('2026-11-10T12:00:00')]
        with tempfile.TemporaryDirectory() as temp:
            seed=Path(temp)/'seed.json';seed.write_bytes((ROOT/'data/auto_queue_inputs.json').read_bytes())
            q=LatestQueueModel(None,seed,remote=True,clock=lambda:clock[0],fetch=lambda url,*args:encode(current[0]) if url==FEED else current[1])
            with calculation_context():
                self.assertEqual(q.operations.model_id,'261110100100')
                updated=copy.deepcopy(self.data);updated['city_operations']['routes'][self.network['routes'][0]['id']]['segment_profiles']['1'][0][2][0]=90
                stamp_model(updated,datetime(2026,11,10,10,2,tzinfo=KST));current[:]=pack(updated);clock[0]+=61
                self.assertEqual(q.operations.model_id,'261110100100')
                self.assertEqual(q.config['id'],'261110100100')
            self.assertEqual(q.operations.model_id,'261110100200')
            self.assertEqual(q.operations.data['routes'][self.network['routes'][0]['id']]['segment_profiles']['1'][0][2][0],90)

if __name__=='__main__':unittest.main()
