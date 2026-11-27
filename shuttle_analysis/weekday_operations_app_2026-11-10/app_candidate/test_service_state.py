import http.client
import io
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import server
from service_state import StoragePausedState, PersistenceUnavailable


class StorageOutageTests(unittest.TestCase):
    def test_keyed_provider_is_blocked_even_in_a_new_instance(self):
        for state in (StoragePausedState(), StoragePausedState()):
            self.assertFalse(state.budget('2026-11-06', 'seoul_position', 900))
            self.assertFalse(state.budget('2026-11-06', 'kakao_walk', 800))
            self.assertIsNone(state.used('2026-11-06', 'seoul_position'))

    def test_public_cache_coalesces_concurrent_requests_without_blob(self):
        state = StoragePausedState()
        calls = []
        def produce():
            calls.append(1)
            return {'vehicles': [{'id': 'observed-test'}]}
        with patch('urllib.request.urlopen', side_effect=AssertionError('Unexpected network access')):
            with ThreadPoolExecutor(max_workers=4) as pool:
                values = list(pool.map(lambda _: state.cached('test', 15, produce), range(4)))
        self.assertEqual(len(calls), 1)
        values[0]['vehicles'].clear()
        self.assertEqual(len(state.read('cache-test')[0]['value']['vehicles']), 1)

    def test_persistence_is_unavailable_instead_of_silently_saving_to_tmp(self):
        state = StoragePausedState()
        with self.assertRaises(PersistenceUnavailable):
            state.add_observation({'is_test': True})
        self.assertFalse(state.info()['observations_available'])
        self.assertFalse(state.info()['blob_access_enabled'])

    def test_bootstrap_position_and_plan_still_work_with_all_blob_access_forbidden(self):
        state = StoragePausedState()
        with patch.object(server, 'SHARED', state):
            app = server.Application()
            with patch('urllib.request.urlopen', side_effect=AssertionError('Unexpected network access')):
                self.assertEqual(app.bootstrap()['version'], server.APP_VERSION)
                self.assertEqual(app.bootstrap()['historical_prediction']['model'],'weekday_history')
                status = app.transit.refresh()
                self.assertTrue(status['position_updates_paused'])
                self.assertEqual(status['vehicles'], [])
                result = app.plan({'origin_id': app.origins[0]['id'],
                                   'destination_id': 'snu-station', 'mode': 'estimate'})
            self.assertTrue(result['candidates'])
            self.assertEqual(result['historical_prediction']['model'],'weekday_history')
            self.assertIn(state.message, result['source_notes'])

    def test_three_shuttle_routes_query_the_provider_without_any_blob_requests(self):
        state = StoragePausedState()
        requests = []
        def respond(request, **kwargs):
            self.assertEqual(request.full_url, 'https://web.busin.co.kr/BuslineCircleS.aspx/GetRoute')
            route = json.loads(request.data)['data'].split(',')[2]
            requests.append(route)
            return io.BytesIO(json.dumps({'d': ''}).encode())
        with patch.object(server, 'SHARED', state):
            app = server.Application()
            with patch('urllib.request.urlopen', side_effect=respond):
                result = app.transit.shuttle.refresh()
                app.transit.shuttle.refresh()
        self.assertEqual(set(requests), {'41841', '41946', '41914', '41843', '41942','41842','41869','41868','41915','41916'})
        self.assertEqual(len(requests), 10)
        self.assertTrue(all(route['empty'] for route in result['routes']))

    def test_http_storage_status_and_write_failure_are_explicit(self):
        state = StoragePausedState()
        with patch.object(server, 'SHARED', state):
            app = server.Application()
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.make_handler(app))
            worker = threading.Thread(target=httpd.serve_forever, daemon=True)
            worker.start()
            try:
                client = http.client.HTTPConnection('127.0.0.1', httpd.server_port)
                client.request('GET', '/api/observations')
                response = client.getresponse()
                payload = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertFalse(payload['available'])
                client.request('POST', '/api/observations', json.dumps({
                    'candidate': 'test', 'planned_seconds': 600, 'actual_minutes': 10,
                    'satisfaction': 3, 'seated': 'unknown', 'is_test': True}),
                    {'Content-Type': 'application/json'})
                response = client.getresponse()
                payload = json.loads(response.read())
                self.assertEqual(response.status, 503)
                self.assertFalse(payload['saved'])
                client.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
                worker.join()


if __name__ == '__main__':
    unittest.main()
