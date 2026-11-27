"""Reference only: map simulated ride legs to passenger-segment hourly totals.

These are explicitly provisional calendar-date / segment-entry-time conventions.
The provider's exact time attribution and segment-sequence rules must be confirmed
before applying this operator to empirical calibration. No API or engine mutation.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
import json
from pathlib import Path

@dataclass(frozen=True)
class Link:
    # Sequence must come from a verified API-to-route mapping, not array index.
    sta_sn: str
    from_id: str
    to_id: str
    seconds: float

@dataclass(frozen=True)
class RideLeg:
    date: str
    route_id: str
    boarded_departure_seconds: float
    weight: float
    # Only links actually ridden, from board inclusive to alight exclusive.
    links: tuple[Link, ...]

def observe(legs, *, timestamp_convention, date_convention):
    """The result is conditional expected passenger crossings, not mean bus load."""
    if timestamp_convention!='segment_entry' or date_convention!='calendar_date':
        raise ValueError('Only the explicitly provisional entry/calendar conventions are implemented')
    result=defaultdict(float)
    for leg in legs:
        if leg.route_id.startswith('shuttle-'):
            raise ValueError('Institutional shuttle legs are outside the city-bus API observation scope')
        if not isfinite(leg.weight) or leg.weight<0 or not isfinite(leg.boarded_departure_seconds):
            raise ValueError('Invalid weight or departure time')
        instant=datetime.strptime(leg.date,'%Y%m%d')+timedelta(seconds=leg.boarded_departure_seconds)
        previous=None
        for link in leg.links:
            if not (link.sta_sn and link.from_id and link.to_id) or not isfinite(link.seconds) or link.seconds<0:
                raise ValueError('Unmapped or invalid traversed link')
            if previous is not None and previous.to_id!=link.from_id:
                raise ValueError('Discontinuous ride-leg links')
            key=(instant.strftime('%Y%m%d'),leg.route_id,link.sta_sn,link.from_id,link.to_id,instant.hour)
            result[key]+=leg.weight
            instant+=timedelta(seconds=link.seconds)
            previous=link
    return dict(result)

def self_check():
    # A rider traversing two links contributes once to each, not once per second.
    leg=RideLeg('20261026','city-test',15*3600+59*60,10,
        (Link('7','A','B',120),Link('8','B','C',60)))
    got=observe([leg],timestamp_convention='segment_entry',date_convention='calendar_date')
    assert got[('20261026','city-test','7','A','B',15)]==10
    assert got[('20261026','city-test','8','B','C',16)]==10
    assert sum(got.values())==leg.weight*len(leg.links)==20
    # One physical ID may occur twice on a loop; sequence keeps those passages distinct.
    loop=RideLeg('20261026','city-test',23*3600+59*60,3,
        (Link('2','A','B',60),Link('3','B','A',60),Link('9','A','B',30)))
    midnight=observe([loop],timestamp_convention='segment_entry',date_convention='calendar_date')
    assert midnight[('20261026','city-test','2','A','B',23)]==3
    assert midnight[('20261027','city-test','9','A','B',0)]==3
    assert sum(midnight.values())==loop.weight*len(loop.links)==9
    # Missing observations remain missing in the join; no zero filling is done here.
    # No real empirical data is consumed in these mathematical examples.
    return {'status':'PASS_REFERENCE_EXAMPLES','checks':['two-link passenger-segment conservation',
        'hour-boundary crossing','sequence distinguishes repeated endpoints','explicit calendar midnight handling'],
        'provider_semantics_confirmed':False,'actual_engine_integration':False,
        'empirical_calibration_performed':False,'network_requests':0}

if __name__=='__main__':
    checked=self_check()
    Path(__file__).with_name('operator_reference_check.json').write_text(json.dumps(checked,indent=2),encoding='utf-8')
    print(json.dumps(checked))
