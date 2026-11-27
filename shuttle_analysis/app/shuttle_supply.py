"""Vehicle supply fixed at the original terminal dispatch, in service-day seconds.

Capacity periods start inclusively and last until the next period. Batch windows
are [start, end); each vehicle retains its own capacity and onboard passengers.
Aliases consume their primary profile rather than creating additional vehicles.
"""
import copy
import math

SUPPLY_KEYS=('capacity','capacity_periods','dispatch_batches')
CONTRACT='original_terminal_dispatch_capacity_and_batches_v1'


def settings(route):
    """Copy source supply without inventing periods or carrying stale overrides."""
    return {key:copy.deepcopy(route[key]) for key in SUPPLY_KEYS if key in route}


def copy_settings(target,source):
    for key in SUPPLY_KEYS:target.pop(key,None)
    target.update(settings(source))


def capacity_at(route,terminal_second):
    capacity=route['capacity']
    for period in route.get('capacity_periods',[]):
        if terminal_second<period['start_second']:break
        capacity=period['capacity']
    return capacity


def vehicles(route,terminal_seconds):
    """Expand coincident departures; never flatten a pair into shorter headways."""
    for second in terminal_seconds:
        count=next((row['vehicles'] for row in route.get('dispatch_batches',[])
                    if row['start_second']<=second<row['end_second']),1)
        for member in range(count):
            yield {'terminal_dispatch_second':second,'capacity':capacity_at(route,second),
                   'batch_member':member,'batch_vehicles':count}


def _integer(value,low,high,label):
    if type(value) is not int or not low<=value<=high:raise ValueError(label)


def validate(route):
    capacity=route.get('capacity')
    if isinstance(capacity,bool) or not isinstance(capacity,(int,float)) or not math.isfinite(capacity) or not 1<=capacity<=200:
        raise ValueError('vehicle_capacity')
    if route.get('profile_route_id') and any(key in route for key in SUPPLY_KEYS[1:]):
        raise ValueError('alias_supply_override')
    for key in SUPPLY_KEYS[1:]:
        if key in route and (not isinstance(route[key],list) or not 1<=len(route[key])<=16):
            raise ValueError('supply_period_count')
    previous=-1
    for row in route.get('capacity_periods',[]):
        if not isinstance(row,dict) or set(row)!={'start_second','capacity'}:raise ValueError('capacity_period_fields')
        _integer(row['start_second'],0,172800,'capacity_period_clock')
        _integer(row['capacity'],1,200,'vehicle_capacity')
        if row['start_second']<=previous:raise ValueError('capacity_period_order')
        previous=row['start_second']
    previous=0
    for row in route.get('dispatch_batches',[]):
        if not isinstance(row,dict) or set(row)!={'start_second','end_second','vehicles'}:raise ValueError('dispatch_batch_fields')
        _integer(row['start_second'],0,172799,'dispatch_batch_clock')
        _integer(row['end_second'],row['start_second']+1,172800,'dispatch_batch_clock')
        _integer(row['vehicles'],1,4,'dispatch_batch_size')
        if row['start_second']<previous:raise ValueError('dispatch_batch_overlap')
        previous=row['end_second']
