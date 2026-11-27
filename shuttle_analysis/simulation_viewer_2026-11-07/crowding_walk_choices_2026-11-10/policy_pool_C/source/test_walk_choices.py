import contextlib,gzip,io,json,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
import walk_choice_model as model
from test_city_capacity import fixture,leg

class WalkingBehaviorTests(unittest.TestCase):
    def test_short_walk_plateau_and_long_walk_decay(self):
        self.assertEqual([model.walking_weight(d) for d in (0,100,300,500)],[1.]*4)
        weights=[model.walking_weight(d) for d in (500,800,1000,1200,1500)]
        self.assertTrue(all(a>b>0 for a,b in zip(weights,weights[1:])))
        self.assertAlmostEqual(weights[2],.3)
        self.assertLess(weights[-1],.02)
    def test_more_full_buses_wait_and_crowding_raise_probability(self):
        base=model.change_probability(180,0,0,10)
        self.assertGreater(model.change_probability(180,2,0,10),base)
        self.assertGreater(model.change_probability(180,0,600,10),base)
        self.assertGreater(model.change_probability(180,0,0,60),base)
        self.assertLessEqual(model.change_probability(99999,50,99999,10000),1.)
    def test_prior_has_all_counts_with_mean_about_one(self):
        sample=[model.prior_budget(i) for i in range(10000)]
        self.assertEqual(set(sample),{0,1,2,3,4})
        self.assertLess(abs(sum(sample)/len(sample)-1),.04)
        self.assertGreater(sample.count(0),sample.count(2))
        self.assertGreater(sample.count(2),sample.count(3))
        self.assertGreater(sample.count(3),sample.count(4))
    def test_no_twenty_minute_trap_even_after_last_bus(self):
        bundle=fixture([('A',120,100)])
        bundle['alternatives']['0|snu']=[{'kind':'walk','name':'도보','walk':[0,600.],
                                        'walk_meters':500.,'stages':[]}]
        with tempfile.TemporaryDirectory() as folder:
            model.WORK=Path(folder);model.OUT=Path(folder);model.base.OUT=Path(folder)
            with contextlib.redirect_stdout(io.StringIO()):
                data=model.simulate(bundle,'월','peak')
            audit=json.loads(gzip.decompress((Path(folder)/'audit-peak-mon.json.gz').read_bytes()))
        self.assertAlmostEqual(data['report']['final_weight'],120)
        self.assertEqual(data['report']['unserved_trip_weight'],0)
        self.assertTrue(all(w[2]-w[1]<=1200.000001 for w in audit['waits']))
        self.assertTrue(all(not d['forced'] for d in audit['behavior_decisions']))
        self.assertTrue(all(len(s['history'])<=4 for s in audit['legs']))
    def test_low_probability_exclusion_is_not_reintroduced_on_arrival(self):
        filtered={**leg('B'),'choice_pool_locked':True,'forbidden_services':[('A',0)]}
        result=model.broaden_compatible_stage(filtered,[leg('A'),leg('B')],1.)
        self.assertIs(result,filtered)
        self.assertEqual(result['rid'],'B')
    def test_review_threshold_does_not_silently_clip_an_inert_model(self):
        bundle=fixture([('A',120,100)])
        bundle['alternatives']['0|snu']=[{'kind':'walk','name':'도보','walk':[0,600.],'walk_meters':500.,'stages':[]}]
        with tempfile.TemporaryDirectory() as folder:
            model.WORK=Path(folder);model.OUT=Path(folder);model.base.OUT=Path(folder)
            with contextlib.redirect_stdout(io.StringIO()),patch.object(model,'change_probability',return_value=0.):
                model.simulate(bundle,'월','peak')
            audit=json.loads(gzip.decompress((Path(folder)/'audit-peak-mon.json.gz').read_bytes()))
        self.assertTrue(any(w[2]-w[1]>1200 for w in audit['waits']))
    def test_boarding_policy_keeps_its_continuation_without_returning_to_used_service(self):
        bundle=fixture([('A',10,100),('B',0,300)])
        plan=bundle['prepared']['plans']['월'][0];bundle['prepared']['plans']['월']=[plan]
        first=leg('A');first['next_walk']=[0,90.]
        last=leg('B');last['next_walk']=[0,0.]
        plan[6]=[first,last]
        bundle['compatible_route_policies']={'0|snu':[{**first,'continuation_stages':[last],'policy_freeflow_seconds':210.}]}
        with tempfile.TemporaryDirectory() as folder:
            model.WORK=Path(folder);model.OUT=Path(folder);model.base.OUT=Path(folder)
            with contextlib.redirect_stdout(io.StringIO()):model.simulate(bundle,'월','peak')
            audit=json.loads(gzip.decompress((Path(folder)/'audit-peak-mon.json.gz').read_bytes()))
        rides=[l for s in audit['legs'] for l in s['legs'] if l[0]==3]
        self.assertEqual(len(rides),2)
        self.assertAlmostEqual(sum(s['weight'] for s in audit['legs']),10.)

if __name__=='__main__':unittest.main()
