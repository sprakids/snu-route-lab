"""Physical small-network regressions for action-set omissions and FIFO index updates."""
import contextlib,io,unittest
from artifacts import ROOT,read,START
from fixtures import fixture,leg
import engine
class JointChoice(unittest.TestCase):
    def config(self,joint=True):
        c=read(ROOT/'config.json');c.update(joint_board_wait_walk_choice=joint,origin_choice=False,
          behavior='sequential',boarding_choice=True,physics='v9_frozen',review_base_rate_per_second=0.,
          review_age_stress_rate_per_second=0.,review_full_stress_rate_per_second=0.,arrival_review_probability=0.)
        return c
    def network(self,joint=True,pair=False):
        b=fixture([('A',1.,100),('B',.01,100)] if pair else [('A',1.,100)],self.config(joint))
        b['prepared']['common']['route_info']['A']['offsets']=[0.,3600.]
        for rid in b['supply']['regular']:b['supply']['regular'][rid]=[START+100]
        b['alternatives']['0|snu']=[{'walk':[0,600.],'walk_meters':800.,'stages':[],'kind':'walk','name':'direct'}]
        if pair:b['compatible_single_stage_pools']={'0|snu':[leg('A'),leg('B')]}
        return b
    def simulate(self,b):
        with contextlib.redirect_stdout(io.StringIO()):return engine.simulate(b,'월','regular',export=False)
    def test_last_service_compares_walking_instead_of_forcing_boarding(self):
        new=self.simulate(self.network());old=self.simulate(self.network(False))
        self.assertEqual(new['report']['unserved_trip_weight'],0.)
        self.assertGreater(new['report']['realized_mean_route_changes'],0.)
        self.assertEqual(old['report']['realized_mean_route_changes'],0.)
        self.assertEqual(new['policy_report']['opportunity_counts']['joint_boarding_walk'],1)
        self.assertLess(new['report']['mean_finished_trip_minutes'],old['report']['mean_finished_trip_minutes'])
    def test_same_time_better_bus_is_retained_as_wait_action(self):
        result=self.simulate(self.network(pair=True))
        self.assertEqual(result['report']['realized_mean_route_changes'],0.)
        self.assertEqual(result['report']['unserved_trip_weight'],0.)
        self.assertGreater(result['policy_report']['opportunity_counts'].get('joint_boarding_wait',0),0)
    def test_many_walk_removals_refresh_live_fifo_prefix(self):
        b=self.network();plans=b['prepared']['plans']['월'];prototype=plans[0]
        for i in range(2,12):
            plans.append([i,*prototype[1:3],1.,prototype[4],[*prototype[5]],prototype[6]])
            b['walk_scales'][str(i)]=1.;b['parent_ids'][str(i)]=i;b['source_parent_mass'][str(i)]=1.;b['destination_keys'][str(i)]='snu'
        result=self.simulate(b)
        self.assertEqual(result['report']['unserved_trip_weight'],0.)
        self.assertGreater(result['policy_report']['opportunity_counts'].get('joint_boarding_walk',0),5)
if __name__=='__main__':unittest.main()
