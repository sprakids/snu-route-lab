"""Ordinal crowd-label profiles. Hourly passenger sums are never target labels."""
import json,math
from pathlib import Path
from datetime import datetime,timezone,timedelta
KST=timezone(timedelta(hours=9))
FEATURE_PATH=Path(__file__).parent/'data/demand_features.json'
FEATURES=json.loads(FEATURE_PATH.read_text(encoding='utf-8')) if FEATURE_PATH.exists() else {}

def feature_key(route,at):
    d=datetime.fromtimestamp(at,KST);minute=(d.hour*60+d.minute)//5*5
    f=FEATURES.get(str(d.weekday()),{}).get(str(minute),{}).get(route,{})
    term='2026-09-01'<=d.date().isoformat()<='2026-12-21' and d.date().isoformat() not in ('2026-09-24','2026-09-25','2026-10-05','2026-10-09','2026-10-15')
    return f"{route}:{min(4,int(f.get('history',0)*5))}:{min(2,int(f.get('classes',0)*3)) if term else 0}"

def profile_counts(cells,pooled,features,route,section,at):
    a,b=context(route,section,at)
    for counts,minimum in [(cells.get(a),10),(pooled.get(b),20),(features.get(feature_key(route,at)),50)]:
        if counts and sum(counts)>=minimum:return counts
    return None

def context(route,section,at):
    d=datetime.fromtimestamp(at,KST)
    return f'{route}:{section}:{d.weekday()}:{(d.hour*60+d.minute)//15}',f'{route}:{d.weekday()}:{d.hour}'

def distribution(counts):
    total=sum(counts)+4
    return [(n+1)/total for n in counts]

def mixed(prob,last,age,tau):
    weight=math.exp(-max(0,age)/tau) if last is not None and age is not None and age<=600 else 0
    return [(1-weight)*p+weight*int(i==last) for i,p in enumerate(prob)]

class CrowdModel:
    def __init__(self,path=None):
        p=Path(path) if path else Path(__file__).parent/'data/crowd_model.json'
        self.data=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
        self.active=self.data.get('schema')=='ordinal_crowd_v1' and self.data.get('validation',{}).get('eligible') is True
    def predict(self,route,section,at,last=None,age=None):
        if not self.active:return None
        counts=profile_counts(self.data.get('cells',{}),self.data.get('pooled',{}),self.data.get('features',{}),route,section,at)
        if not counts:return None
        p=mixed(distribution(counts),last,age,self.data['tau_seconds'])
        mean=sum(i*x for i,x in enumerate(p));sd=math.sqrt(sum((i-mean)**2*x for i,x in enumerate(p)))
        return {'crowd_cost':None,'crowd_estimate':round(mean,3),'crowd_risk':min(3,mean+.5*sd),
            'crowd_uncertainty':.5*sd,'crowd_source':'calibrated_history',
            'crowd_label':f'{mean:.1f}/3 추정','model_version':self.data['model_id'],
            'age_seconds':round(age) if age is not None else None,'observed_at':at-age if age is not None else None,
            'training_passages':sum(counts),'prediction_spread_kind':'ordinal_category_spread_not_confidence_interval'}
