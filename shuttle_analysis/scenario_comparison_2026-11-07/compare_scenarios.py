"""Independent station aggregation and scenario comparison after the shared run."""
from pathlib import Path
import json
import hashlib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
SIM = ROOT / 'simulation_outputs'
spec = json.loads((ROOT/'scenario_specs.json').read_text(encoding='utf-8'))
baseline = spec['baseline']
df = pd.read_csv(SIM/'stop_inflow_5min_scenarios.csv', dtype={'stop_id':str,'route_id':str})
keys = ['scenario','weekday','stop_id','direction','route_id','bin_minute','boarding_stage']
assert set(df.scenario.unique()) == {s['name'] for s in spec['scenarios']}
assert not df.duplicated(keys).any()
assert df.expected_trip_events.ge(0).all()
assert df.bin_minute.between(680,1389).all()
assert set(df.boarding_stage.unique()) <= {1,2}

reference = pd.read_csv(ROOT/'independent_linear_reference.csv',dtype={'stop_id':str,'route_id':str})
check = reference.merge(df[keys+['expected_trip_events']],on=keys,how='outer',validate='one_to_one')
check[['reference_expected_trip_events','expected_trip_events']] = check[['reference_expected_trip_events','expected_trip_events']].fillna(0)
errors = np.abs(check.reference_expected_trip_events-check.expected_trip_events)
maxerr = float(errors.max())
assert maxerr < 1e-5, maxerr
summary_err=check.assign(abs_difference=errors).groupby('scenario').abs_difference.agg(['max','sum'])
summary_err.to_csv(ROOT/'independent_cell_reconciliation.csv',encoding='utf-8-sig')

names = df[['stop_id','stop_name']].drop_duplicates()
assert not names.stop_id.duplicated().any(), 'Resolve inconsistent labels before grouping stops'
name_map=names.set_index('stop_id').stop_name.to_dict()
day_order={'월':0,'화':1,'수':2,'목':3,'금':4}
def clock(x): return f'{int(x)//60:02d}:{int(x)%60:02d}'

def aggregate(entity_keys):
    outputs=[]
    for scope,(start,end) in spec['time_scopes'].items():
        part=df[df.bin_minute.ge(start)&df.bin_minute.lt(end)]
        for stage_label, stages in [('all',[1,2]),('first',[1]),('transfer',[2])]:
            cells=part[part.boarding_stage.isin(stages)].groupby(
                ['scenario','weekday']+entity_keys+['bin_minute'],as_index=False).expected_trip_events.sum()
            groupkeys=['scenario','weekday']+entity_keys
            cells=cells.sort_values(groupkeys+['bin_minute'])
            idx=cells.groupby(groupkeys).expected_trip_events.idxmax()
            peaks=cells.loc[idx].rename(columns={'bin_minute':'peak_bin_minute','expected_trip_events':'peak_5min_weight'})
            totals=cells.groupby(groupkeys,as_index=False).expected_trip_events.sum().rename(columns={'expected_trip_events':'window_boarding_weight'})
            peaks=peaks.merge(totals,on=groupkeys,validate='one_to_one')
            bases=peaks[peaks.scenario.eq(baseline)].drop(columns='scenario').rename(columns={
                'peak_bin_minute':'baseline_peak_bin_minute','peak_5min_weight':'baseline_peak_5min_weight',
                'window_boarding_weight':'baseline_window_boarding_weight'})
            peaks=peaks.merge(bases,on=['weekday']+entity_keys,how='left',validate='many_to_one')
            probes=peaks[['scenario','weekday']+entity_keys+['baseline_peak_bin_minute']].rename(columns={'baseline_peak_bin_minute':'bin_minute'})
            probes=probes.merge(cells,on=['scenario','weekday']+entity_keys+['bin_minute'],how='left',validate='one_to_one')
            peaks['weight_at_baseline_peak_bin']=probes.expected_trip_events.fillna(0).to_numpy()
            peaks['peak_change_weight']=peaks.peak_5min_weight-peaks.baseline_peak_5min_weight
            peaks['peak_change_percent']=100*peaks.peak_change_weight/peaks.baseline_peak_5min_weight.replace(0,np.nan)
            peaks['same_bin_change_percent']=100*(peaks.weight_at_baseline_peak_bin/peaks.baseline_peak_5min_weight.replace(0,np.nan)-1)
            peaks['peak_time']=peaks.peak_bin_minute.map(clock)
            peaks['baseline_peak_time']=peaks.baseline_peak_bin_minute.map(clock)
            peaks['window']=scope;peaks['stage']=stage_label
            peaks['stop_name']=peaks.stop_id.map(name_map)
            outputs.append(peaks)
    return pd.concat(outputs,ignore_index=True)

station=aggregate(['stop_id'])
direction=aggregate(['stop_id','direction'])
station.to_csv(ROOT/'stop_peak_comparison.csv',index=False,encoding='utf-8-sig')
direction.to_csv(ROOT/'direction_peak_comparison.csv',index=False,encoding='utf-8-sig')

# Max of the ten-replication MEAN bins, not the mean of per-replication maxima.
weekly=station.assign(day_order=station.weekday.map(day_order)).sort_values(['day_order','peak_bin_minute'])
wkeys=['scenario','window','stage','stop_id']
weekly=weekly.loc[weekly.groupby(wkeys).peak_5min_weight.idxmax()].copy()
baseweekly=weekly[weekly.scenario.eq(baseline)][['window','stage','stop_id','peak_5min_weight','weekday','peak_time']].rename(columns={
    'peak_5min_weight':'baseline_weekly_peak_weight','weekday':'baseline_weekly_peak_weekday','peak_time':'baseline_weekly_peak_time'})
weekly=weekly.merge(baseweekly,on=['window','stage','stop_id'],validate='many_to_one')
weekly['weekly_peak_change_percent']=100*(weekly.peak_5min_weight/weekly.baseline_weekly_peak_weight.replace(0,np.nan)-1)
weekly.to_csv(ROOT/'weekly_stop_peak_comparison.csv',index=False,encoding='utf-8-sig')
network=station.loc[station.groupby(['scenario','window','stage','weekday']).peak_5min_weight.idxmax()]
network.to_csv(ROOT/'network_peak_comparison.csv',index=False,encoding='utf-8-sig')

# Keep both the largest modeled sites and upper-engineering-specific boarding points.
priority=['snu-410','120000174','120000173','snu-1001','snu-901','120900172','120000191','120000177']
priority=[x for x in priority if x in name_map]
payload={
 'metric':'월~금 중 가장 큰 5분 예상 탑승 통행 가중치',
 'unit':'통행 가중치/5분; 관측 인원·잔류 대기열 아님',
 'selected_stops':priority,
 'scenarios':[{k:s[k] for k in ['name','label','external_mix','dorm_share','immediate_trip_share']} for s in spec['scenarios']],
 'rows':weekly[weekly.stop_id.isin(priority)&weekly.stage.eq('all')][[
     'scenario','window','stop_id','stop_name','weekday','peak_time','peak_5min_weight',
     'baseline_weekly_peak_weight','baseline_weekly_peak_weekday','baseline_weekly_peak_time','weekly_peak_change_percent']].to_dict('records'),
}
(ROOT/'comparison_chart_data.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')

validation={
 'status':'PASS_CONDITIONAL_SCENARIO_COMPARISON',
 'interpretation':'Numerical consistency of a conditional scenario, not measured crowding or empirical predictive accuracy.',
 'scenarios':len(spec['scenarios']), 'all_scenario_destination_probabilities_sum_to_one':all(abs(sum(s['external_mix'])-1)<1e-12 for s in spec['scenarios']),
 'input_row_count':len(df), 'independent_archived_mixture_max_abs_cell_difference':maxerr,
 'comparison_grain':'distinct stop_id; routes and boarding stages summed at same five-minute bin; direction details retained separately',
 'peak_rule':'maximum of ten-replication mean bins, per stop/day or across Mon-Fri; afternoon window starts 15:00',
 'same_bin_changes_retained':True, 'source_sha256':hashlib.sha256((SIM/'stop_inflow_5min_scenarios.csv').read_bytes()).hexdigest(),
 'spec_sha256':hashlib.sha256((ROOT/'scenario_specs.json').read_bytes()).hexdigest(),
}
(ROOT/'comparison_validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf-8')
out=weekly[weekly.window.eq('afternoon')&weekly.stage.eq('all')&weekly.stop_id.isin(priority)]
print(out.pivot(index=['stop_id','stop_name'],columns='scenario',values='peak_5min_weight').round(2).to_string())
print(json.dumps(validation,ensure_ascii=False))
