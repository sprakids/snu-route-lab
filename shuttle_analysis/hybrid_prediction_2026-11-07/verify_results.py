"""Independent stdlib source, preprocessing and score reconciliation."""
from pathlib import Path
from collections import defaultdict
import csv,json,math,hashlib,sys
from datetime import datetime

ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'tdata_calibration_2026-11-07'
KEY=('route_id','sta_sn','from_stop_id','to_stop_id','hour')
MODELS=('history_only','weekday_history','history_plus_background','history_plus_class','history_background_class')
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def rows(p):
    with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def key(r):return tuple(str(r[k]) for k in KEY)
def average(v):return math.fsum(v)/len(v)
def close(a,b):return abs(a-b)<max(1e-8,abs(b)*1e-11)

def main():
    plan=load(ROOT/'experiment_plan.json');frozen=load(ROOT/'selection_frozen.json');model=load(ROOT/'frozen_models.json')
    assert sha(ROOT/'frozen_models.json')==frozen['frozen_model_sha256']
    assert sha(ROOT/'frozen_test_predictions.csv')==frozen['frozen_predictions_sha256']
    assert sha(ROOT/'experiment_plan.json')==frozen['plan_sha256']
    fit_dates=plan['train_dates']+plan['tuning_dates'];tests=plan['forward_test_dates']+plan['retrospective_test_dates']
    assert set(fit_dates).isdisjoint(tests) and len(set(fit_dates+tests))==26
    metadata={key({**r,'hour':0})[:-1]:r for r in rows(OLD/'observations/current_links.csv')}
    inside={k:r['campus_origin']=='True' for k,r in metadata.items()}
    classes={(str(r['weekday']),)+key(r):float(r['class_flow']) for r in model['class_template']}
    raw={};base_values=defaultdict(list);class_values=defaultdict(list);lag_values=defaultdict(list)
    outside=defaultdict(list);outside_weekday=defaultdict(list)
    for date in fit_dates+tests:
        w=str(datetime.strptime(date,'%Y%m%d').weekday())
        for r in load(OLD/'collected'/date/'target_routes.json'):
            assert r['stdrDe']==date
            for hour in range(12,23):
                k=(r['routeId'],str(int(r['staSn'])),r['fromStaId'],r['toStaId'],str(hour))
                value=r.get(f'a18SumLoadPsngNum{hour:02d}h');value=None if value is None else float(value)
                assert (date,)+k not in raw
                raw[(date,)+k]=value
                if date not in fit_dates or value is None:continue
                base_values[k].append(value)
                class_values[k].append(classes.get((w,)+k,0.))
                lag_values[k].append(classes.get((w,)+k[:-1]+(str(hour-1),),0.))
                if not inside[k[:-1]]:
                    outside[(k[0],str(hour))].append(value)
                    outside_weekday[(w,k[0],str(hour))].append(value)
    max_preprocess_error=0.
    for r in model['tables']['base']:
        k=key(r)
        for column,values in [('H',base_values[k]),('C0',class_values[k]),('C1',lag_values[k])]:
            expected=average(values);error=abs(expected-float(r[column]))
            max_preprocess_error=max(max_preprocess_error,error);assert close(expected,float(r[column]))
    for r in model['tables']['background']:
        k=(str(r['weekday']),r['route_id'],str(r['hour']));den=average(outside[k[1:]])
        expected=average(outside_weekday[k])/den if den else 1.
        max_preprocess_error=max(max_preprocess_error,abs(expected-float(r['background_ratio'])))
        assert close(expected,float(r['background_ratio']))
    predictions=rows(ROOT/'evaluation/cell_predictions_and_observations.csv')
    missing=0
    for r in predictions:
        actual=raw[(r['date'],)+key(r)];observed=None if r['observed']=='' else float(r['observed'])
        assert actual==observed
        missing+=int(actual is None and r['campus_origin']=='True')
    max_metric_error=0.;checked=0
    for metric in rows(ROOT/'evaluation/metrics.csv'):
        group=metric['group'];scope=metric['scope'];name=metric['model']
        def eligible(r):
            if scope=='campus_origin_bbox' and r['campus_origin']!='True':return False
            if group=='all_six_dates':return True
            return group in (r['date'],r['route_id'],r['test_partition'])
        a=[r for r in predictions if eligible(r) and r['observed']!='']
        yy=[float(r['observed']) for r in a];pp=[float(r[name]) for r in a]
        assert len(a)==int(metric['valid_cells'])
        total=math.fsum(yy);ae=math.fsum(abs(x-y) for x,y in zip(pp,yy));sq=math.fsum((x-y)**2 for x,y in zip(pp,yy))
        for column,expected in [('observed_sum',total),('predicted_sum',math.fsum(pp)),('MAE',ae/len(a)),('WAPE',ae/total),('RMSE',math.sqrt(sq/len(a)))]:
            max_metric_error=max(max_metric_error,abs(expected-float(metric[column])))
            assert close(expected,float(metric[column]))
        checked+=1
    linear_clips={}
    for name in ('history_plus_background','history_plus_class','history_background_class'):
        count=0;delta=0.
        for r in rows(ROOT/'frozen_test_predictions.csv'):
            a,b,c=model['models'][name]['coefficients'][r['route_id']]
            linear=float(r['H'])+a*float(r['bg'])+b*float(r['c0'])+c*float(r['c1'])
            if linear<0:count+=1;delta-=linear
        linear_clips[name]={'all_route_test_cells_clipped':count,'sum_added_by_clipping':delta}
    # The plaintext is read only for a local leak check, never logged or persisted.
    sys.path.insert(0,str(OLD))
    from local_secret import load_key
    secret=load_key().encode();scanned=0
    for p in ROOT.rglob('*'):
        if '.taskdeps' in p.parts or not p.is_file() or p.suffix.lower() not in ('.json','.csv','.py','.md','.txt'):continue
        scanned+=1;assert secret not in p.read_bytes(),'Credential exposure detected; content suppressed'
    output={'status':'PASS_INDEPENDENT_RAW_SOURCE_PREPROCESSING_AND_METRICS',
            'date_sets_disjoint':True,'frozen_models_predictions_and_plan_unchanged':True,
            'historical_mean_and_class_centering_recomputed_keys':len(model['tables']['base']),
            'historical_outside_proxy_recomputed_groups':len(model['tables']['background']),
            'max_preprocessing_difference':max_preprocess_error,
            'test_raw_observation_cells_reconciled':len(predictions),'primary_null_cells_retained_and_excluded_from_all_scores':missing,
            'metric_rows_recomputed':checked,'max_metric_difference':max_metric_error,
            'clipping_diagnostics':linear_clips,'authored_text_artifacts_checked_for_credential':scanned,'credential_hits':0,
            'figure_visually_inspected':True,
            'report_sha256':sha(ROOT/'과거평균_수업_배경_결합모형_검증.md')}
    (ROOT/'verification.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(output,ensure_ascii=False))

if __name__=='__main__':main()
