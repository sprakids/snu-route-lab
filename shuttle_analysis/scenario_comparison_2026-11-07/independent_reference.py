"""Reconstruct conditional weights from archived scenarios, independent of new runner.

This checks scenario mixing/export consistency, not empirical predictive accuracy.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OLD = ROOT.parent / 'course_demand_2026-11-06' / 'outputs'
spec = json.loads((ROOT / 'scenario_specs.json').read_text(encoding='utf-8'))
df = pd.read_csv(OLD / 'stop_inflow_5min_scenarios.csv', dtype={'stop_id':str, 'route_id':str})
keys = ['weekday', 'stop_id', 'direction', 'route_id', 'bin_minute', 'boarding_stage']
assert not df.duplicated(['scenario'] + keys).any()
pivot = df.pivot(index=keys, columns='scenario', values='expected_trip_events').fillna(0)
dorm = spec['selected_dorm_numerator'] / spec['selected_dorm_denominator']

def weights(d, mix):
    return np.array([d] + [(1-d)*x for x in mix]) * 0.5

basis_names = ['dorm10_depart50','dorm30_depart50','snu_dominant','nak_dominant']
basis = np.array([weights(.1,[1/3]*3), weights(.3,[1/3]*3),
                  weights(dorm,[.6,.2,.2]), weights(dorm,[.2,.6,.2])])
conditional = np.linalg.solve(basis, pivot[basis_names].to_numpy().T).T
old_check = conditional @ weights(dorm,[.2,.2,.6])
max_check = float(np.max(np.abs(old_check-pivot['daehak_dominant'])))
assert max_check < 1e-5, max_check
rows=[]
for s in spec['scenarios']:
    vals = conditional @ weights(s['dorm_share'], s['external_mix'])
    # Negative sub-micro values are possible solely from old CSV rounding.
    assert vals.min() > -1e-5
    part=pivot.index.to_frame(index=False)
    part['scenario']=s['name']; part['reference_expected_trip_events']=vals
    rows.append(part)
pd.concat(rows,ignore_index=True).to_csv(ROOT/'independent_linear_reference.csv',index=False,encoding='utf-8-sig')
record={'method':'Invert four archived scenario mixtures to recover destination-conditional values, then apply new specified probabilities.',
        'scope':'Mixing and export verification, not empirical accuracy.',
        'old_csv_rounding_decimals':6,'matrix_condition_number':float(np.linalg.cond(basis)),
        'held_out_old_daehak_dominant_max_abs_difference':max_check,
        'cell_count_per_scenario':len(pivot),'new_scenarios':len(rows)}
(ROOT/'independent_reference_check.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps(record))
