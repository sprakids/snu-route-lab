"""Review frozen code/forecasts without opening any held-out observations."""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
from itertools import product
from collections import defaultdict
import importlib.util,json,hashlib,csv,math
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
EXP=ROOT.parent
load=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
plan=load(EXP/'experiment_plan.json');receipt=load(EXP/'selection_frozen.json')
tests=plan['forward_test_dates']+plan['retrospective_test_dates']
def audit(event,args):
    if event!='open' or not isinstance(args[0],(str,bytes)):return
    name=str(args[0]).replace('\\','/')
    if any('/collected/'+d+'/' in name for d in tests):
        raise AssertionError('Review must not open held-out observations')
sys.addaudithook(audit)
hashes={name:sha(EXP/name) for name in ['common.py','train_and_freeze.py','experiment_plan.json',
    'selection_frozen.json','frozen_models.json','frozen_test_predictions.csv']}
assert receipt['code_sha256']==hashes['train_and_freeze.py']
assert receipt['plan_sha256']==hashes['experiment_plan.json']
assert receipt['frozen_model_sha256']==hashes['frozen_models.json']
assert receipt['frozen_predictions_sha256']==hashes['frozen_test_predictions.csv']
assert set(receipt['development_dates_used'])==set(plan['train_dates']+plan['tuning_dates'])
assert set(receipt['test_dates_never_loaded'])==set(tests)
assert {x['date'] for x in receipt['training_sources']}==set(receipt['development_dates_used'])
assert set(receipt['development_dates_used']).isdisjoint(tests)

sys.path.insert(0,str(EXP))
import common
spec=importlib.util.spec_from_file_location('hybrid_training_readonly_review',EXP/'train_and_freeze.py')
training=importlib.util.module_from_spec(spec);spec.loader.exec_module(training)

# Exact convex examples exercise interior, upper/lower bounds and degenerate columns.
x=np.array(list(product([-1.,1.],repeat=3)))
y=x@np.array([1.8,2.,-.4])
z,_=training.quadratic_fit(x,y,(1,1,1),.1,.2)
assert np.allclose(z,[1.,2/1.2,0.],atol=1e-10,rtol=0)
z_inactive,_=training.quadratic_fit(x,y,(0,1,1),.1,.2)
assert np.allclose(z_inactive,[0.,2/1.2,0.],atol=1e-10,rtol=0)
s=np.array([-1.,1.]*4);collinear=np.column_stack([np.zeros(8),s,s])
z_collinear,_=training.quadratic_fit(collinear,2*s,(1,1,1),.1,.1)
assert np.allclose(z_collinear,[0.,2/2.1,2/2.1],atol=1e-10,rtol=0)
z_zero,_=training.quadratic_fit(np.zeros((4,3)),np.array([1.,-1.,2.,3.]),(1,1,1),.1,.1)
assert np.array_equal(z_zero,np.zeros(3))

# Synthetic template: grid() must use 11h values as the 12h lag.
original_metadata,original_template=common.metadata,common.template
try:
    meta=pd.DataFrame([{'route_id':'synthetic','sta_sn':i+1,'from_stop_id':f'A{i}',
                       'to_stop_id':f'B{i}','campus_origin':True} for i in range(259)])
    template=pd.DataFrame([{'weekday':0,'route_id':'synthetic','sta_sn':1,'from_stop_id':'A0',
        'to_stop_id':'B0','hour':h,'class_flow':v} for h,v in [(11,7.),(12,11.)]])
    common.metadata=lambda:meta.copy();common.template=lambda:template.copy()
    grid=common.grid(['20260105']) # synthetic calendar date, no observation read
    first=grid[grid.sta_sn.eq(1)].set_index('hour')
    assert first.loc[12,'class_flow']==11 and first.loc[12,'class_lag1']==7
    assert first.loc[13,'class_lag1']==11 and first.loc[14,'class_lag1']==0
finally:
    common.metadata,common.template=original_metadata,original_template

# Counterexample: class means use valid target rows; ratio-minus-one need not center B.
inside=[(0,100.,10.,4.),(0,110.,10.,4.),(1,120.,30.,12.),(1,None,30.,12.)]
rows=[{'weekday':w,'observed':v,'class_flow':c,'class_lag1':lag,'campus_origin':True,
    'route_id':'synthetic','sta_sn':1,'from_stop_id':'A','to_stop_id':'B','hour':12} for w,v,c,lag in inside]
rows += [{'weekday':w,'observed':v,'class_flow':0.,'class_lag1':0.,'campus_origin':False,
    'route_id':'synthetic','sta_sn':2,'from_stop_id':'B','to_stop_id':'C','hour':12} for w,v in [(0,60.),(1,40.)]]
frame=pd.DataFrame(rows);bound=training.bind(frame,training.history(frame))
valid=bound[bound.campus_origin & bound.observed.notna()]
assert abs(valid.c0.mean())<1e-12 and abs(valid.c1.mean())<1e-12
assert abs(valid.bg.mean()-110*.2/3)<1e-10

# Read frozen FORECASTS only. The held-out observation directory stays unopened.
artifact=load(EXP/'frozen_models.json')
forecast=pd.read_csv(EXP/'frozen_test_predictions.csv',dtype={'date':str,'route_id':str,'from_stop_id':str,'to_stop_id':str})
assert 'observed' not in forecast.columns
assert set(forecast.date)==set(tests)
assert len(forecast)==6*259*11 and not forecast.duplicated(['date']+common.KEY).any()
assert forecast.groupby('date').campus_origin.sum().eq(125*11).all()
for name in common.MODELS:assert np.isfinite(forecast[name]).all() and forecast[name].ge(0).all()
assert set(artifact['fit_dates']).isdisjoint(tests)
assert set(artifact['models'])==set(common.MODELS)

def cell(r):return (str(r['route_id']),int(r['sta_sn']),str(r['from_stop_id']),str(r['to_stop_id']),int(r['hour']))
weekday_counts=defaultdict(dict)
for r in artifact['tables']['weekday']:weekday_counts[cell(r)][int(r['weekday'])]=r['weekday_n']
template={(int(r['weekday']),cell(r)):r['class_flow'] for r in artifact['class_template']}
ratio={(int(r['weekday']),str(r['route_id']),int(r['hour'])):r['background_ratio'] for r in artifact['tables']['background']}
primary={cell(r) for r in forecast[forecast.campus_origin].drop_duplicates(common.KEY).to_dict('records')}
center_c0=[];center_c1=[];center_bg=[]
for row in artifact['tables']['base']:
    k=cell(row)
    if k not in primary:continue
    counts=weekday_counts[k];n=sum(counts.values())
    c0=math.fsum(count*(template.get((w,k),0)-row['C0']) for w,count in counts.items())/n
    lagkey=k[:-1]+(k[-1]-1,)
    c1=math.fsum(count*(template.get((w,lagkey),0)-row['C1']) for w,count in counts.items())/n
    bg=math.fsum(count*row['H']*(ratio.get((w,k[0],k[-1]),1)-1) for w,count in counts.items())/n
    center_c0.append(abs(c0));center_c1.append(abs(c1));center_bg.append(abs(bg))
assert max(center_c0)<1e-8 and max(center_c1)<1e-8

# Verify the frozen within-family tie rule, without rereading any target observations.
with (EXP/'development/tuning_candidates.csv').open(encoding='utf-8-sig',newline='') as f:candidates=list(csv.DictReader(f))
for name in common.MODELS:
    group=[r for r in candidates if r['kind']==name]
    number=lambda r,k:float(r[k]) if r[k] else 0.
    chosen=min(group,key=lambda r:(float(r['WAPE']),-number(r,'ridge_background')-number(r,'ridge_class'),-number(r,'k')))
    assert int(chosen['candidate_id'])==receipt['selected'][name]['development_score']['candidate_id']
assert len({(r['valid_cells'],r['observed_sum']) for r in candidates})==1
assert all(sha(EXP/name)==value for name,value in hashes.items()),'Frozen inputs changed during review'

result={'status':'PASS_FROZEN_CODE_AND_FORECAST_REVIEW_WITH_LIMITATIONS','source_hashes_reviewed':hashes,
    'test_observation_files_read':False,'keys_read':False,'api_calls':0,
    'model_or_hyperparameters_changed':False,'training_main_executed':False,
    'quadratic_reference_examples':['orthogonal box optimum','inactive components','ridge collinearity','zero features'],
    'lag_12_uses_11_hour_synthetic_check':True,'class_centering_uses_valid_target_rows_synthetic_check':True,
    'nonzero_background_mean_counterexample_confirmed':True,
    'frozen_forecast_rows':len(forecast),'frozen_forecast_dates':len(tests),
    'forecasts_and_model_match_selection_receipt_hashes':True,
    'class_centering_max_abs_final_primary':max(center_c0),'lag_centering_max_abs_final_primary':max(center_c1),
    'background_mean_max_abs_final_primary':max(center_bg),
    'selection_within_each_family_reproduced':True,'all_tuning_candidates_same_observation_count_and_sum':True,
    'common_py_hash_present_in_original_freeze_receipt':False,
    'point_in_time_operational_forecast_validated':False,'test_performance_reviewed':False}
(ROOT/'frozen_code_review_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
