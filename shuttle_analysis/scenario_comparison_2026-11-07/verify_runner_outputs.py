"""Independent arithmetic checks of the runner exports, without report ownership."""
from pathlib import Path
import json,hashlib,math
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'simulation_outputs'
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=load(OUT/'execution_provenance.json');assert p['status']=='complete'
    specs=load(ROOT/'scenario_specs.json');names=[s['name'] for s in specs['scenarios']]
    keys=['weekday','stop_id','direction','route_id','bin_minute','boarding_stage']
    types={'stop_id':str,'route_id':str}
    c=pd.read_csv(OUT/'conditional_mean_bins.csv',dtype=types)
    a=pd.read_csv(OUT/'stop_inflow_5min_scenarios.csv',dtype=types)
    assert set(a.scenario)==set(names)
    assert not c.duplicated(['destination_group',*keys]).any()
    assert not a.duplicated(['scenario',*keys]).any()
    assert a.expected_trip_events.ge(0).all() and np.isfinite(a.expected_trip_events).all()
    assert a.bin_minute.between(680,1389).all() and a.bin_minute.mod(5).eq(0).all()
    assert set(a.boarding_stage).issubset({1,2})
    filtered=c[c.bin_minute.between(680,1389)]
    reconstruction=[]
    for s in specs['scenarios']:
        rho=s['dorm_share'];q=s['immediate_trip_share']
        probs={'dorm':rho*q,'snu':(1-rho)*q*s['external_mix'][0],
               'nak':(1-rho)*q*s['external_mix'][1],'daehak':(1-rho)*q*s['external_mix'][2]}
        cf=filtered.copy();cf['reconstructed']=cf.conditional_trip_events*cf.destination_group.map(probs)
        expected=cf.groupby(keys,dropna=False,as_index=False).reconstructed.sum()
        joined=a[a.scenario==s['name']].merge(expected,on=keys,how='outer',indicator=True,validate='one_to_one')
        assert joined['_merge'].eq('both').all()
        error=float((joined.expected_trip_events-joined.reconstructed).abs().max())
        assert error<1e-8,(s['name'],error)
        reconstruction.append({'scenario':s['name'],'matched_bins':len(joined),'max_absolute_error':error})
    mean=a.groupby(['scenario','weekday'],as_index=False).expected_trip_events.sum()
    checks=pd.read_csv(OUT/'scenario_mode_conservation_by_rep.csv')
    assert checks.conservation_error.abs().max()<1e-6
    assert checks.groupby(['replicate','weekday']).generated_trip_events.nunique().eq(1).all()
    conditional=pd.read_csv(OUT/'conditional_mode_conservation_by_rep.csv')
    assert conditional.mode_conservation_error.abs().max()<1e-6
    assert conditional.boarding_link_error.abs().max()<1e-6
    dense_receipts=[]
    for stem,extra in [('replicate_stop_peaks',[]),('replicate_stop_direction_peaks',['direction'])]:
        r=pd.read_csv(OUT/(stem+'.csv'),dtype={'stop_id':str})
        pk=['scenario','replicate','window','weekday','stop_id',*extra]
        assert not r.duplicated(pk).any()
        assert set(r['window'])=={'all','afternoon'}
        assert np.allclose(r.all_boarding_total_events,r.first_boarding_total_events+r.transfer_boarding_total_events,atol=1e-6)
        assert (r.all_boarding_peak_events+1e-8>=r.first_boarding_peak_events).all()
        assert (r.all_boarding_peak_events+1e-8>=r.transfer_boarding_peak_events).all()
        group_keys=['window','weekday','stop_id',*extra]
        groups=r[group_keys].drop_duplicates()
        grid=pd.MultiIndex.from_product([names,range(1,11)],names=['scenario','replicate']).to_frame(index=False).merge(groups,how='cross')
        dense=grid.merge(r,on=pk,how='left',validate='one_to_one',indicator=True)
        dense['zero_filled']=dense['_merge'].eq('left_only')
        name_map=r.groupby('stop_id').stop_name.first()
        dense['stop_name']=dense.stop_name.fillna(dense.stop_id.map(name_map))
        metric_cols=[c for c in r.columns if c.endswith('_events')]
        dense[metric_cols]=dense[metric_cols].fillna(0)
        dense=dense.drop(columns='_merge')
        dense.to_csv(OUT/(stem+'_zero_filled.csv'),index=False,encoding='utf-8-sig')
        dense_receipts.append({'file':stem+'_zero_filled.csv','rows':len(dense),
                               'zero_filled_rows':int(dense.zero_filled.sum())})
    inventory=load(OUT/'original_inventory_before.json')
    old=ROOT.parent/'course_demand_2026-11-06'
    assert all(sha(old/name)==h for name,h in inventory.items())
    assert sha(ROOT/'scenario_specs.json')==p['specs_sha256']
    evidence=load(OUT/'input_snapshot/research_inputs.json')
    assert all(x is None for x in evidence['observed_current_destination_shares'].values())
    result={'status':'PASS','scenario_count':len(names),'replications':10,
            'conditional_csv_rows':len(c),'scenario_csv_rows':len(a),
            'independent_scenario_reconstruction':reconstruction,
            'maximum_mode_conservation_error':float(checks.conservation_error.abs().max()),
            'maximum_conditional_boarding_link_error':float(conditional.boarding_link_error.abs().max()),
            'duplicate_scenario_stop_route_stage_bins':0,
            'original_files_verified_unchanged':len(inventory),
            'equal_baseline_max_absolute_error':p['equal_baseline_max_absolute_error'],
            'zero_filled_peak_exports':dense_receipts,
            'unmeasured_current_destination_shares_preserved_null':True,
            'meaning':'Internal simulation arithmetic passed; not validation against observed queues or occupancy.'}
    (OUT/'runner_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    layout='''# Simulation output schema

Execution is complete only when execution_provenance.json has status=complete and runner_validation.json has status=PASS.

- stop_inflow_5min_scenarios.csv: existing schema; scenario/weekday/stop_id/stop_name/direction/route_id/route_name/time_bin/bin_minute/boarding_stage/expected_trip_events/lat/lon. Ten-replication means, restricted to 680 <= bin_minute < 1390. Values are stop-arrival boarding-demand weights, not actual boardings or measured congestion.
- conditional_mean_bins.csv: destination_group and conditional_trip_events replace scenario weights. Each group assumes all eligible enrollment events select that destination and move immediately. Multiply dorm by dorm_share*immediate_trip_share, and each external group by (1-dorm_share)*external_mix*immediate_trip_share, then sum. Includes outside-window bins for conservation checks; filter before comparison.
- conditional_mean_modes.csv and conditional_mode_conservation_by_rep.csv: whole modeled day, not only collection window. walk/city_first/shuttle_first/unassigned sum to enrollment weight independently for each destination condition.
- scenario_mode_conservation_by_rep.csv: whole-day scenario generation and modes. Transfer boardings are not new generated trips.
- replicate_stop_peaks.csv: raw positive-arrival physical-stop groups, with all/afternoon windows. Each row has separate all_boarding/first_boarding/transfer_boarding maximum five-minute weights, peak bins and window totals. The maximum of replicate bins differs from the maximum of mean bins.
- replicate_stop_direction_peaks.csv: same, preserving provider direction labels. These labels are not standardized compass directions.
- *_zero_filled.csv: complete replicate/scenario grid over the union of observed-in-simulation window/day/stop groups. Missing groups in raw peak exports mean zero simulated arrival events, not missing observations. Their peak times remain empty because no peak exists. Use these files when averaging replicate peaks; do not average only positive-presence rows.
- execution_provenance.json, input_manifest.json, evidence_snapshot_manifest.json: seeds, versions, hashes and assumptions. Original source and historical evidence are retained under input_snapshot/. Culture Hall's corrected stop is snu-300, distinct from Administration snu-410.
- original_preservation_check.json: original engine/source/output files and the user's XLS were preserved. No live bus APIs or production deployment settings were used.

Historical Sillim including Daehak is mapped to the Daehak representative point as a reference assumption. The original historical percentage discrepancy and current observed destination shares remain unchanged/null. No capacity, crowding-feedback or background-passenger model is introduced.
'''
    (OUT/'FILE_LAYOUT.md').write_text(layout,encoding='utf-8')
    files=[{'name':f.name,'bytes':f.stat().st_size,'sha256':sha(f)} for f in sorted(OUT.iterdir()) if f.is_file()]
    (OUT/'READY.json').write_text(json.dumps({'status':'READY','validation_status':'PASS','files':files},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':'PASS','reconstructed_scenarios':len(reconstruction),
        'scenario_bin_rows':len(a),'zero_filled':dense_receipts},ensure_ascii=False))

if __name__=='__main__':main()
