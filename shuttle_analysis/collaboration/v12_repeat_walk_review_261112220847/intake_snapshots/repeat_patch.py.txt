"""A bounded exponential increase in conditional terminal-walk probability."""
from pathlib import Path
def replace(p,old,new):
    s=p.read_text(encoding='utf8');assert s.count(old)==1,(p,old[:70],s.count(old));p.write_text(s.replace(old,new),encoding='utf8')

ADDITION='''def is_terminal_walk(candidate):
    option=candidate.get('option')
    return option is not None and 'stages' in option and not option['stages']


def logsum(values):
    maximum=max(values)
    return maximum+math.log(math.fsum(math.exp(v-maximum) for v in values))


def softplus(value):return max(0.,value)+math.log1p(math.exp(-abs(value)))


def logistic(value):
    if value>=0:return 1./(1.+math.exp(-value))
    e=math.exp(value);return e/(1.+e)


def exponential_walk_shift(candidates,config,completed_changes=0,reference_change_increment=0.):
    """p_n=1-(1-p_ref)**g**n, with stable log-space group reweighting.

The reference removes only the existing count-dependent incremental change fee
from changing actions. Distances, current wait experience, costs and priors stay.
No physical ETA, trajectory, queue or capacity is modified here.
"""
    n=completed_changes
    if not isinstance(n,int) or n<0:raise ValueError('completed_changes must be a nonnegative integer')
    growth=config.get('repeat_walk_growth_factor',2.)
    if not math.isfinite(growth) or growth<=1:raise ValueError('walk growth factor must exceed1')
    if not math.isfinite(reference_change_increment) or reference_change_increment<0:raise ValueError('invalid reference change increment')
    temperature=config['choice_temperature_minutes'];walk=[];other=[];refwalk=[];refother=[]
    for c in candidates:
        prior=c.get('prior',1.)
        if prior<=0 or not math.isfinite(c['cost']):continue
        value=-c['cost']/temperature+math.log(prior)
        reference=value+(reference_change_increment/temperature if c.get('option') is not None else 0.)
        if is_terminal_walk(c):walk.append(value);refwalk.append(reference)
        else:other.append(value);refother.append(reference)
    available=bool(walk)
    if not walk or not other:
        p=1. if walk else 0.
        return 0.,{'completed_changes':n,'growth_factor':growth,'walk_available':available,
          'unboosted_probability':p,'reference_probability':p,'target_probability':p,'logit_shift':0.,'numeric_saturation':False}
    actual=logsum(walk)-logsum(other);reference=logsum(refwalk)-logsum(refother)
    saturated=False
    if n==0:target=actual
    else:
        # log(-log(1-p_ref)); approximation below-36 is at machine precision.
        log_hazard0=reference if reference < -36. else math.log(softplus(reference))
        log_hazard=log_hazard0+n*math.log(growth)
        epsilon=config.get('repeat_walk_numeric_epsilon',1e-12)
        if not 0<epsilon<.5:raise ValueError('invalid numeric probability epsilon')
        ceiling=max(reference,math.log1p(-epsilon)-math.log(epsilon))
        log_hazard_ceiling=math.log(softplus(ceiling))
        if log_hazard>=log_hazard_ceiling:target=ceiling;saturated=True
        elif log_hazard < -36.:target=log_hazard
        else:
            hazard=math.exp(log_hazard)
            target=math.log(-math.expm1(-hazard))+hazard
    shift=0. if n==0 else max(0.,target-actual)
    effective=actual+shift
    return shift,{'completed_changes':n,'growth_factor':growth,'walk_available':available,
      'unboosted_probability':logistic(actual),'reference_probability':logistic(reference),
      'reference_log_odds':reference,'target_probability':logistic(effective),
      'target_log_odds':effective,'logit_shift':shift,'numeric_saturation':saturated,
      'interpretation':'conditional on this feasible choice set and iid event errors; not population frequency or review hazard'}


'''

RECORDER='''        def record_repeat_walk_choice(self,state,selected,phase):
            if selected is None:return
            d=selected.get('terminal_walk_rule')
            if d is None:return
            key=(phase,len(state['history']))
            row=self.repeat_walk_stats.setdefault(key,{'phase':phase,'completed_changes':key[1],'decisions':0,
              'decision_weight':0.,'walk_available_weight':0.,'unboosted_probability_weighted_sum':0.,
              'reference_probability_weighted_sum':0.,'target_probability_weighted_sum':0.,'terminal_walk_selected_weight':0.})
            weight=state['w'];row['decisions']+=1;row['decision_weight']+=weight
            if d['walk_available']:row['walk_available_weight']+=weight
            for name in ('unboosted_probability','reference_probability','target_probability'):
                row[name+'_weighted_sum']+=weight*d[name]
            if is_terminal_walk(selected):row['terminal_walk_selected_weight']+=weight

'''

def apply(work):
    p=work/'preferences.py'
    replace(p,'def choose(candidates,identity,event_key,config):',ADDITION+'def choose(candidates,identity,event_key,config,completed_changes=0,reference_change_increment=0.):')
    replace(p,"    temperature=config['choice_temperature_minutes'];best=None;best_value=-math.inf",
      """    temperature=config['choice_temperature_minutes'];best=None;best_value=-math.inf
    shift=0.;diagnostic=None
    if config.get('exponential_repeat_walk'):
        shift,diagnostic=exponential_walk_shift(list(unique.values()),config,completed_changes,reference_change_increment)""")
    replace(p,"        value=-candidate['cost']/temperature+math.log(prior)+noise",
      "        value=-candidate['cost']/temperature+math.log(prior)+noise+(shift if is_terminal_walk(candidate) else 0.)")
    replace(p,'    return best\n',"    return {**best,'terminal_walk_rule':diagnostic} if best is not None and diagnostic is not None else best\n")
    p=work/'policy.py'
    replace(p,'from preferences import Prediction,traits,cost,choose,uniform,walking_weight',
      'from preferences import Prediction,traits,cost,choose,uniform,walking_weight,is_terminal_walk')
    replace(p,'self.counts=Counter();self.boarding_choices=[];self.initial_choices=0;self.review_diagnostics=[]',
      'self.counts=Counter();self.boarding_choices=[];self.initial_choices=0;self.review_diagnostics=[];self.repeat_walk_stats={}')
    replace(p,'        def complete_same_stop(self,state,stage,node):',RECORDER+'        def complete_same_stop(self,state,stage,node):')
    replace(p,"                if lower>best_so_far+12*config['choice_temperature_minutes']:",
      "                if lower>best_so_far+12*config['choice_temperature_minutes'] and not (config.get('exponential_repeat_walk') and count>0 and not chain):")
    replace(p,"            selected=choose(candidates,identity,('reroute',state['visit'],state['review_ordinal']),config)",
      """            selected=choose(candidates,identity,('reroute',state['visit'],state['review_ordinal']),config,
                count,.5*state['traits'].change*count)
            self.record_repeat_walk_choice(state,selected,'review')""")
    replace(p,"            selected=choose(options,state['plan'][0],('board',state['visit'],vehicle['id'],k),config)\n            # No forecastable suffix:",
      """            selected=choose(options,state['plan'][0],('board',state['visit'],vehicle['id'],k),config,
                len(state['history']),.5*state['traits'].change*len(state['history']))
            self.record_repeat_walk_choice(state,selected,'boarding')
            # No forecastable suffix:""")
    replace(p,"                'generalized_cost_minutes':selected['cost'],'physical_prediction':pred.components(),",
      "                'generalized_cost_minutes':selected['cost'],'physical_prediction':pred.components(),'terminal_walk_rule':selected.get('terminal_walk_rule'),")
    replace(p,"                'selected_cost':selected['cost'],'joint_action_count':len(options),'selected_key':selected['key'],",
      "                'selected_cost':selected['cost'],'joint_action_count':len(options),'selected_key':selected['key'],'terminal_walk_rule':selected.get('terminal_walk_rule'),")
    replace(p,"                    'committed_approach_forecast':committed.report() if committed is not None else None,",
      """                    'repeat_walk_choice_statistics':[self.repeat_walk_stats[k] for k in sorted(self.repeat_walk_stats)],
                    'repeat_walk_probability_rule':'p_n=1-(1-p_reference)^growth^n; terminal walking only; conditional choice probability, review timing unchanged',
                    'committed_approach_forecast':committed.report() if committed is not None else None,""")
