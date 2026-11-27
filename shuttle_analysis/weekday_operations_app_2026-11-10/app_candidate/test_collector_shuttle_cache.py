import unittest
from unittest.mock import Mock
from collector_client import CollectorState
from service_state import PersistenceUnavailable


class SharedShuttleCacheTests(unittest.TestCase):
    def test_failed_claim_reads_last_observation_without_fetching_source(self):
        shared=CollectorState('https://fixture','fixture')
        old={'captured_at':123,'vehicles':[{'id':'reverse-fixture'}],'error':None}
        shared.request=Mock(side_effect=[PersistenceUnavailable('write guard'),{'value':old}])
        producer=Mock()
        self.assertEqual(shared.cached('shuttle-v2-41914',15,producer),old)
        producer.assert_not_called()
        self.assertEqual(shared.request.call_args.args[1]['action'],'read')

    def test_failed_publish_keeps_the_valid_source_observation(self):
        shared=CollectorState('https://fixture','fixture')
        shared.request=Mock(side_effect=[{'owned':True,'owner':'fixture'},PersistenceUnavailable('restart')])
        fresh={'captured_at':456,'vehicles':[{'id':'reverse-fixture'}],'error':None}
        producer=Mock(return_value=fresh)
        self.assertEqual(shared.cached('shuttle-v2-41914',15,producer),fresh)
        producer.assert_called_once()

    def test_failed_claim_and_read_never_call_the_source(self):
        shared=CollectorState('https://fixture','fixture')
        shared.request=Mock(side_effect=PersistenceUnavailable('offline'))
        producer=Mock()
        self.assertIsNone(shared.cached('shuttle-v2-41914',15,producer))
        producer.assert_not_called()


if __name__=='__main__':unittest.main()
