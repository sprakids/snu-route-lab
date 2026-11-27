"""Check the collaborator's read-only feature binding against exported baseline."""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
from datetime import date,timedelta
import importlib.util,json,hashlib
import pandas as pd

ROOT=Path(__file__).resolve().parent
CALIB=ROOT.parents[1]
OUT=ROOT/'outputs'
assert json.loads((OUT/'READY.json').read_text(encoding='utf-8'))['status']=='READY_CONDITIONAL_FEATURES'
module_path=CALIB/'calibrate_model.py'
spec=importlib.util.spec_from_file_location('calibration_binding_readonly',module_path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
actual=module.standardized_features(OUT/'conditional_segment_hour.csv')
baseline=pd.read_csv(OUT/'baseline_segment_hour.csv',dtype={'route_id':str,'from_stop_id':str,'to_stop_id':str})
actual_offsets=sorted(int(x) for x in baseline.day_offset.unique())
days='월화수목금토일';monday=date(2026,10,19)
baseline['weekday']=[days[(monday+timedelta(days=days.index(d)+int(offset))).weekday()]
                     for d,offset in zip(baseline.weekday,baseline.day_offset)]
baseline=baseline.rename(columns={'clock':'operator','observed_sta_sn':'sta_sn'})
baseline['sta_sn']=baseline.sta_sn.astype(int)
keys=['operator']+module.KEY
expected=baseline.groupby(keys,as_index=False).expected_trip_events.sum()
joined=actual.merge(expected,on=keys,how='outer',validate='one_to_one',indicator=True)
assert joined['_merge'].eq('both').all()
error=float((joined.model_base-joined.expected_trip_events).abs().max())
assert error<1e-9,error
plan=json.loads((CALIB/'analysis_plan.json').read_text(encoding='utf-8'))
assert set(plan['train_dates']).isdisjoint(plan['evaluation_dates'])
assert plan['model_fixed_scenario']['immediate_trip_share']==.5
# The actual export has no midnight spill; exercise nonzero offsets separately.
synthetic=[]
for clock in ('segment_entry','boarding_hour'):
    for origin,offset,hour,group,value in [('금',1,0,'dorm',100),('금',0,23,'dorm',100),('일',1,0,'nak',20)]:
        synthetic.append({'clock':clock,'weekday':origin,'day_offset':offset,'hour':hour,'destination_group':group,
            'route_id':'synthetic','from_stop_id':'A','to_stop_id':'B','observed_sta_sn':1,'conditional_trip_events':value})
fixture=ROOT/'synthetic_offset_fixture.csv'
pd.DataFrame(synthetic).to_csv(fixture,index=False,encoding='utf-8-sig')
fixture_bound=module.standardized_features(fixture)
rho=5772/29613
for operator in ('segment_entry','boarding_hour'):
    values=fixture_bound[fixture_bound.operator.eq(operator)].set_index(['weekday','hour']).model_base
    assert abs(values.loc[('토',0)]-100*rho*.5)<1e-12
    assert abs(values.loc[('금',23)]-100*rho*.5)<1e-12
    assert abs(values.loc[('월',0)]-20*(1-rho)/6)<1e-12
result={'status':'PASS_CALIBRATION_FEATURE_BINDING','matched_rows':len(joined),
        'maximum_probability_and_weekday_binding_difference':error,
        'date_offset_applied_once_in_weekly_template':True,
        'actual_export_day_offsets':actual_offsets,
        'nonzero_offset_verified_on_actual_export':any(x!=0 for x in actual_offsets),
        'nonzero_and_week_wrap_verified_on_separate_synthetic_fixture':True,
        'date_sets_disjoint':True,'conditional_probabilities_applied_once':True,
        'features_sha256':hashlib.sha256((OUT/'conditional_segment_hour.csv').read_bytes()).hexdigest(),
        'calibration_source_sha256':hashlib.sha256(module_path.read_bytes()).hexdigest(),
        'calibration_main_executed':False,'credential_tools_imported_or_run':False,
        'empirical_metrics_reviewed':False}
(ROOT/'calibration_binding_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
