"""Exact group probabilities, actual Gumbel choices and nonlinear counter stability."""
import copy,math,unittest
from preferences import choose,exponential_walk_shift,is_terminal_walk
def cfg():return {'seed':0,'choice_temperature_minutes':2.,'exponential_repeat_walk':True,'repeat_walk_growth_factor':2.,'repeat_walk_numeric_epsilon':1e-12}
def choices(p=.1):
    return [{'key':'walk','cost':0.,'prior':p,'option':{'stages':[],'kind':'walk'}},
            {'key':'stay','cost':0.,'prior':1-p,'option':None}]
def probability(options,shift):
    logs=[-c['cost']/2+math.log(c.get('prior',1.))+(shift if is_terminal_walk(c) else 0.) for c in options]
    m=max(logs);weights=[math.exp(x-m) for x in logs]
    return math.fsum(w for c,w in zip(options,weights) if is_terminal_walk(c))/math.fsum(weights)
class RepeatWalking(unittest.TestCase):
    def policy_state(self):
        from artifacts import ROOT,read
        from fixtures import fixture,leg
        from preferences import traits,Prediction
        from policy import attach_policy
        c=read(ROOT/'config.json');c.update(cfg());b=fixture([('A',1,100)],c)
        p=attach_policy(b,c,None,None,None,None,[],[],[],[],[],[],{},None,None,None,[],[])
        s={'w':1.,'history':[0,0],'plan':[1],'node':0,'traits':traits(1,c),'visit':1,'review_ordinal':0,
          'stop_entry':0.,'full_passes':0,'hazard_clock':None,'stages':[leg()],'stage':0,'queue_ticket':1,'completed_wait_seconds':0.}
        p.predict=lambda *args,**kw:Prediction(200.,walk=100.)
        p.alternative_choices=lambda *args:[{**c,'prediction':Prediction(200.,walk=100.)} for c in choices()]
        return p,s
    def test_completed_count_reaches_review_probability_rule(self):
        p,s=self.policy_state();picked=[]
        p.commit_switch=lambda state,at,reason,selected,current:(picked.append(selected) or True)
        self.assertTrue(p.maybe_switch(s,100.,'queue_recheck'))
        self.assertEqual(picked[0]['terminal_walk_rule']['completed_changes'],2)
        self.assertEqual(p.repeat_walk_stats['review',2]['decisions'],1)
    def test_completed_count_reaches_boarding_probability_rule(self):
        from fixtures import leg
        p,s=self.policy_state();p.accept_boarding(s,leg(),{'id':0,'rid':'A'},0,100.,1.)
        self.assertEqual(p.repeat_walk_stats['boarding',2]['decisions'],1)
    def test_probability_matches_complement_exponential_not_just_odds(self):
        for p in (.001,.01,.1,.3,.7):
            for n in range(6):
                shift,d=exponential_walk_shift(choices(p),cfg(),n)
                expected=1-(1-p)**(2**n);expected=min(max(p,1-1e-12),expected)
                self.assertAlmostEqual(d['target_probability'],expected,places=11)
                self.assertAlmostEqual(probability(choices(p),shift),d['target_probability'],places=12)
    def test_actual_sampled_choices_follow_target(self):
        options=choices(.1);observed=[]
        for n in range(5):
            count=sum(choose(options,uid,('same-event',),cfg(),completed_changes=n)['key']=='walk' for uid in range(12000))
            actual=count/12000;observed.append(actual);self.assertAlmostEqual(actual,1-.9**(2**n),delta=.02)
        self.assertEqual(observed,sorted(observed))
    def test_zero_changes_preserves_every_old_choice(self):
        enabled=cfg();disabled={**enabled,'exponential_repeat_walk':False}
        for uid in range(500):self.assertEqual(choose(choices(),uid,'e',enabled)['key'],choose(choices(),uid,'e',disabled)['key'])
    def test_incremental_change_penalty_cannot_reverse_increasing_walking(self):
        values=[]
        for n in range(12):
            inc=9.*n
            options=[{'key':'walk','cost':2.+inc,'option':{'stages':[]}},
              {'key':'other-stop','cost':1.+inc,'option':{'stages':[{'rid':'B'}]}},
              {'key':'board','cost':3.,'option':None}]
            _,d=exponential_walk_shift(options,cfg(),n,inc);values.append(d['target_probability'])
            if n==0:reference=d['reference_probability']
            else:self.assertAlmostEqual(reference,d['reference_probability'],places=12)
        self.assertTrue(all(a<=b for a,b in zip(values,values[1:])))
    def test_transfer_walk_not_treated_as_terminal_walk(self):
        options=[{'key':'hop','cost':0.,'option':{'stages':[{'rid':'A'}]}},{'key':'board','cost':0.,'option':None}]
        shift,d=exponential_walk_shift(options,cfg(),5)
        self.assertEqual(shift,0.);self.assertFalse(d['walk_available']);self.assertEqual(d['target_probability'],0.)
    def test_other_actions_keep_relative_probabilities(self):
        options=choices()+[{'key':'hop','cost':2.,'option':{'stages':[{'rid':'A'}]}}]
        shift,d=exponential_walk_shift(options,cfg(),3)
        self.assertGreater(shift,0.);self.assertAlmostEqual(probability(options,shift),d['target_probability'],places=12)
        self.assertFalse(is_terminal_walk(options[-1]))
    def test_exact_duplicate_does_not_multiply_walk_probability(self):
        for n in range(5):
            for uid in range(50):self.assertEqual(choose(choices(),uid,'e',cfg(),completed_changes=n)['key'],choose(choices()+[choices()[0]]*20,uid,'e',cfg(),completed_changes=n)['key'])
    def test_large_count_and_extreme_cost_stay_finite_without_count_limit(self):
        for cost in (0.,100.,20000.,-20000.):
            options=choices();options[0]['cost']=cost
            for n in (1,10,100,1000000):
                shift,d=exponential_walk_shift(options,cfg(),n)
                self.assertTrue(math.isfinite(shift));self.assertTrue(0<=d['target_probability']<=1)
    def test_infeasible_walking_remains_unavailable(self):
        options=choices();options[0]['prior']=0.
        shift,d=exponential_walk_shift(options,cfg(),99);self.assertEqual(shift,0.);self.assertEqual(d['target_probability'],0.)
    def test_inputs_and_physical_predictions_unchanged(self):
        options=choices();options[0]['physical_eta']=1000.;before=copy.deepcopy(options)
        choose(options,4,'e',cfg(),completed_changes=3)
        self.assertEqual(options,before)
    def test_invalid_counter_and_growth_rejected(self):
        for n in (-1,1.5):
            with self.assertRaises(ValueError):exponential_walk_shift(choices(),cfg(),n)
        with self.assertRaises(ValueError):exponential_walk_shift(choices(),{**cfg(),'repeat_walk_growth_factor':1.},1)
if __name__=='__main__':unittest.main()
