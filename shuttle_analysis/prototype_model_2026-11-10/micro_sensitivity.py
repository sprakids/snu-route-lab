"""Finite, declared two-door process sensitivity; no best-point fitting."""
from pathlib import Path
from itertools import product
import csv,hashlib,json
from dwell import Vehicle,simulate_batch

ROOT=Path(__file__).resolve().parent
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')

def main():
    lock=ROOT/'micro_experiment_lock.json'
    protocol={'status':'PREREGISTERED_BEFORE_MICRO_EXECUTION','event':'20261110-1523-admin-snu-queue-wait-01',
        'arrival_seconds_after_join':[30,60,120],'door_delay_seconds':[0,30,60],
        'seconds_per_boarder':[1,2,4,6],'clearance_after_last_boarder_seconds':[0,15,30],
        'already_onboard_per_vehicle':[0,10,20],'allocation':['fill_first','next_available'],
        'observer_ready_delay_seconds':[0,20],'outside_people_including_observer':67,'capacity_per_vehicle':44,'vehicles':2,
        'constant_scenario_queue':'66 ahead present and ready when observer joins; no further arrivals, no alighting',
        'event_uncertainty':'join minute unknown second, actual vehicle arrival/door opening/residual seats not measured',
        'not_estimated_from_event':True,'post_boarding30_is_not_clearance_parameter':True,
        'amends_original_micro_grid':'Adds separately named ready/clearance/onboard hypotheses before execution; no coefficient selection or ranking'}
    if lock.exists():assert json.loads(lock.read_text(encoding='utf8'))==protocol
    else:save(lock,protocol)
    output=ROOT/'micro_sensitivity.csv';assert not output.exists(),'Preserve existing micro outputs'
    rows=[]
    for arrival,door,service,clearance,onboard,allocation,ready in product(*[protocol[k] for k in (
        'arrival_seconds_after_join','door_delay_seconds','seconds_per_boarder','clearance_after_last_boarder_seconds',
        'already_onboard_per_vehicle','allocation','observer_ready_delay_seconds')]):
        vehicles=[Vehicle(f'bus-{i+1}',arrival,44,onboard,door,service,clearance) for i in range(2)]
        people=[(i,0.,ready if i==66 else 0.) for i in range(67)]
        result=simulate_batch(vehicles,people,allocation);observer=result['passengers'][-1]
        rows.append({'arrival_after_join_seconds':arrival,'door_delay_seconds':door,'seconds_per_boarder':service,
            'clearance_seconds':clearance,'onboard_per_vehicle':onboard,'allocation':allocation,'observer_ready_seconds':ready,
            'observer_vehicle':observer['vehicle'],'observer_boarded_same_pair':not observer['censored'],
            'join_to_boarding_seconds':observer.get('boarding_at'),'post_boarding_seconds':observer.get('post_boarding_seconds'),
            'join_to_departure_seconds':observer.get('join_to_departure_seconds'),
            'boarded_all_people':sum(not p['censored'] for p in result['passengers']),
            'two_separate_44_vehicles':True})
    with output.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,list(rows[0]));writer.writeheader();writer.writerows(rows)
    served=[r for r in rows if r['observer_boarded_same_pair']]
    summary={'status':'COMPUTED_SENSITIVITY_NOT_VALIDATION','hypotheses':len(rows),'observer_served_hypotheses':len(served),
        'predicted_join_to_boarding_seconds_range':[min(r['join_to_boarding_seconds'] for r in served),max(r['join_to_boarding_seconds'] for r in served)],
        'post_boarding_seconds_range':[min(r['post_boarding_seconds'] for r in served),max(r['post_boarding_seconds'] for r in served)],
        'protocol_sha256':hashlib.sha256(lock.read_bytes()).hexdigest(),'new_coefficients_fitted':False,
        'observed_seconds':{'join_to_board':189,'board_to_departure':30,'join_to_departure':219},
        'interpretation':'A single event cannot identify vehicle arrival, door delay, throughput, occupancy and queue allocation. More hypotheses are not more observations.',
        'full_network_dwell_integrated':False,'capacity_conclusion':'Two 44-person buses have 88 total places only when empty. Existing onboard load must be subtracted separately.'}
    save(ROOT/'micro_sensitivity.json',summary);print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
