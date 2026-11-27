"""Continuous causal reconsideration: ordinary repeat aversion and stress are separate."""
from dataclasses import dataclass
import math
from preferences import uniform

def integrated(a,b,changes,full,response,config):
    dt=b-a;scale=config['review_age_scale_seconds']
    ordinary=config['review_base_rate_per_second']*config['repeat_multiplier']**changes
    stress=config.get('review_full_stress_rate_per_second',0.)*(-math.expm1(-config.get('review_full_saturation',.4)*full))
    age_rate=config.get('review_age_stress_rate_per_second',0.)
    # Polynomial difference factored to retain precision for nearby events.
    horizon=config.get('review_age_stress_saturation_seconds',1800.)
    if b<=horizon:
        age_integral=dt*(b*b*b+b*b*a+b*a*a+a*a*a)/(4*scale**3)
    elif a>=horizon:age_integral=dt*(horizon/scale)**3
    else:
        width=horizon-a
        age_integral=width*(horizon**3+horizon*horizon*a+horizon*a*a+a**3)/(4*scale**3)+(b-horizon)*(horizon/scale)**3
    return response*(ordinary*(dt+dt*(b+a)/(2*scale))+stress*dt+age_rate*age_integral)

def delay(age,remaining,changes,full,response,config):
    if remaining<=0:return 0.
    if config.get('review_age_stress_rate_per_second',0.)<=0 and config['review_base_rate_per_second']<=0 and config.get('review_full_stress_rate_per_second',0.)<=0:return math.inf
    low=0.;high=60.
    while integrated(age,age+high,changes,full,response,config)<remaining:
        high*=2
        if high>1e12:return math.inf
    for _ in range(36):
        mid=(low+high)/2
        if integrated(age,age+mid,changes,full,response,config)<remaining:low=mid
        else:high=mid
    return (low+high)/2

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
    def due(self,config):return self.last+delay(self.last-self.stop_entry,self.remaining,self.count,self.full,self.response,config)

def interval_probability(a,b,count,full,response,config):
    return -math.expm1(-integrated(a,b,count,full,response,config))
