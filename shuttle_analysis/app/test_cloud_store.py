import copy
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from cloud_store import CloudStore, Conflict

class MemoryCloud(CloudStore):
    def __init__(self,backend=None):
        self.backend=backend if backend is not None else ({},threading.Lock())
    def read(self,key):
        data,lock=self.backend
        with lock:
            value,version=data.get(key,({},None))
            return copy.deepcopy(value),version
    def write(self,key,value,etag):
        data,lock=self.backend
        with lock:
            version=data.get(key,({},None))[1]
            if version!=etag:raise Conflict()
            data[key]=(copy.deepcopy(value),(version or 0)+1)

class CloudStateTests(unittest.TestCase):
    def test_connected_store_token_takes_precedence_over_local_oidc(self):
        with patch.dict('os.environ',{'BLOB_STORE_ID':'store_test','BLOB_READ_WRITE_TOKEN':'store-scoped-test-token','VERCEL_OIDC_TOKEN':'other-environment-test-token'}):
            self.assertEqual(CloudStore().headers()['Authorization'],'Bearer store-scoped-test-token')

    def test_two_instances_share_one_quota(self):
        first=MemoryCloud();second=MemoryCloud(first.backend)
        with ThreadPoolExecutor(max_workers=2) as pool:
            accepted=list(pool.map(lambda store:store.budget('2026-11-06','api',1),[first,second]))
        self.assertEqual(sum(accepted),1)
        self.assertEqual(first.used('2026-11-06','api'),1)

    def test_storage_failure_does_not_allow_an_unaccounted_api_call(self):
        store=MemoryCloud()
        with patch.object(store,'read',side_effect=RuntimeError('offline')):
            self.assertFalse(store.budget('2026-11-06','api',900))

    def test_shared_cache_fetches_once_across_instances(self):
        first=MemoryCloud();second=MemoryCloud(first.backend);calls=[]
        def produce():calls.append(1);return {'captured_at':1,'vehicles':[{'id':'observed'}]}
        self.assertEqual(first.cached('shuttle',15,produce),second.cached('shuttle',15,produce))
        self.assertEqual(len(calls),1)

    def test_conditional_conflict_retries_without_overwriting_another_change(self):
        store=MemoryCloud();store.budget('2026-11-06','api',10)
        original=store.write;calls=[]
        def conflicting(key,value,etag):
            if not calls:
                calls.append(1);original(key,{'api':2},etag);raise Conflict()
            original(key,value,etag)
        with patch.object(store,'write',side_effect=conflicting):
            self.assertTrue(store.budget('2026-11-06','api',10))
        self.assertEqual(store.used('2026-11-06','api'),3)

    def test_observations_survive_a_new_instance_without_duplicate_ids(self):
        first=MemoryCloud();second=MemoryCloud(first.backend)
        with ThreadPoolExecutor(max_workers=2) as pool:
            identifiers=list(pool.map(lambda store:store.add_observation({'is_test':True}),[first,second]))
        self.assertEqual(sorted(identifiers),[1,2])
        self.assertEqual(len(MemoryCloud(first.backend).observations()),2)

if __name__=='__main__':unittest.main(verbosity=2)
