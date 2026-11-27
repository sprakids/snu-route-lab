"""Read-only shared evidence and metric helpers; no credential or network access."""
from pathlib import Path
from datetime import datetime,timezone
import csv,json,hashlib,math
import pandas as pd

ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'tdata_calibration_2026-11-07'
FEATURE=OLD/'review/segment_model/outputs/baseline_segment_hour.csv'
LINK=['route_id','sta_sn','from_stop_id','to_stop_id']
KEY=LINK+['hour']
ROUTES={'100100250':'5511','100100251':'5513','100100253':'5516','120900011':'관악02-1','120900012':'관악02-2'}
MODELS=('history_only','weekday_history','history_plus_background','history_plus_class','history_background_class')

def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def now():return datetime.now(timezone.utc).isoformat()
def weekday(date):return datetime.strptime(date,'%Y%m%d').weekday()
def key(row):return tuple(str(row[k]) for k in KEY)
def mean(values):return math.fsum(values)/len(values)

def metadata():
    x=pd.read_csv(OLD/'observations/current_links.csv',dtype={'route_id':str,'from_stop_id':str,'to_stop_id':str})
    assert len(x)==259 and x.campus_origin.sum()==125 and not x.duplicated(LINK).any()
    return x

def template():
    x=pd.read_csv(FEATURE,dtype={'route_id':str,'from_stop_id':str,'to_stop_id':str})
    x=x[(x.clock=='segment_entry')].rename(columns={'observed_sta_sn':'sta_sn','expected_trip_events':'class_flow'})
    assert (x.day_offset==0).all(),'New offset requires explicit calendar binding'
    x['weekday']=x.weekday.map({d:i for i,d in enumerate('월화수목금토일')})
    x=x[['weekday']+KEY+['class_flow']]
    assert not x.duplicated(['weekday']+KEY).any()
    assert (x.class_flow>=0).all()
    return x

def grid(dates):
    p=load(ROOT/'experiment_plan.json');lo,hi=p['hours_inclusive']
    links=metadata();t=template()
    hours=pd.DataFrame({'hour':range(lo,hi+1)})
    days=pd.DataFrame({'date':dates,'weekday':[weekday(d) for d in dates]})
    assert (days.weekday<5).all(),'This model covers weekday class endings only'
    x=days.merge(links,how='cross').merge(hours,how='cross')
    x=x.merge(t,on=['weekday']+KEY,how='left',validate='many_to_one')
    lag=t.rename(columns={'class_flow':'class_lag1'}).copy();lag['hour']+=1
    x=x.merge(lag,on=['weekday']+KEY,how='left',validate='many_to_one')
    x[['class_flow','class_lag1']]=x[['class_flow','class_lag1']].fillna(0)
    assert len(x)==len(dates)*259*(hi-lo+1)
    return x

def observations(dates):
    """Strict geometry match and numeric/null preservation, all 24 raw hours."""
    links=metadata();allowed={tuple(str(r[k]) for k in LINK) for r in links.to_dict('records')}
    result=[];audits=[]
    for date in dates:
        source=OLD/'collected'/date/'target_routes.json'
        receipt=load(source.parent/'collection_receipt.json')
        assert receipt['status']=='complete' and receipt['end_proved_by_empty_page']
        assert sha(source)==receipt['target_file_sha256']
        seen=set();daily_errors=0;nonnull=0;zeros=0;rows=load(source)
        for r in rows:
            assert r['stdrDe']==date
            ident=(str(r['routeId']),str(int(r['staSn'])),str(r['fromStaId']),str(r['toStaId']))
            assert ident in allowed and ident not in seen,(date,'Unmatched or repeated historical route geometry',ident)
            seen.add(ident);daily=0.
            for hour in range(24):
                raw=r.get(f'a18SumLoadPsngNum{hour:02d}h')
                value=None if raw is None else float(raw)
                assert value is None or (math.isfinite(value) and value>=0)
                if value is not None:daily+=value;nonnull+=1;zeros+=int(value==0)
                result.append({'date':date,'weekday':weekday(date),**dict(zip(LINK,ident)),'hour':hour,'observed':value})
            total=r.get('a18SumLoadPsng')
            daily_errors+=int(total is not None and abs(float(total)-daily)>1e-8)
        assert seen==allowed,'Changed historical route must not be silently imputed'
        audits.append({'date':date,'rows':len(rows),'matched_links':len(seen),'non_null_cells':nonnull,
                       'observed_zero_cells':zeros,'daily_sum_mismatches':daily_errors,'sha256':sha(source)})
        assert daily_errors==0
    frame=pd.DataFrame(result);frame['sta_sn']=frame.sta_sn.astype(int)
    assert not frame.duplicated(['date']+KEY).any()
    return frame,audits

def metrics(y,p):
    pairs=[(float(a),float(b)) for a,b in zip(y,p) if not pd.isna(a)]
    assert pairs and all(math.isfinite(b) and b>=0 for a,b in pairs)
    total=math.fsum(a for a,b in pairs);absolute=math.fsum(abs(a-b) for a,b in pairs)
    return {'valid_cells':len(pairs),'observed_sum':total,'predicted_sum':math.fsum(b for a,b in pairs),
            'MAE':absolute/len(pairs),'WAPE':absolute/total if total else None,
            'RMSE':math.sqrt(math.fsum((a-b)**2 for a,b in pairs)/len(pairs))}
