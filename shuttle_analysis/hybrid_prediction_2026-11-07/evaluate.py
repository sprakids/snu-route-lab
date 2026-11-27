"""One untouched-target evaluation of already frozen model predictions."""
import sys
sys.dont_write_bytecode=True
from collections import defaultdict
import numpy as np
import pandas as pd
from common import *
from predictor import FrozenPredictor

OUT=ROOT/'evaluation'

def main():
    assert not OUT.exists(),'Do not overwrite a held-out result or tune from it'
    plan=load(ROOT/'experiment_plan.json');frozen=load(ROOT/'selection_frozen.json')
    assert sha(ROOT/'experiment_plan.json')==frozen['plan_sha256']
    assert sha(ROOT/'frozen_models.json')==frozen['frozen_model_sha256']
    assert sha(ROOT/'frozen_test_predictions.csv')==frozen['frozen_predictions_sha256']
    dates=plan['forward_test_dates']+plan['retrospective_test_dates']
    assert set(dates)==set(frozen['test_dates_never_loaded'])
    assert set(dates).isdisjoint(frozen['development_dates_used'])
    # This standalone inference path has no pandas/numpy dependency or target access.
    predictor=FrozenPredictor(ROOT/'frozen_models.json')
    predicted=pd.read_csv(ROOT/'frozen_test_predictions.csv',dtype={'date':str,'route_id':str,'from_stop_id':str,'to_stop_id':str})
    maximum=0.
    for r in predicted.to_dict('records'):
        p=predictor.predict(r['date'],r['route_id'],r['sta_sn'],r['from_stop_id'],r['to_stop_id'],r['hour'])
        for name in MODELS:maximum=max(maximum,abs(float(r[name])-p[name]))
    assert maximum<1e-8,'Backend export does not reproduce frozen predictions'
    observed,audits=observations(dates)
    joined=predicted.merge(observed[['date']+KEY+['observed']],on=['date']+KEY,how='left',validate='one_to_one')
    assert len(joined)==len(predicted)
    assert joined[list(MODELS)].notna().all().all()
    # Verify that the final parameters preceded every full test collection.
    from datetime import datetime
    freeze_time=datetime.fromisoformat(frozen['created_utc'])
    test_source_times={}
    for date in dates:
        metas=list((OLD/'collected'/date).glob('page_*.receipt.json'))
        assert metas
        # Filesystem dates corroborate the recorded explicit source-access barrier.
        earliest=min(p.stat().st_mtime for p in metas)
        assert earliest>=freeze_time.timestamp()-2,'Test full collection predates model freeze'
        test_source_times[date]=earliest
    joined['test_partition']=joined.date.map(lambda d:'forward_20261102' if d in plan['forward_test_dates'] else 'retrospective_20261012_16')
    results=[]
    for scope,cells in [('campus_origin_bbox',joined[joined.campus_origin]),('all_route_links',joined)]:
        partitions=[('all_six_dates',cells)]+list(cells.groupby('test_partition'))
        partitions+=list(cells.groupby('date'))+list(cells.groupby('route_id'))
        for group,g in partitions:
            for model in MODELS:results.append({'scope':scope,'group':group,'model':model,**metrics(g.observed,g[model])})
    scores=pd.DataFrame(results)
    OUT.mkdir();scores.to_csv(OUT/'metrics.csv',index=False,encoding='utf-8-sig')
    joined.to_csv(OUT/'cell_predictions_and_observations.csv',index=False,encoding='utf-8-sig')
    dump(OUT/'source_audit.json',audits)
    daily=[]
    for date,g in joined[joined.campus_origin].groupby('date'):
        daily.append({'date':date,'observed_sum':float(g.observed.sum()),
                      'history_absolute_error':float((g.observed-g.history_only).abs().sum()),
                      'hybrid_absolute_error':float((g.observed-g.history_background_class).abs().sum())})
    # Day-cluster bootstrap describes the small retrospective week only.
    blocks=[r for r in daily if r['date'] in plan['retrospective_test_dates']]
    rng=np.random.default_rng(20261107);indices=rng.integers(0,len(blocks),(10000,len(blocks)))
    dy=np.array([r['observed_sum'] for r in blocks]);dd=np.array([r['history_absolute_error']-r['hybrid_absolute_error'] for r in blocks])
    diffs=dd[indices].sum(axis=1)/dy[indices].sum(axis=1)
    interval=np.quantile(diffs,[.025,.975]).tolist()
    receipt={'status':'COMPLETE_UNTOUCHED_TARGET_EVALUATION','created_utc':now(),
             'test_dates':dates,'primary_forward_dates':plan['forward_test_dates'],
             'secondary_retrospective_dates':plan['retrospective_test_dates'],
             'fit_dates_disjoint':True,'frozen_hashes_unchanged':True,
             'backend_inference_cells_verified':len(predicted),'backend_max_difference':maximum,
             'test_collection_epoch_seconds':test_source_times,
             'same_observed_mask_for_all_models':True,'observed_null_imputed':False,
             'retrospective_day_cluster_bootstrap_WAPE_improvement_95pct_interval':interval,
             'bootstrap_days':len(blocks),'bootstrap_note':'Five day clusters only; descriptive approximate interval; no interval for the single forward Monday',
             'daily_error_blocks':daily,'post_test_refit_or_selection':False,
             'strict_point_in_time_forecast':False,
             'limits':['Nov6 course export used for earlier dates','Hourly provider semantics not confirmed','Background is a historical outside-link proxy','No per-bus crowding or shuttle queue validation'],
             'source_hashes':{r['date']:r['sha256'] for r in audits},
             'freeze_sha256':sha(ROOT/'selection_frozen.json'),
             'outputs_sha256':{p.name:sha(p) for p in OUT.glob('*.csv')}}
    dump(OUT/'evaluation_receipt.json',receipt)
    print(scores[(scores.scope=='campus_origin_bbox') & scores.group.isin(['forward_20261102','retrospective_20261012_16','all_six_dates'])][['group','model','valid_cells','WAPE','MAE']].to_string(index=False))

if __name__=='__main__':main()
