import copy
import json
import tempfile
import threading
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch

from calculation_context import calculation_context,calculation_request
from queue_model_sync import LatestQueueModel,FEED,ORIGIN,strict_json
from queue_release import SCHEMA,ALGORITHM,compatibility,content_digest,digest,encode,release_name,release_time,stamp_model,validate

ROOT=Path(__file__).parent
KST=timezone(timedelta(hours=9))

class ModelSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.seed=json.loads((ROOT/'data/auto_queue_inputs.json').read_bytes())
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=stamp_model(copy.deepcopy(self.seed),datetime(2026,11,9,15,0,0,tzinfo=KST))
        self.path=Path(self.temp.name)/'base.json';self.path.write_bytes(encode(self.base))
        self.now=datetime(2026,11,9,16,0,tzinfo=KST).timestamp();self.calls=[]
        self.data=stamp_model(copy.deepcopy(self.base),datetime(2026,11,9,15,1,tzinfo=KST))
        self.feed,self.raw=self.release(self.data)
        self.q=LatestQueueModel(None,self.path,remote=True,fetch=self.fetch,clock=lambda:self.now)
    def release(self,data):
        name=data['model']['id'];meta={'model_id':name,'published_at':release_time(name).isoformat(),
            'algorithm_id':ALGORITHM,'compatibility_sha256':compatibility(data),'content_sha256':content_digest(data)}
        data['release']=meta;raw=encode(data)
        return {'schema':SCHEMA,**meta,'sha256':digest(raw),'bytes':len(raw),
            'payload_path':'/routing-model/releases/'+name+'.json'},raw
    def fetch(self,url,limit,timeout):
        self.calls.append(url)
        return encode(self.feed) if url==FEED else self.raw
    def test_names_use_korean_calendar_time_and_real_seconds(self):
        self.assertEqual(release_name(datetime(2026,11,9,5,52,4,tzinfo=timezone.utc)),'261109145204')
        for value in ('261332145204','261109246000','20261109145204','not-a-model'):
            with self.assertRaises(ValueError):release_time(value)
    def test_valid_update_uses_fresh_instance_and_clears_profiles(self):
        previous=self.q._active;previous.cache['old']='cached'
        self.assertEqual(self.q.info()['model_id'],'261109150100')
        self.assertIsNot(previous,self.q.current());self.assertEqual(self.q.cache,{})
        self.assertEqual(self.q.info()['sync']['payload_sha256'],digest(self.raw))
        self.assertEqual(len(self.calls),2)
    def test_poll_budget_and_unchanged_release_downloads_manifest_only(self):
        self.q.info()
        for _ in range(20):self.q.info()
        self.assertEqual(len(self.calls),2)
        self.now+=60;self.q.info();self.assertEqual(self.calls,[FEED,ORIGIN+self.feed['payload_path'],FEED])
    def test_invalid_release_keeps_last_model(self):
        mutations=[lambda f:f.update(sha256='0'*64),lambda f:f.update(payload_path='https://other.test/file'),
            lambda f:f.update(compatibility_sha256='0'*64),lambda f:f.update(bytes=5_000_000),
            lambda f:f.update(published_at='wrong'),lambda f:f.update(model_id='261109190000')]
        for change in mutations:
            with self.subTest(change=change):
                old=copy.deepcopy(self.feed);change(self.feed)
                previous=self.q._active;self.q.info();self.assertIs(self.q._active,previous)
                self.assertIsNotNone(self.q.info()['sync']['last_error'])
                self.feed=old;self.now+=61
    def test_network_failure_preserves_valid_model(self):
        self.q.info();previous=self.q._active;self.now+=61
        self.q._fetch=lambda *a:(_ for _ in ()).throw(TimeoutError())
        self.assertEqual(self.q.info()['model_id'],'261109150100');self.assertIs(previous,self.q._active)
        self.assertEqual(self.q.info()['sync']['status'],'last_valid_model')
    def test_same_name_cannot_change_and_older_release_cannot_revert(self):
        self.q.info();previous=self.q._active;self.now+=61
        self.feed['sha256']='0'*64;self.q.info()
        self.assertEqual(self.q._error,'immutable_release_changed');self.assertIs(previous,self.q._active)
        self.feed['model_id']='261109145900';self.feed['published_at']=release_time(self.feed['model_id']).isoformat()
        self.feed['payload_path']='/routing-model/releases/261109145900.json';self.now+=61;self.q.info()
        self.assertEqual(self.q._error,'older_release')
    def test_json_duplicates_nan_and_infinity_are_rejected(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}'):
            with self.assertRaises(ValueError):strict_json(raw)
    def test_unknown_algorithm_topology_and_invalid_mass_are_rejected(self):
        for change in (lambda d:d['model'].update(algorithm_id='new-engine'),
            lambda d:d['routes']['shuttle-41841']['stops'][0].update(id='other'),
            lambda d:d['routes']['shuttle-41841'].update(ready_packets=[[0,1,50000,-1,None]]),
            lambda d:d['model'].update(factor_bounds=['bad',1]),
            lambda d:d['model'].update(live_decay_seconds=0),
            lambda d:d['model'].update(phases=[.1]*100)):
            data=copy.deepcopy(self.data);change(data)
            with self.assertRaises(ValueError):validate(data,compatibility(self.base),check_profiles=True)
    def test_request_pins_model_while_other_request_updates(self):
        self.q._remote=False
        with calculation_context():
            old=self.q.current();self.q._remote=True
            result=[]
            thread=threading.Thread(target=lambda:result.append(self.q.current()))
            thread.start();thread.join(10);self.assertFalse(thread.is_alive())
            self.assertEqual(result[0].config['id'],'261109150100')
            self.assertIs(self.q.current(),old);self.assertEqual(self.q.info()['sync']['payload_sha256'],digest(self.path.read_bytes()))
        self.assertEqual(self.q.current().config['id'],'261109150100')
    def test_concurrent_requests_do_not_duplicate_download(self):
        entered=threading.Event();release=threading.Event();calls=[]
        def slow(url,*args):
            calls.append(url)
            if url==FEED:entered.set();release.wait(5)
            return self.fetch(url,*args)
        self.q._fetch=slow;thread=threading.Thread(target=self.q.current);thread.start()
        self.assertTrue(entered.wait(5));old=self.q._active
        self.assertIs(self.q.current(),old);release.set();thread.join(10)
        self.assertFalse(thread.is_alive());self.assertEqual(len(calls),2)
    def test_local_default_performs_no_external_requests(self):
        q=LatestQueueModel(None,self.path,remote=False,fetch=lambda *a:self.fail('unexpected HTTP'))
        self.assertEqual(q.info()['model_id'],'261109150000')
    def test_data_change_changes_actual_wait_without_collector_access(self):
        import server
        app=server.Application();service=app.transit.shuttle
        route=next(r for r in service.routes if r['id']=='shuttle-41841')
        index=next(i for i,s in enumerate(route['stops']) if s['id']=='snu-410' and s['board_allowed'])
        ready=self.now;before=self.q._active.arrival(route,index,ready,[],service.timetable,ready,{},False)
        mid=datetime(2026,11,9,tzinfo=KST).timestamp()
        self.data['routes'][route['id']]['ready_packets']=[[0,index,ready-mid-30,300,None]]
        self.feed,self.raw=self.release(self.data)
        with patch.object(self.q.terminal_wait,'cells',{}), patch('urllib.request.urlopen',side_effect=AssertionError('collector called')):
            after=self.q.arrival(route,index,ready,[],service.timetable,ready,{},False)
        self.assertNotEqual([v['wait_seconds'] for v in before],[v['wait_seconds'] for v in after])
        self.assertTrue(after);self.assertEqual(after[0]['automatic_queue']['model_id'],'261109150100')

    def supply_upgrade(self,pair=True):
        route=self.data['routes']['shuttle-41841']
        route.update(capacity=44,capacity_periods=[{'start_second':75600,'capacity':60}])
        if pair:route['dispatch_batches']=[{'start_second':54000,'end_second':68400,'vehicles':2}]
        self.feed,self.raw=self.release(self.data)

    def test_approved_supply_upgrade_changes_fleet_only_after_verified_payload(self):
        self.supply_upgrade();previous=self.q._active
        info=self.q.info();self.assertIsNot(previous,self.q._active)
        self.assertEqual(info['sync']['compatibility_sha256'],compatibility(self.data))
        self.assertEqual(self.q.data['routes']['shuttle-41841']['capacity'],44)
        self.assertEqual(previous.data['routes']['shuttle-41841']['capacity'],60)
        self.assertEqual(previous.data['routes']['shuttle-41946'],self.q.data['routes']['shuttle-41946'])

    def test_approved_manifest_does_not_allow_different_payload_supply(self):
        self.supply_upgrade();approved=self.feed['compatibility_sha256']
        self.data['routes']['shuttle-41841']['capacity_periods'][0]['capacity']=61
        self.feed,self.raw=self.release(self.data)
        self.feed['compatibility_sha256']=approved
        previous=self.q._active;self.q.info()
        self.assertIs(self.q._active,previous)
        self.assertEqual(self.q._error,'incompatible_clock_or_stops')

    def test_unapproved_supply_contract_is_rejected_before_payload_download(self):
        self.supply_upgrade()
        self.data['routes']['shuttle-41946']['capacity']=44
        self.feed,self.raw=self.release(self.data)
        previous=self.q._active;self.q.info()
        self.assertIs(self.q._active,previous)
        self.assertEqual(self.calls,[FEED])
        self.assertEqual(self.q._error,'incompatible_clock_or_stops')

    def test_upgraded_model_cannot_silently_return_to_scalar_60_with_newer_name(self):
        self.supply_upgrade();self.q.info();previous=self.q._active
        self.data=stamp_model(copy.deepcopy(self.base),datetime(2026,11,9,15,2,tzinfo=KST))
        self.feed,self.raw=self.release(self.data);self.now+=61;self.q.info()
        self.assertIs(self.q._active,previous)
        self.assertEqual(self.q._error,'incompatible_clock_or_stops')

    def test_request_pins_capacity_contract_and_payload_during_upgrade(self):
        self.supply_upgrade();self.q._remote=False
        with calculation_context():
            old=self.q.current();old_compat=compatibility(old.data);self.q._remote=True
            result=[];thread=threading.Thread(target=lambda:result.append(self.q.current()))
            thread.start();thread.join(10);self.assertFalse(thread.is_alive())
            self.assertEqual(result[0].data['routes']['shuttle-41841']['capacity'],44)
            self.assertIs(self.q.current(),old)
            info=self.q.info()['sync']
            self.assertEqual(info['compatibility_sha256'],old_compat)
            self.assertEqual(info['payload_sha256'],digest(self.path.read_bytes()))
        self.assertEqual(self.q.current().data['routes']['shuttle-41841']['capacity'],44)

if __name__=='__main__':unittest.main()
