"""Speed changes must preserve fresh inputs, isolated searches and path rules."""
import gzip,heapq,http.client,json,threading,unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from calculation_context import calculation_context,calculation_now,memoized,refresh_calculation_clock
from road_geometry import RoadGeometry
from routing import WalkingGraph,distance
from test_walking_lookup import network
import server
from types import SimpleNamespace
from shuttle_live import ShuttleService

class CalculationPerformanceTests(unittest.TestCase):
    def test_memo_is_request_local_and_resets_after_exception(self):
        calls=[]
        def produce():calls.append(1);return len(calls)
        with self.assertRaises(RuntimeError):
            with calculation_context():
                self.assertEqual(memoized('x',1,produce),1)
                self.assertEqual(memoized('x',1,produce),1)
                raise RuntimeError('test')
        with calculation_context():self.assertEqual(memoized('x',1,produce),2)
        self.assertEqual(memoized('x',1,produce),3)

    def test_simultaneous_contexts_do_not_share_forecasts(self):
        barrier=threading.Barrier(2)
        def query(value):
            with calculation_context():
                result=memoized('x',1,lambda:value);barrier.wait()
                return result,memoized('x',1,lambda:999)
        with ThreadPoolExecutor(2) as pool:self.assertEqual(list(pool.map(query,[10,20])),[(10,10),(20,20)])

    def test_one_search_clock_is_stable_but_next_search_is_fresh(self):
        with patch('calculation_context.time.time',side_effect=[100.,101.,102.]):
            with calculation_context():self.assertEqual((calculation_now(),calculation_now()),(100.,100.))
            with calculation_context():self.assertEqual(calculation_now(),101.)
            self.assertEqual(calculation_now(),102.)

    def test_grid_lookup_matches_full_scan_at_cell_boundaries(self):
        graph=WalkingGraph(network())
        for a in (-.00001,0.,.00001,.00099,.001):
            for b in (-.00001,0.,.00001,.00099,.001):
                point=(37.46+a,126.95+b)
                choices=heapq.nsmallest(24,graph.points,key=lambda x:(x[1][0]-point[0])**2+((x[1][1]-point[1])*.794)**2)
                expected=next(((n,distance(point,p)) for n,p in choices if distance(point,p)<=30 and not graph.buildings.blocked(point,p)),None)
                self.assertEqual(graph.visible_node(point),expected)

    def test_network_prefetch_can_advance_the_frozen_clock(self):
        with patch('calculation_context.time.time',side_effect=[100.,107.]):
            with calculation_context():
                self.assertEqual(calculation_now(),100.)
                refresh_calculation_clock()
                self.assertEqual(calculation_now(),107.)

    def test_road_cache_keeps_directed_and_missing_legs_distinct(self):
        road=RoadGeometry();rid=next(iter(road.routes));route={'id':rid}
        with patch.object(road,'_leg',wraps=road._leg) as compute:
            first=road.leg(route,0,1)
            self.assertEqual(road.leg(route,0,1),first)
            self.assertIsNone(road.leg(route,1,0))
            self.assertIsNone(road.leg(route,1,0))
            self.assertEqual(compute.call_count,2)

    def test_selective_shuttle_reads_are_throttled_per_line_even_on_miss(self):
        reads=[]
        service=ShuttleService.__new__(ShuttleService)
        service.last_cache_load=0;service.cache_load_times={}
        service.transit=SimpleNamespace(shared=SimpleNamespace(read=lambda key:(reads.append(key) or {},None)))
        service.lines={rid:SimpleNamespace(route={'id':rid},status=lambda:{'stale':True}) for rid in ('41946','41914','41841')}
        with patch('shuttle_live.time.time',return_value=100.):
            service.load_cached_positions({'41946'});service.load_cached_positions({'41946'})
            service.load_cached_positions({'41914'})
        self.assertEqual(reads,['cache-shuttle-v2-41946','cache-shuttle-v2-41914'])
        with patch('shuttle_live.time.time',return_value=116.):service.load_cached_positions({'41946'})
        self.assertEqual(len(reads),3)

    def test_warm_arrivals_skip_remote_read_only_within_existing_ttl(self):
        transit=server.Transit.__new__(server.Transit);calls=[]
        transit.shared=SimpleNamespace(cached=lambda *args:calls.append(args[0]) or {'fetched_at':1060.,'values':[]})
        route={'id':'test','stops':[{'seq':1}]};key=('test',1)
        transit.cache={key:{'fetched_at':1000.,'values':[]}}
        with patch('server.time.time',return_value=1059.):transit.fetch_arrivals((route,0))
        self.assertEqual(calls,[])
        with patch('server.time.time',return_value=1060.):transit.fetch_arrivals((route,0))
        self.assertEqual(calls,['arrivals-test-1'])

    def test_json_compression_round_trip_and_timing_header(self):
        handler=server.make_handler(None)
        payload={'candidates':['가'*10000],'performance':{'routing_ms':12.3,'execution':'server'}}
        class Probe(handler):
            def do_GET(self):return self.send_json(200,payload)
            def log_message(self,*args):pass
        httpd=ThreadingHTTPServer(('127.0.0.1',0),Probe)
        worker=threading.Thread(target=httpd.serve_forever,daemon=True);worker.start()
        try:
            client=http.client.HTTPConnection('127.0.0.1',httpd.server_port)
            for compressed in (False,True):
                client.request('GET','/api/plan',headers={'Accept-Encoding':'gzip' if compressed else 'identity'})
                response=client.getresponse();raw=response.read()
                self.assertIn('routing;dur=12.3',response.getheader('Server-Timing'))
                if compressed:
                    self.assertEqual(response.getheader('Content-Encoding'),'gzip');self.assertLess(len(raw),1000);raw=gzip.decompress(raw)
                self.assertEqual(json.loads(raw),payload)
            client.close()
        finally:httpd.shutdown();httpd.server_close();worker.join()

if __name__=='__main__':unittest.main()
