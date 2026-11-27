"""Adult-card bus chain scenario. No unknown prior fare is labelled observed."""
from dataclasses import dataclass,replace
import math

@dataclass(frozen=True)
class FareLedger:
    base_paid:float=0.
    distance_paid:float=0.
    meters:float=0.
    boardings:int=0
    last_alight:float|None=None
    last_route:str|None=None

def transfer_window(at):return 3600 if at%86400>=21*3600 or at%86400<7*3600 else 1800

def board(ledger,rid,at,base_fare,ride_meters):
    if base_fare==0:return 0.,ledger
    eligible=(ledger.last_alight is not None and 0<=at-ledger.last_alight<=transfer_window(ledger.last_alight)
              and ledger.boardings<5 and rid!=ledger.last_route)
    if not eligible:
        return float(base_fare),FareLedger(float(base_fare),0.,ride_meters,1,None,rid)
    meters=ledger.meters+ride_meters
    surcharge=100*max(0,math.ceil((meters-10000)/5000-1e-12))
    charge=max(0.,base_fare-ledger.base_paid)+max(0.,surcharge-ledger.distance_paid)
    return charge,FareLedger(max(base_fare,ledger.base_paid),surcharge,meters,ledger.boardings+1,None,rid)

def alight(ledger,rid,at,base_fare):
    return replace(ledger,last_alight=at,last_route=rid) if base_fare else ledger
