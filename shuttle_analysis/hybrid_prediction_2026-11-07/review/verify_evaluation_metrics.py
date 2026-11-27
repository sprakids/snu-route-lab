"""Reconcile completed evaluation against frozen forecasts and raw test JSON.

This is explicitly AFTER verified selection freeze and AFTER the code-only review.
It never fits a model, changes a setting, or calls an API/credential tool.
"""
from pathlib import Path
from collections import defaultdict
from datetime import datetime,timezone,timedelta
import csv,json,hashlib,math

ROOT=Path(__file__).resolve().parent;EXP=ROOT.parent;OLD=EXP.parent/'tdata_calibration_2026-11-07'
load=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):
    with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
plan=load(EXP/'experiment_plan.json');frozen=load(EXP/'selection_frozen.json')
evaluation=load(EXP/'evaluation/evaluation_receipt.json')
method=load(ROOT/'frozen_code_review_checks.json')
assert method['test_observation_files_read'] is False
assert method['status']=='PASS_FROZEN_CODE_AND_FORECAST_REVIEW_WITH_LIMITATIONS'
assert sha(EXP/'selection_frozen.json')==evaluation['freeze_sha256']==method['source_hashes_reviewed']['selection_frozen.json']
assert sha(EXP/'frozen_test_predictions.csv')==frozen['frozen_predictions_sha256']
assert sha(EXP/'frozen_models.json')==frozen['frozen_model_sha256']
assert sha(EXP/'experiment_plan.json')==frozen['plan_sha256']
tests=plan['forward_test_dates']+plan['retrospective_test_dates']
assert set(tests).isdisjoint(frozen['development_dates_used'])
FIELDS=('date','route_id','sta_sn','from_stop_id','to_stop_id','hour')
def key(r):return (str(r['date']),str(r['route_id']),str(int(r['sta_sn'])),str(r['from_stop_id']),str(r['to_stop_id']),str(int(r['hour'])))
models=('history_only','weekday_history','history_plus_background','history_plus_class','history_background_class')
forecast={key(r):r for r in read(EXP/'frozen_test_predictions.csv')}
raw={};sources={};raw_rows=0
for day in tests:
    path=OLD/'collected'/day/'target_routes.json'
    sources[day]=sha(path);assert sources[day]==evaluation['source_hashes'][day]
    rows=load(path);assert len(rows)==259;raw_rows+=len(rows)
    for r in rows:
        assert r['stdrDe']==day
        for hour in range(24):
            k=(day,str(r['routeId']),str(int(r['staSn'])),str(r['fromStaId']),str(r['toStaId']),str(hour))
            assert k not in raw
            v=r.get(f'a18SumLoadPsngNum{hour:02d}h')
            raw[k]=None if v is None else float(v)
            assert raw[k] is None or (math.isfinite(raw[k]) and raw[k]>=0)
joined=read(EXP/'evaluation/cell_predictions_and_observations.csv')
assert len(joined)==len(forecast)==17094 and len({key(r) for r in joined})==len(joined)
largest_forecast_delta=0.
for r in joined:
    k=key(r);assert k in raw and k in forecast
    observed=None if not r['observed'] else float(r['observed'])
    assert observed==raw[k]
    assert r['test_partition']==('forward_20261102' if r['date'] in plan['forward_test_dates'] else 'retrospective_20261012_16')
    for model in models:
        value=float(r[model]);assert value>=0 and math.isfinite(value)
        delta=abs(value-float(forecast[k][model]));largest_forecast_delta=max(largest_forecast_delta,delta)
        assert delta<1e-10
groups={}
for scope in ('campus_origin_bbox','all_route_links'):
    pool=[r for r in joined if scope=='all_route_links' or r['campus_origin']=='True']
    groups[(scope,'all_six_dates')]=pool
    for field in ('test_partition','date','route_id'):
        for name in {r[field] for r in pool}:groups[(scope,name)]=[r for r in pool if r[field]==name]
metrics=read(EXP/'evaluation/metrics.csv');largest_metric_delta=0.;checked=0;primary=[]
for r in metrics:
    pool=groups[(r['scope'],r['group'])]
    valid=[x for x in pool if raw[key(x)] is not None]
    y=[raw[key(x)] for x in valid];p=[float(x[r['model']]) for x in valid]
    errors=[b-a for a,b in zip(y,p)];total=math.fsum(y)
    expected={'observed_sum':total,'predicted_sum':math.fsum(p),
        'MAE':math.fsum(abs(e) for e in errors)/len(valid),
        'WAPE':math.fsum(abs(e) for e in errors)/total if total else None,
        'RMSE':math.sqrt(math.fsum(e*e for e in errors)/len(valid))}
    assert int(r['valid_cells'])==len(valid)
    for name,value in expected.items():
        if value is None:assert r[name]==''
        else:
            delta=abs(value-float(r[name]));largest_metric_delta=max(largest_metric_delta,delta)
            assert delta<max(1e-8,abs(value)*2e-12),(r['scope'],r['group'],r['model'],name)
    checked+=1
    if r['scope']=='campus_origin_bbox' and r['group'] in ('all_six_dates','forward_20261102','retrospective_20261012_16'):
        primary.append({'group':r['group'],'model':r['model'],'candidate_cells':len(pool),
            'valid_cells':len(valid),'missing_observations':len(pool)-len(valid),**expected})
for group in ('all_six_dates','forward_20261102','retrospective_20261012_16'):
    masks=[(x['valid_cells'],x['observed_sum']) for x in primary if x['group']==group]
    assert len(masks)==5 and len(set(masks))==1
assert sha(EXP/'selection_frozen.json')==evaluation['freeze_sha256']
record={'status':'PASS_POST_FREEZE_RAW_AND_METRIC_RECONCILIATION',
    'reviewed_at_kst':datetime.now(timezone(timedelta(hours=9))).isoformat(),
    'method_review_saved_before_this_observation_read':True,
    'raw_test_rows_reconciled':raw_rows,'raw_hour_cells':len(raw),
    'frozen_forecast_rows_reconciled':len(joined),'metrics_rows_recomputed':checked,
    'max_frozen_forecast_difference':largest_forecast_delta,'max_metric_difference':largest_metric_delta,
    'primary_results':primary,'observed_null_filled_with_zero':False,
    'all_models_same_observed_masks':True,'model_refit_or_settings_changed':False,
    'source_hashes':sources,'freeze_sha256':evaluation['freeze_sha256'],
    'bootstrap_interval_independently_validated':False,
    'authentication_keys_read':False,'api_calls':0,
    'strict_point_in_time_prediction_validated':False}
(ROOT/'evaluation_metric_review.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in record.items() if k not in ('primary_results','source_hashes')},ensure_ascii=False,indent=2))
print(json.dumps(primary,ensure_ascii=False))
