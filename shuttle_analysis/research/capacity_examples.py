"""Exact illustrative calculations, never an estimate of observed SNU demand."""
from fractions import Fraction
from math import ceil
from pathlib import Path
import csv, json

ROOT=Path(__file__).resolve().parent
rows=[]
for h in [3,5,10,15,20,30]:
    f=Fraction(60,h)
    rows.append({'scenario':'illustrative_not_observed', 'headway_minutes':h,
                 'departures_per_hour_long_run':str(f),
                 'supply_formula_passengers_per_hour':f'{f} * available_passenger_capacity'})
with (ROOT/'evidence/capacity_formulas.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)

def residual_queue(initial, new_arrivals, available_capacity):
    assert min(initial,new_arrivals,available_capacity)>=0
    boarded=min(initial+new_arrivals,available_capacity)
    return {'boarded':boarded,'remaining':initial+new_arrivals-boarded}

# Conservation check for a constructed bulk-service example, not field data.
q=residual_queue(10,30,25)
assert q=={'boarded':25,'remaining':15}
assert 10+30==q['boarded']+q['remaining']
uniform=Fraction(10*10+10*10,2*(10+10))
uneven=Fraction(5*5+15*15,2*(5+15))
assert uniform==5 and uneven==Fraction(25,4)
results={'scenario':'illustrative_not_observed',
         'reverse_if_25_passenger_places_and_20min_headway':str(Fraction(60,20)*25),
         'fleet_lower_bound_50min_cycle_10min_headway':ceil(50/10),
         'fleet_lower_bound_60min_cycle_10min_headway':ceil(60/10),
         'uniform_10min_headways_random_arrival_wait_min':str(uniform),
         'alternating_5_15min_headways_random_arrival_wait_min':str(uneven),
         'queue_conservation_example':q,
         'article_S08_29_of_578_exact_percent':str(Fraction(29,578)*100)}
(ROOT/'evidence/calculation_checks.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps(results,indent=2))
