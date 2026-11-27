"""Persistent tastes and minute-equivalent costs, never physical ETA."""
from dataclasses import dataclass,asdict
import hashlib,math

def uniform(seed,identity,*parts):
    raw='|'.join(map(str,('prototype-v1',seed,identity,*parts))).encode()
    return (int.from_bytes(hashlib.sha256(raw).digest()[:8],'big')+.5)/2**64

def lognormal(seed,identity,label,median,sigma):
    a=max(1e-15,uniform(seed,identity,label,'a'));b=uniform(seed,identity,label,'b')
    z=math.sqrt(-2*math.log(a))*math.cos(2*math.pi*b)
    return median*math.exp(sigma*z)

@dataclass(frozen=True)
class Traits:
    walk:float
    wait:float
    vot:float
    transfer:float
    change:float
    crowd:float
    response:float
    fatigue:float
    def record(self):return asdict(self)

def traits(identity,config):
    seed=config['seed'];sigma=config['trait_log_sigma']
    draw=lambda key,median:lognormal(seed,identity,key,median,sigma)
    return Traits(draw('walk',config['walk_coefficient_median']),draw('wait',config['wait_coefficient_median']),
                  draw('vot',config['value_of_time_won_hour']),draw('transfer',config['transfer_penalty_minutes']),
                  draw('change',config['change_penalty_minutes']),draw('crowd',config['crowd_penalty_coefficient']),draw('response',1.),draw('fatigue',config['fatigue_coefficient']))

@dataclass(frozen=True)
class Prediction:
    eta:float
    walk:float=0.
    wait:float=0.
    ride:float=0.
    prep:float=0.
    transfers:int=0
    fare:float=0.
    crowd_exposure:float=0.
    fatigue:float=0.
    first_wait:float=0.
    wait_squared:float=0.
    wait_cubed:float=0.
    empirical_context:tuple=()
    boarding_load_projections:tuple=()
    def components(self):return asdict(self)

def cost(pred,taste,changes=0,changing=False,fare_enabled=False):
    """Inputs in seconds/won, result in equivalent minutes; no sunk waiting."""
    return (pred.ride+taste.walk*pred.walk+taste.wait*(pred.wait+pred.prep))/60 + taste.transfer*pred.transfers + \
           (60*pred.fare/taste.vot if fare_enabled else 0.) + \
           (taste.change*(1+.5*changes) if changing else 0.) + taste.crowd*pred.crowd_exposure/60 + taste.fatigue*pred.fatigue/60

def walking_weight(meters):
    if meters<=500:return 1.
    if meters<=1000:return 1.-.7*(meters-500)/500
    return .3*math.exp(-(meters-1000)/150)

def is_terminal_walk(candidate):
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


def choose(candidates,identity,event_key,config,completed_changes=0,reference_change_increment=0.):
    """Exact duplicate strategies never gain probability by being listed twice."""
    unique={}
    for candidate in candidates:
        key=candidate['key']
        if key not in unique or candidate['cost']<unique[key]['cost']:unique[key]=candidate
    temperature=config['choice_temperature_minutes'];best=None;best_value=-math.inf
    shift=0.;diagnostic=None
    if config.get('exponential_repeat_walk'):
        shift,diagnostic=exponential_walk_shift(list(unique.values()),config,completed_changes,reference_change_increment)
    for key,candidate in sorted(unique.items(),key=lambda kv:str(kv[0])):
        prior=candidate.get('prior',1.)
        if prior<=0 or not math.isfinite(candidate['cost']):continue
        noise_key=('trip-strategy',candidate.get('taste_key',key)) if config.get('persistent_strategy_utility') else (event_key,key)
        noise=-math.log(-math.log(max(1e-15,uniform(config['seed'],identity,*noise_key))))
        value=-candidate['cost']/temperature+math.log(prior)+noise+(shift if is_terminal_walk(candidate) else 0.)
        if value>best_value:best_value=value;best=candidate
    return {**best,'terminal_walk_rule':diagnostic} if best is not None and diagnostic is not None else best
