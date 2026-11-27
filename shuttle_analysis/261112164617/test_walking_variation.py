"""Cross-layer walking clock checks: access, boarding, egress and prediction."""
import contextlib,copy,gzip,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from artifacts import ROOT,read,START
from fixtures import fixture,leg
from fares import FareLedger
from preferences import traits
from policy import attach_policy
import engine
class WalkingVariation(unittest.TestCase):
    def test_each_walking_leg_scaled_once_and_bus_clock_kept(self):
        cfg=read(ROOT/'config.json');cfg.update(origin_choice=False,physics='path_local_4p8',behavior='sequential',
          boarding_choice=True,arrival_review_probability=0,review_base_rate_per_second=0,review_age_stress_rate_per_second=0,review_full_stress_rate_per_second=0)
        b=fixture([('A',1,180)],cfg);p=b['prepared']['plans']['월'][0]
        factor=1.2;p[5][1]=100*factor;p[6]=engine.scaled_stages([leg()],factor);b['walk_scales'][str(p[0])]=factor
        b['supply']['regular']['A']=[START+180]
        with tempfile.TemporaryDirectory() as folder,contextlib.redirect_stdout(io.StringIO()),patch.object(engine,'WORK',Path(folder)):
            engine.simulate(b,'월','regular',export=True)
            audit=json.loads(gzip.decompress((Path(folder)/'audit-regular-mon.json.gz').read_bytes()))
        trip=audit['legs'][0];walks=[x for x in trip['legs'] if x[0]==0];rides=[x for x in trip['legs'] if x[0]==3]
        self.assertAlmostEqual(walks[0][2]-walks[0][1],120)
        self.assertAlmostEqual(walks[-1][2]-walks[-1][1],6)
        self.assertEqual(rides[0][1],START+180);self.assertEqual(trip['finish_time'],START+246)
        self.assertAlmostEqual(trip['completed_wait_seconds'],60.)
    def test_scaled_continuation_predictions_do_not_scale_twice(self):
        cfg=read(ROOT/'config.json');b=fixture([('A',1,100)],cfg)
        raw=leg();scaled=engine.scaled_stages([raw],1.2)
        fleet=[{'id':0,'rid':'A','cap':44,'last_stop':-1,'onboard':[],'times':[100.,160.]}]
        policy=attach_policy(b,cfg,lambda s:0,lambda s:s['stages'][s['stage']],None,lambda *a:[],[[(100.,0,0)]],fleet,[],[],[],[],b['prepared']['common']['route_info'],None,None,None,[],[])
        state={'w':1.,'factor':1.2,'ready_time':20.,'stop_entry':0.,'full_passes':0,'history':[],'fare_ledger':FareLedger(),'traits':traits(1,cfg),'stages':scaled,'stage':0}
        p=policy.predict(scaled,0.,state);self.assertEqual(p.eta,166.)
        future=policy.predict([raw],0.,state,access=12.,factor=1.2)
        self.assertEqual(future.eta,166.);self.assertEqual(future.walk,18.)
    def test_inherited_variation_exists_without_new_random_draws(self):
        b=read(ROOT/'frozen/prepared_capacity44_pair.json.gz');values=list(b['walk_scales'].values())
        self.assertLess(min(values),1.);self.assertGreater(max(values),1.)
        self.assertEqual(values,list(read(ROOT/'frozen/prepared_capacity44_pair.json.gz')['walk_scales'].values()))
if __name__=='__main__':unittest.main()
