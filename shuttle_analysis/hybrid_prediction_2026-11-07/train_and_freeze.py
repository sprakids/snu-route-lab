"""Select on development only; freeze parameters and predictions BEFORE test access."""
import sys
sys.dont_write_bytecode=True
from itertools import product
from collections import defaultdict
import numpy as np
import pandas as pd
from common import *

OUT=ROOT/'development'

def history(data):
    valid=data[data.observed.notna()].copy()
    base=valid.groupby(KEY,as_index=False).agg(H=('observed','mean'),C0=('class_flow','mean'),C1=('class_lag1','mean'))
    wh=valid.groupby(['weekday']+KEY,as_index=False).agg(weekday_mean=('observed','mean'),weekday_n=('observed','count'))
    outside=valid[~valid.campus_origin]
    denom=outside.groupby(['route_id','hour'],as_index=False)['observed'].mean().rename(columns={'observed':'outside_mean'})
    bg=outside.groupby(['weekday','route_id','hour'],as_index=False)['observed'].mean().rename(columns={'observed':'outside_weekday_mean'})
    bg=bg.merge(denom,on=['route_id','hour'],validate='many_to_one')
    bg['background_ratio']=np.where(bg.outside_mean>0,bg.outside_weekday_mean/bg.outside_mean,1.)
    return base,wh,bg

def bind(frame,tables):
    base,wh,bg=tables
    x=frame.merge(base,on=KEY,how='left',validate='many_to_one')
    assert x[['H','C0','C1']].notna().all().all(),'No training history for a target key'
    x=x.merge(wh,on=['weekday']+KEY,how='left',validate='many_to_one')
    x=x.merge(bg[['weekday','route_id','hour','background_ratio']],on=['weekday','route_id','hour'],how='left',validate='many_to_one')
    x['background_ratio']=x.background_ratio.fillna(1.)
    x['weekday_mean']=x.weekday_mean.fillna(x.H);x['weekday_n']=x.weekday_n.fillna(0.)
    x['bg']=x.H*(x.background_ratio-1.)
    x['c0']=x.class_flow-x.C0;x['c1']=x.class_lag1-x.C1
    return x

def quadratic_fit(x,y,active,lb,lc):
    """Enumerate all box-constrained active sets in three dimensions."""
    n=len(y);rms2=(x*x).mean(axis=0)
    penalty=np.array([lb,lc,lc])*rms2
    G=x.T@x/n+np.diag(penalty);v=x.T@y/n
    states=[('free','lo','hi') if active[0] else ('lo',),
            ('free','lo') if active[1] else ('lo',),('free','lo') if active[2] else ('lo',)]
    candidates=[]
    for state in product(*states):
        z=np.array([1. if s=='hi' else 0. for s in state]);free=[i for i,s in enumerate(state) if s=='free'];fixed=[i for i in range(3) if i not in free]
        if free:
            A=G[np.ix_(free,free)];b=v[free]-G[np.ix_(free,fixed)]@z[fixed]
            z[free]=np.linalg.lstsq(A,b,rcond=None)[0]
        if np.any(z < -1e-9) or z[0]>1+1e-9:continue
        z=np.maximum(z,0.);z[0]=min(z[0],1.)
        objective=float(z@G@z-2*v@z)
        candidates.append((objective,float(z@z),z))
    assert candidates
    loss,_,z=min(candidates,key=lambda a:(a[0],a[1]))
    grad=G@z-v
    for i in range(3):
        if not active[i]:continue
        tol=max(1e-7,float(np.abs(v).max())*1e-9)
        if z[i]<=1e-8:assert grad[i]>=-tol
        elif i==0 and z[i]>=1-1e-8:assert grad[i]<=tol
        else:assert abs(grad[i])<tol
    return z,{'n':n,'rms2':rms2.tolist(),'objective_without_constant':loss,'gradient':grad.tolist()}

def fit_adjustment(train,kind,lb,lc):
    active={'history_plus_background':(1,0,0),'history_plus_class':(0,1,1),'history_background_class':(1,1,1)}[kind]
    coefs={};checks={}
    for rid,rows in train[train.campus_origin & train.observed.notna()].groupby('route_id'):
        x=rows[['bg','c0','c1']].to_numpy(float);y=(rows.observed-rows.H).to_numpy(float)
        z,check=quadratic_fit(x,y,active,lb,lc)
        coefs[rid]=z.tolist();checks[rid]=check
    return coefs,checks

def predict_bound(frame,kind,params):
    if kind=='history_only':return frame.H.to_numpy()
    if kind=='weekday_history':
        k=params['k'];w=np.where(frame.weekday_n>0,frame.weekday_n/(frame.weekday_n+k),0.)
        return (frame.H+w*(frame.weekday_mean-frame.H)).to_numpy()
    z=np.array([params['coefficients'][r] for r in frame.route_id])
    return np.maximum(0.,frame.H.to_numpy()+np.sum(frame[['bg','c0','c1']].to_numpy()*z,axis=1))

def serial_tables(tables):
    return {name:x.to_dict('records') for name,x in zip(('base','weekday','background'),tables)}

def main():
    assert not OUT.exists(),'Do not overwrite an experiment'
    assert not (ROOT/'selection_frozen.json').exists()
    plan=load(ROOT/'experiment_plan.json')
    train_dates=plan['train_dates'];tune_dates=plan['tuning_dates'];tests=plan['forward_test_dates']+plan['retrospective_test_dates']
    assert set(train_dates).isdisjoint(tune_dates) and set(train_dates+tune_dates).isdisjoint(tests)
    # An explicit access barrier also makes accidental future code paths fail.
    def audit(event,args):
        if event!='open' or not isinstance(args[0],(str,bytes)):return
        p=str(args[0]).replace('\\','/')
        if any('/collected/'+d+'/' in p for d in tests):raise AssertionError('Test target access before freeze is forbidden')
    sys.addaudithook(audit)
    raw,audits=observations(train_dates+tune_dates)
    data=grid(train_dates+tune_dates).merge(raw[['date']+KEY+['observed']],on=['date']+KEY,validate='one_to_one')
    train=data[data.date.isin(train_dates)];tune=data[data.date.isin(tune_dates)]
    tables=history(train);a=bind(train,tables);b=bind(tune,tables)
    OUT.mkdir();dump(OUT/'input_audit.json',audits)
    candidates=[];objects={};candidate_id=0
    for kind in MODELS:
        if kind=='history_only':settings=[{}]
        elif kind=='weekday_history':settings=[{'k':k} for k in (0,1,3,10,1000000)]
        elif kind=='history_plus_background':settings=[{'ridge_background':x,'ridge_class':1.} for x in plan['ridge_background_grid']]
        elif kind=='history_plus_class':settings=[{'ridge_background':1.,'ridge_class':x} for x in plan['ridge_class_grid']]
        else:settings=[{'ridge_background':x,'ridge_class':y} for x,y in product(plan['ridge_background_grid'],plan['ridge_class_grid'])]
        for params in settings:
            candidate_id+=1;params=dict(params);checks={}
            if kind not in ('history_only','weekday_history'):
                params['coefficients'],checks=fit_adjustment(a,kind,params['ridge_background'],params['ridge_class'])
            p=predict_bound(b,kind,params);mask=b.campus_origin
            score=metrics(b.loc[mask,'observed'],p[mask])
            record={'candidate_id':candidate_id,'kind':kind,'ridge_background':params.get('ridge_background'),
                    'ridge_class':params.get('ridge_class'),'k':params.get('k'),**score}
            candidates.append(record);objects[candidate_id]=(params,checks)
    scores=pd.DataFrame(candidates);scores.to_csv(OUT/'tuning_candidates.csv',index=False,encoding='utf-8-sig')
    chosen={};selected_audits={}
    for kind in MODELS:
        rows=[r for r in candidates if r['kind']==kind]
        winner=min(rows,key=lambda r:(r['WAPE'],-(r.get('ridge_background') or 0)-(r.get('ridge_class') or 0),-(r.get('k') or 0)))
        params,check=objects[winner['candidate_id']]
        chosen[kind]={'settings':{k:v for k,v in params.items() if k!='coefficients'},'development_score':winner}
        selected_audits[kind]=check
    # Final fit uses only development dates, never any test measurement.
    final_tables=history(data);final_bound=bind(data,final_tables);refit={};final_checks={}
    for kind,s in chosen.items():
        params=dict(s['settings'])
        if kind not in ('history_only','weekday_history'):
            params['coefficients'],final_checks[kind]=fit_adjustment(final_bound,kind,params['ridge_background'],params['ridge_class'])
        refit[kind]=params
    future=bind(grid(tests),final_tables)
    frozen=future[['date','weekday']+KEY+['campus_origin','H','class_flow','class_lag1','C0','C1','background_ratio','bg','c0','c1']].copy()
    for kind in MODELS:frozen[kind]=predict_bound(future,kind,refit[kind])
    artifact={'schema':'snu_history_class_background_v1','created_utc':now(),'prediction_hours':plan['hours_inclusive'],
              'fit_dates':train_dates+tune_dates,'test_dates_never_fitted':tests,
              'formula':'max(0,H+a*H*(historical_outside_ratio-1)+b*(class-C0)+c*(lagged_class-C1))',
              'models':refit,'tables':serial_tables(final_tables),'class_template':template().to_dict('records'),
              'source_hashes':{'plan':sha(ROOT/'experiment_plan.json'),'class_feature':sha(FEATURE)},
              'background_is_proxy_not_identified_nonstudent_count':True,'provider_semantics_confirmed':False}
    dump(ROOT/'frozen_models.json',artifact)
    frozen.to_csv(ROOT/'frozen_test_predictions.csv',index=False,encoding='utf-8-sig')
    dump(OUT/'selected_settings.json',chosen);dump(OUT/'fit_checks.json',{'selection_fits':selected_audits,'final_fits':final_checks})
    receipt={'status':'FROZEN_BEFORE_TEST_COLLECTION','created_utc':now(),
             'development_dates_used':train_dates+tune_dates,'test_dates_never_loaded':tests,
             'selected':chosen,'frozen_model_sha256':sha(ROOT/'frozen_models.json'),
             'frozen_predictions_sha256':sha(ROOT/'frozen_test_predictions.csv'),
             'plan_sha256':sha(ROOT/'experiment_plan.json'),'training_sources':audits,
             'code_sha256':sha(__file__),'refitted_after_tuning':True,'test_target_accesses':0}
    dump(ROOT/'selection_frozen.json',receipt)
    print(scores.loc[scores.groupby('kind').WAPE.idxmin(),['kind','WAPE','MAE']].to_string(index=False))
    print('MODEL AND SIX-DATE PREDICTIONS FROZEN. Test observations have not been loaded.')

if __name__=='__main__':main()
