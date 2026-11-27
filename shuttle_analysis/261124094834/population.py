"""Daily departure-budget check in weighted people, before routing."""
import math

DAILY_TRIP_LIMIT = 30_000

def cap_daily_departures(bundle,day,profile,converted):
    plans=bundle['prepared']['plans'][day]
    proposed=math.fsum(p[3] for p in plans)
    if not math.isfinite(proposed) or proposed<0 or not math.isclose(proposed,profile['total_trip_mass'],abs_tol=1e-7):
        raise ValueError('Inconsistent pre-routing homebound total')
    # Keep sub-person roundoff from crossing an integer ceiling on a binding day.
    binding=proposed>DAILY_TRIP_LIMIT
    factor=(DAILY_TRIP_LIMIT-1e-7)/proposed if binding else 1.
    if binding:
        for i,p in enumerate(plans):
            weight=p[3]*factor
            plans[i]=[*p[:3],weight,*p[4:]]
            if p[0] in converted:
                _,path,seconds=converted[p[0]]
                converted[p[0]]=(weight,path,seconds)
        for row in profile['rate_by_class_end']:
            row['probability']*=factor
            row['immediate_trip_mass']*=factor
            row['other_activity_mass']=row['enrollment']-row['immediate_trip_mass']
        profile['hourly_clock_rates']={h:v*factor for h,v in profile['hourly_clock_rates'].items()}
    admitted=math.fsum(p[3] for p in plans)
    if admitted>DAILY_TRIP_LIMIT or not math.isclose(admitted,proposed*factor,abs_tol=1e-7):
        raise ValueError('Daily homebound trip limit exceeded')
    bundle['prepared']['expected'][day]=admitted
    profile['total_trip_mass']=admitted
    profile['daily_population']=dict(limit=DAILY_TRIP_LIMIT,proposed=proposed,admitted=admitted,
        applied_factor=factor,binding=binding,remaining=DAILY_TRIP_LIMIT-admitted)
    return profile['daily_population']

def check_result(result):
    ledger=result['invariants']
    entered,finished=ledger['input_weight'],ledger['final_weight']
    if not (0<=entered<=DAILY_TRIP_LIMIT+1e-7 and math.isclose(finished,entered,abs_tol=1e-6)):
        raise ValueError('Stored daily demand or conservation check failed')
    return dict(limit=DAILY_TRIP_LIMIT, entered=entered, exit_accounted=finished)
