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

def choose(candidates,identity,event_key,config):
    """Exact duplicate strategies never gain probability by being listed twice."""
    unique={}
    for candidate in candidates:
        key=candidate['key']
        if key not in unique or candidate['cost']<unique[key]['cost']:unique[key]=candidate
    temperature=config['choice_temperature_minutes'];best=None;best_value=-math.inf
    for key,candidate in sorted(unique.items(),key=lambda kv:str(kv[0])):
        prior=candidate.get('prior',1.)
        if prior<=0 or not math.isfinite(candidate['cost']):continue
        noise=-math.log(-math.log(max(1e-15,uniform(config['seed'],identity,event_key,key))))
        value=-candidate['cost']/temperature+math.log(prior)+noise
        if value>best_value:best_value=value;best=candidate
    return best
