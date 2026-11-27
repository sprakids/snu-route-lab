"""Event-time review opportunities; no Bernoulli draw per API/animation tick."""
from dataclasses import dataclass
import math
from preferences import uniform

def integrated(a,b,changes,full,response,config):
    rate=config['review_base_rate_per_second']*config['repeat_multiplier']**changes*response*(1+config['review_full_bus_multiplier']*full)
    return rate*((b-a)+(b*b-a*a)/(2*config['review_age_scale_seconds']))

def delay(age,remaining,changes,full,response,config):
    rate=config['review_base_rate_per_second']*config['repeat_multiplier']**changes*response*(1+config['review_full_bus_multiplier']*full)
    if rate<=0:return math.inf
    scale=config['review_age_scale_seconds'];b=1+age/scale;q=remaining/rate
    # Rationalized quadratic solution: no cancellation at small intervals.
    return 2*q/(b+math.sqrt(b*b+2*q/scale))

@dataclass
class ReviewClock:
    last:float
    stop_entry:float
    remaining:float
    count:int
    full:int
    ordinal:int
    identity:object
    response:float

    @classmethod
    def start(cls,at,stop_entry,count,full,identity,response,config,ordinal=0):
        e=-math.log(max(1e-15,uniform(config['seed'],identity,'hazard',stop_entry,ordinal)))
        return cls(at,stop_entry,e,count,full,ordinal,identity,response)
    def update(self,at,count,full,config):
        assert at>=self.last-1e-7
        self.remaining=max(0.,self.remaining-integrated(self.last-self.stop_entry,at-self.stop_entry,self.count,self.full,self.response,config))
        self.last=at;self.count=count;self.full=full
    def due(self,config):
        return self.last+delay(self.last-self.stop_entry,self.remaining,self.count,self.full,self.response,config)

def interval_probability(a,b,count,full,response,config):
    return -math.expm1(-integrated(a,b,count,full,response,config))
