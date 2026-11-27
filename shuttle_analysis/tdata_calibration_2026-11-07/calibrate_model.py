"""Offline exploratory calibration with date-disjoint evaluation and fixed scope.

Fits effective scales of total segment load sums, never a student homebound rate.
All observed cells, including positive observations with zero modeled flow, remain.
"""
from pathlib import Path
from collections import defaultdict
import argparse, json, hashlib, math
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'calibration'
KEY=['weekday','route_id','sta_sn','from_stop_id','to_stop_id','hour']
LINK_HOUR=['route_id','sta_sn','from_stop_id','to_stop_id','hour']
OPERATORS=('segment_entry','boarding_hour')

def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def scale(x,y):
    denominator=float(x@x)
    return max(0.0,float(x@y)/denominator) if denominator>0 else 0.0

def metrics(frame,prediction):
    valid=frame['sum_load'].notna() & frame[prediction].notna()
    x=frame.loc[valid,prediction].to_numpy(float);y=frame.loc[valid,'sum_load'].to_numpy(float)
    error=x-y;n=len(x);total=float(y.sum())
    return {'candidate_cells':len(frame),'valid_cells':n,
            'missing_observations':int(frame['sum_load'].isna().sum()),
            'missing_predictions_on_observed':int((frame['sum_load'].notna() & frame[prediction].isna()).sum()),
            'observed_zero_cells':int((y==0).sum()),'observed_sum':total,'predicted_sum':float(x.sum()),
            'MAE':float(np.abs(error).mean()) if n else None,
            'WAPE':float(np.abs(error).sum()/total) if total else None,
            'RMSE':float(np.sqrt((error**2).mean())) if n else None,
            'model_zero_cells':int((frame.loc[valid,'model_base']==0).sum()),
            'observed_positive_model_zero_cells':int(((y>0)&(frame.loc[valid,'model_base'].to_numpy()==0)).sum()),
            'observed_sum_in_model_zero_cells':float(y[frame.loc[valid,'model_base'].to_numpy()==0].sum())}

def standardized_features(path):
    """Input contract for a zero-filled-across-repetitions conditional mean."""
    frame=pd.read_csv(path,dtype={'route_id':str,'from_stop_id':str,'to_stop_id':str})
    frame=frame.rename(columns={'clock':'operator','observed_sta_sn':'sta_sn'})
    assert set(frame.operator)==set(OPERATORS)
    # CSV weekday is the origin class-end day. Attribute to the modeled calendar
    # day without assuming that the provider's undocumented operating day agrees.
    if 'day_offset' in frame:
        days='월화수목금토일'
        frame['weekday']=[days[(days.index(d)+int(o))%7] for d,o in zip(frame.weekday,frame.day_offset)]
    required=set(KEY+['operator','destination_group','conditional_trip_events'])
    assert required.issubset(frame.columns),f'Feature contract missing {sorted(required-set(frame.columns))}'
    assert frame.sta_sn.notna().all()
    frame['sta_sn']=frame.sta_sn.astype(int)
    assert set(frame.destination_group)<=set(('dorm','snu','nak','daehak'))
    assert np.isfinite(frame.conditional_trip_events).all() and (frame.conditional_trip_events>=0).all()
    plan=load(ROOT/'analysis_plan.json');s=plan['model_fixed_scenario']
    rho=s['dorm_share_numerator']/s['dorm_share_denominator'];q=s['immediate_trip_share']
    weight={'dorm':rho*q,**{g:(1-rho)*v*q for g,v in zip(('snu','nak','daehak'),s['external_mix'])}}
    assert abs(sum(weight.values())-q)<1e-12
    frame['model_base']=frame.conditional_trip_events*frame.destination_group.map(weight)
    return frame.groupby(['operator']+KEY,as_index=False,dropna=False).model_base.sum()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--features',type=Path,required=True)
    args=parser.parse_args()
    assert not OUT.exists(),'Preserve prior calibration outputs; choose a new version explicitly'
    plan=load(ROOT/'analysis_plan.json')
    obs=pd.read_csv(ROOT/'observations/hourly_observations.csv',dtype={'date':str,'route_id':str,'from_stop_id':str,'to_stop_id':str})
    assert set(obs[obs.split=='train'].date)==set(plan['train_dates'])
    assert set(obs[obs.split=='evaluation'].date)==set(plan['evaluation_dates'])
    assert set(plan['train_dates']).isdisjoint(plan['evaluation_dates'])
    hours=plan['primary_hours_inclusive'];obs=obs[obs.hour.between(*hours)].copy()
    assert not obs.duplicated(['date']+LINK_HOUR).any()
    feature=standardized_features(args.features)
    history=(obs[obs.split=='train'].groupby(LINK_HOUR,as_index=False)
             .agg(history_mean=('sum_load','mean'),history_count=('sum_load','count')))
    obs=obs.merge(history,on=LINK_HOUR,how='left',validate='many_to_one')
    result=[];scores=[];coefficients=[];allpred=[];audits=[]
    for operator in OPERATORS:
        f=feature[feature.operator==operator].drop(columns='operator')
        frame=obs.merge(f,on=KEY,how='left',validate='many_to_one')
        frame['model_base']=frame.model_base.fillna(0)  # absent MODEL contribution, never observed null
        train=frame[(frame.split=='train') & frame.campus_origin & frame.sum_load.notna()]
        x=train.model_base.to_numpy(float);y=train.sum_load.to_numpy(float)
        alpha=scale(x,y);by_route={}
        coefficients.append({'operator':operator,'fit_group':'all_routes','alpha':alpha,
                             'training_cells':len(train),'sum_xx':float(x@x),'sum_xy':float(x@y),
                             'scale_identified':bool(x@x>0)})
        for rid,r in train.groupby('route_id',sort=True):
            a=r.model_base.to_numpy(float);b=r.sum_load.to_numpy(float);value=scale(a,b);by_route[rid]=value
            coefficients.append({'operator':operator,'fit_group':rid,'alpha':value,
                                 'training_cells':len(r),'sum_xx':float(a@a),'sum_xy':float(a@b),
                                 'scale_identified':bool(a@a>0)})
        frame['unscaled_class_model']=frame.model_base
        frame['nonnegative_global_scale']=frame.model_base*alpha
        frame['nonnegative_per_route_scale']=frame.model_base*frame.route_id.map(by_route)
        frame['training_segment_hour_mean']=frame.history_mean
        assert frame['nonnegative_per_route_scale'].notna().all()
        # Analytical least-squares normal equations and no-regression of training SSE.
        base_sse=float(((y-x)**2).sum());fit_sse=float(((y-alpha*x)**2).sum())
        assert fit_sse<=base_sse+1e-6
        assert abs(float(x@(y-alpha*x)))<max(1e-5,abs(float(x@y))*1e-12) or alpha==0
        for scope,cells in [('campus_origin_bbox',frame[frame.campus_origin]),('all_route_links',frame)]:
            for split in ('train','evaluation'):
                selected=cells[cells.split==split]
                groups=[('all_routes',selected)] + [(rid,a) for rid,a in selected.groupby('route_id',sort=True)]
                groups += [(date,a) for date,a in selected.groupby('date',sort=True)]
                for group,a in groups:
                    for model in plan['fixed_predictions']:
                        scores.append({'operator':operator,'scope':scope,'split':split,'group':group,'prediction':model,**metrics(a,model)})
        frame['operator']=operator;allpred.append(frame)
        audits.append({'operator':operator,'train_dates_used':sorted(train.date.unique()),
                       'evaluation_dates_used_for_fit':[],'training_base_sse':base_sse,'training_global_fit_sse':fit_sse,
                       'normal_equation_residual':float(x@(y-alpha*x)),
                       'model_zero_observed_cells_retained':True,'background_estimated':False})
    score=pd.DataFrame(scores);coef=pd.DataFrame(coefficients);pred=pd.concat(allpred,ignore_index=True)
    OUT.mkdir()
    coef.to_csv(OUT/'coefficients.csv',index=False,encoding='utf-8-sig')
    score.to_csv(OUT/'metrics.csv',index=False,encoding='utf-8-sig')
    pred.to_csv(OUT/'cell_predictions.csv',index=False,encoding='utf-8-sig')
    selected=score[(score.scope=='campus_origin_bbox') & (score.split=='evaluation') & (score.group=='all_routes')]
    summary={'status':'COMPLETE_EXPLORATORY_SCALE_CALIBRATION','fit_audits':audits,
             'evaluation':selected.where(pd.notna(selected),None).to_dict('records'),
             'scope':'all observed passenger segment sums versus class-only weighted modeled segment flow',
             'provider_hour_semantics_confirmed':False,'background_passengers_modeled':False,
             'student_homebound_rate_estimated':False,'shuttle_queue_validated':False,'per_bus_crowding_validated':False,
             'evaluation_blinded':False,'evaluation_used_to_choose_model':False,
             'features_source':str(args.features.resolve()),'features_sha256':sha(args.features),
             'observations_sha256':sha(ROOT/'observations/hourly_observations.csv'),
             'analysis_plan_sha256':sha(ROOT/'analysis_plan.json'),
             'outputs_sha256':{p.name:sha(p) for p in OUT.glob('*.csv')}}
    dump(OUT/'calibration_receipt.json',summary)
    print(selected[['operator','prediction','valid_cells','MAE','WAPE','RMSE']].to_string(index=False))

if __name__=='__main__':main()
