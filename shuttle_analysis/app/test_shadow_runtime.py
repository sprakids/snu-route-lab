import copy,json,time,unittest
from pathlib import Path
from unittest.mock import patch
from calculation_context import calculation_context,calculation_now,refresh_calculation_clock
from shadow_runtime import encode_ticket,decode_ticket,capture_walks,summarize,MODEL,MAX_RAW,shuttle_provider
from shadow_shuttle import supported,ShadowQueue,ShuttleTravel
from automatic_queue import simulate

class ShadowTests(unittest.TestCase):
    def test_global_gate_replacement_is_forbidden(self):
        from shadow_transport.candidate_runtime import install_candidate
        with self.assertRaisesRegex(ValueError,'Global gate replacement'):
            install_candidate(None,None,set(),'fixture',patch_gate=True)
    def test_shuttle_proxy_denies_anonymous_requests_before_network(self):
        from types import SimpleNamespace
        with patch('urllib.request.urlopen',side_effect=AssertionError('network forbidden')):
            self.assertEqual(shuttle_provider({'routes':['41841']},None,SimpleNamespace(token='fixture'))[1],401)
            self.assertEqual(shuttle_provider({'routes':['not-a-route']},'Bearer fixture',SimpleNamespace(token='fixture'))[1],400)
    def test_signed_ticket_ttl_tamper_and_version(self):
        p={'issued_at':100,'candidate':MODEL,'point':[37.46,126.95]};ticket=encode_ticket(p,'test-only')
        self.assertEqual(decode_ticket(ticket,'test-only',150),p)
        with self.assertRaises(ValueError):decode_ticket(ticket,'other',150)
        with self.assertRaises(ValueError):decode_ticket(ticket,'test-only',281)
        with self.assertRaises(ValueError):decode_ticket(encode_ticket({**p,'candidate':'other'},'test-only'),'test-only',150)
    def test_pinned_clock_never_changes_public_default(self):
        with calculation_context(123):refresh_calculation_clock();self.assertEqual(calculation_now(),123)
        with patch('calculation_context.time.time',side_effect=[200,201]):
            with calculation_context():refresh_calculation_clock();self.assertEqual(calculation_now(),201)
    def test_walk_capture_does_not_include_other_visitors_cache(self):
        from types import SimpleNamespace
        p=SimpleNamespace(walk_observer=None,local_walks={'previous-exact-location':1})
        with capture_walks(p) as values:p.walk_observer((1,2,3,4),{'seconds':7})
        self.assertEqual(list(values),[(1,2,3,4)]);self.assertIsNone(p.walk_observer)
    def test_storage_summary_excludes_exact_origin_and_geometry(self):
        p={'origin':{'lat':37,'lon':126},'candidates':[{'id':'one','legs':[{'type':'walk','geometry':[[37,126]],'seconds':10}],
            'total_seconds':10,'walk_seconds':10,'wait_seconds':0}]}
        text=json.dumps(summarize(p));self.assertNotIn('"geometry"',text);self.assertNotIn('"lat"',text);self.assertNotIn('"origin"',text)
    def test_observed_support_requires_two_days_and_five_bounded_completions(self):
        rows=[{'day':'2026-11-14' if i%2 else '2026-11-15','lo':250,'hi':310,'seconds':280,'known_at':100+i} for i in range(6)]
        self.assertIsNotNone(supported(rows,110));self.assertIsNone(supported(rows[:4],110));self.assertIsNone(supported(rows,101))
        self.assertIsNone(supported([{**r,'day':'one'} for r in rows],110))
        self.assertIsNone(supported([{**r,'lo':0,'hi':1000} for r in rows],110))
    def test_no_shuttle_support_returns_exact_legacy_travel(self):
        from types import SimpleNamespace
        base={'available':True,'seconds':321,'source':'old'}
        wrapper=ShuttleTravel(SimpleNamespace(estimate=lambda *a:base),{},100)
        self.assertIs(wrapper.estimate({'kind':'shuttle','id':'shuttle-41841','stops':[{},{}]},0,1,100),base)
    def test_clock_keeps_fixed_departures_and_paired_vehicle_contract(self):
        from automatic_queue import dispatches
        head={'interval_samples':[180,210,150,180,180]}
        self.assertEqual(ShadowQueue.empirical_clock('shuttle-41914',.5,16,head),dispatches('shuttle-41914',.5))
        base=dispatches('shuttle-41841',.5);value=ShadowQueue.empirical_clock('shuttle-41841',.5,16,head)
        self.assertEqual([x for x in value if x<15*3600 or x>=18*3600],[x for x in base if x<15*3600 or x>=18*3600])
    def test_opt_in_clock_does_not_change_default_simulation_or_person_conservation(self):
        route={'id':'shuttle-41946','n':2,'loop':True,'offsets':[0,30,60,90],'anchor':0,'capacity':60,
               'stops':[{'board_allowed':True},{'board_allowed':True}],
               'flows':[[0,0,480,50.],[0,1,480,30.]],'od':{'0:0':[[2,1.]],'0:1':[[1,1.]]}}
        a=simulate(route,0,.5,1,0,lambda i,t:1.)
        b=simulate(route,0,.5,1,0,lambda i,t:1.,dispatch_times=None)
        self.assertEqual(a,b)
        c=simulate(route,0,.5,1,0,lambda i,t:1.,dispatch_times=[15*3600,15*3600+180])
        self.assertAlmostEqual(c['input_mass'],c['boarded_mass']+c['remaining_mass']+c.get('exited_mass',0))

if __name__=='__main__':unittest.main()
