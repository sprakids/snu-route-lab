"""Two separate 44-seat vehicles and sequential boarding, isolated micro model.

This is an explicit hypothesis interface, not a fitted whole-network dwell model.
"""
from dataclasses import dataclass
import heapq

@dataclass(frozen=True)
class Vehicle:
    id:str
    arrival_at:float
    capacity:int
    already_onboard:int
    door_open_delay:float
    seconds_per_boarder:float
    departure_clearance:float

def simulate_batch(vehicles,people,allocation='next_available'):
    """People are (id, stop_arrival_at, ready_at), ordered physical FIFO.

Reports service completion as boarding_at; all wait stages stay inspectable.
The next-available-door and fill-first allocation rules are alternative scenarios.
"""
    fleet={v.id:v for v in vehicles};free={v.id:v.capacity-v.already_onboard for v in vehicles}
    for v in vehicles:
        assert 0<=v.already_onboard<=v.capacity and v.seconds_per_boarder>0
    clocks={v.id:v.arrival_at+v.door_open_delay for v in vehicles};rows=[]
    order={v.id:i for i,v in enumerate(vehicles)}
    for uid,arrival,ready in people:
        assert ready>=arrival
        choices=[v for v in vehicles if free[v.id]>0]
        if not choices:
            rows.append({'id':uid,'stop_arrival_at':arrival,'ready_at':ready,'boarding_at':None,'vehicle':None,'censored':True});continue
        if allocation=='fill_first':selected=min(choices,key=lambda v:order[v.id])
        elif allocation=='next_available':selected=min(choices,key=lambda v:(max(clocks[v.id],ready),order[v.id]))
        else:raise ValueError('Unknown allocation scenario')
        start=max(clocks[selected.id],ready);end=start+selected.seconds_per_boarder
        rows.append({'id':uid,'stop_arrival_at':arrival,'ready_at':ready,'service_start_at':start,
                     'boarding_at':end,'leave_at':end,'vehicle':selected.id,'censored':False})
        free[selected.id]-=1;clocks[selected.id]=end
    departures={v.id:max(v.arrival_at+v.door_open_delay,clocks[v.id])+v.departure_clearance for v in vehicles}
    for row in rows:
        if row['vehicle']:
            row['departure_at']=departures[row['vehicle']];row['pure_queue_wait_seconds']=row['boarding_at']-row['stop_arrival_at']
            row['post_boarding_seconds']=row['departure_at']-row['boarding_at']
            row['join_to_departure_seconds']=row['departure_at']-row['stop_arrival_at']
    for v in vehicles:
        assert v.already_onboard+sum(r['vehicle']==v.id for r in rows)<=v.capacity
    return {'passengers':rows,'departures':departures,'vehicles':len(vehicles),
            'boarding_is_instantaneous':False,'no_aggregate_88_seat_vehicle':True,'allocation':allocation}
