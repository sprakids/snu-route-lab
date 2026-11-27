"""Independent arithmetic and source reconciliation; redact credentials entirely."""
from pathlib import Path
from collections import defaultdict
import csv,json,math,hashlib
from local_secret import load_key

ROOT=Path(__file__).resolve().parent
KEY_FIELDS=('date','route_id','sta_sn','from_stop_id','to_stop_id','hour')
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def rows(p):
    with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def dump(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def key(r):return tuple(r[x] for x in KEY_FIELDS)
def close(a,b):return abs(a-b)<max(1e-8,abs(b)*1e-11)

def main():
    plan=load(ROOT/'analysis_plan.json');receipt=load(ROOT/'calibration/calibration_receipt.json')
    quality=load(ROOT/'observations/quality_audit.json')
    assert receipt['analysis_plan_sha256']==sha(ROOT/'analysis_plan.json')==quality['analysis_plan_sha256']
    assert receipt['observations_sha256']==sha(ROOT/'observations/hourly_observations.csv')
    assert receipt['features_sha256']==sha(receipt['features_source'])
    assert set(plan['train_dates']).isdisjoint(plan['evaluation_dates'])
    raw={}
    for date in plan['train_dates']+plan['evaluation_dates']:
        for r in load(ROOT/'collected'/date/'target_routes.json'):
            for hour in range(24):
                k=(date,r['routeId'],str(int(r['staSn'])),r['fromStaId'],r['toStaId'],str(hour))
                assert k not in raw
                value=r.get(f'a18SumLoadPsngNum{hour:02d}h')
                raw[k]=None if value is None else float(value)
    predictions=rows(ROOT/'calibration/cell_predictions.csv')
    matched=0;groups=defaultdict(list);history=defaultdict(list)
    for r in predictions:
        observed=raw[key(r)];stored=None if r['sum_load']=='' else float(r['sum_load'])
        assert observed==stored,'Prediction cells changed raw observations'
        matched+=1
        group_key=(r['operator'],r['split'],r['campus_origin'])
        groups[group_key].append(r)
        if r['operator']=='segment_entry' and r['split']=='train' and stored is not None:
            history[tuple(r[x] for x in ('route_id','sta_sn','from_stop_id','to_stop_id','hour'))].append(stored)
    for r in predictions:
        vals=history.get(tuple(r[x] for x in ('route_id','sta_sn','from_stop_id','to_stop_id','hour')),[])
        value=float(r['history_mean']) if r['history_mean'] else None
        assert (value is None and not vals) or (vals and close(value,math.fsum(vals)/len(vals)))
    primary=[r for r in predictions if r['campus_origin']=='True']
    coef=rows(ROOT/'calibration/coefficients.csv');max_coefficient_error=0.
    for c in coef:
        train=[r for r in primary if r['operator']==c['operator'] and r['split']=='train' and r['sum_load']!=''
               and (c['fit_group']=='all_routes' or r['route_id']==c['fit_group'])]
        xx=math.fsum(float(r['model_base'])**2 for r in train)
        xy=math.fsum(float(r['model_base'])*float(r['sum_load']) for r in train)
        a=max(0.,xy/xx) if xx else 0.
        max_coefficient_error=max(max_coefficient_error,abs(a-float(c['alpha'])))
        assert close(a,float(c['alpha']))
    checks=0;max_metric_error=0.
    for m in rows(ROOT/'calibration/metrics.csv'):
        if m['group']!='all_routes':continue
        subset=[r for r in predictions if r['operator']==m['operator'] and r['split']==m['split']
                and (m['scope']=='all_route_links' or r['campus_origin']=='True')]
        valid=[r for r in subset if r['sum_load']!='' and r[m['prediction']]!='']
        ysum=math.fsum(float(r['sum_load']) for r in valid)
        errors=[float(r[m['prediction']])-float(r['sum_load']) for r in valid]
        absolute=math.fsum(abs(e) for e in errors)
        expected={'MAE':absolute/len(valid),'WAPE':absolute/ysum,'RMSE':math.sqrt(math.fsum(e*e for e in errors)/len(valid)),
                  'observed_sum':ysum,'predicted_sum':math.fsum(float(r[m['prediction']]) for r in valid)}
        assert int(m['valid_cells'])==len(valid)
        for name,value in expected.items():
            difference=abs(value-float(m[name]));max_metric_error=max(max_metric_error,difference)
            assert close(value,float(m[name])),(m['operator'],m['prediction'],name)
        checks+=1
    # Search only task artifacts. The credential remains an in-process byte string
    # and no content, key fragment or secret-bearing exception is ever printed.
    secret=load_key().encode('utf-8');hits=[];scanned=0
    for p in ROOT.rglob('*'):
        if p.is_file() and p.suffix.lower() in ('.json','.csv','.md','.txt','.py'):
            scanned+=1
            if secret in p.read_bytes():hits.append(str(p.relative_to(ROOT)))
    assert not hits,'Credential detected in task text artifacts; details suppressed'
    report={'status':'PASS_INDEPENDENT_SOURCE_AND_ARITHMETIC_RECONCILIATION',
            'raw_observation_prediction_cells_reconciled':matched,
            'training_mean_recomputed_without_evaluation_values':True,
            'coefficients_recomputed_from_train_only':len(coef),'max_coefficient_difference':max_coefficient_error,
            'all_route_and_campus_aggregate_metric_rows_recomputed':checks,'max_metric_difference':max_metric_error,
            'text_artifacts_scanned_for_exact_plaintext_credential':scanned,'credential_hits':0,'credential_printed':False,
            'provider_semantics_confirmed':False,'population_scope_mismatch_resolved':False,
            'report_sha256':sha(ROOT/'과거_재차합_수집과_예비보정_결과.md')}
    dump(ROOT/'artifact_verification.json',report)
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
