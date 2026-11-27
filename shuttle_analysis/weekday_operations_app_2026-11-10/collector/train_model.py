"""Date-held-out evaluation. Writes a candidate; never silently deploys a model.

Inputs: private daily gzip NDJSON exports. No passenger sums become crowd grades.
The first observation in each 10-minute vehicle window is revealed; later
passage observations are used to assess predictions between sparse updates.
"""
import argparse,json,gzip,hashlib,math,sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime,timezone,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from crowd_model import context,distribution,mixed,feature_key,profile_counts
KST=timezone(timedelta(hours=9))
GRADES={'3':0,'4':1,'5':2,'6':3}

def load(files):
    rows=[];days=set();seen=set()
    for file in files:
        raw=gzip.decompress(Path(file).read_bytes()).decode('utf-8')
        for line in raw.splitlines():
            record=json.loads(line)
            if record.get('error'):continue
            days.add(datetime.fromtimestamp(record['at'],KST).date().isoformat())
            for v in record.get('vehicles',[]):
                at=v.get('provided_at');grade=GRADES.get(v.get('crowd_code'));section=str(v.get('section_order',''))
                if not at or grade is None or not section.isdigit() or int(section)<1:continue
                key=(v['route_id'],v['id'],at)
                if key in seen:continue
                seen.add(key);rows.append({'route':v['route_id'],'vehicle':v['id'],'section':section,'at':at,'grade':grade,
                    'day':datetime.fromtimestamp(at,KST).date().isoformat()})
    return sorted(rows,key=lambda x:x['at']),sorted(days)

def passages(rows):
    previous={};seen=set();result=[]
    for r in rows:
        vid=(r['day'],r['route'],r['vehicle']);p=previous.get(vid);section=int(r['section'])
        trip=(p[1] if p else 0)+int(bool(p and section<p[0]-5));previous[vid]=(section,trip)
        key=(*vid,trip,section)
        if key not in seen:seen.add(key);result.append(r)
    return result

def fit(rows):
    cells=defaultdict(lambda:[0]*4);pooled=defaultdict(lambda:[0]*4);features=defaultdict(lambda:[0]*4)
    for r in passages(rows):
        a,b=context(r['route'],r['section'],r['at']);cells[a][r['grade']]+=1;pooled[b][r['grade']]+=1
        features[feature_key(r['route'],r['at'])][r['grade']]+=1
    return dict(cells),dict(pooled),dict(features)

def evaluate(rows,cells,pooled,features,tau):
    revealed={};previous={};errors={'history':[],'persistence':[],'combined':[]};miss={k:[0,0] for k in errors};ages=[];dates=set()
    passage_ids={id(x) for x in passages(rows)}
    for r in rows:
        vid=(r['day'],r['route'],r['vehicle']);window=int(r['at']//600);key=(*vid,window)
        if key not in revealed:revealed[key]=True;previous[vid]=r;continue
        if id(r) not in passage_ids:continue
        prior=previous.get(vid)
        if not prior:continue
        age=r['at']-prior['at']
        if not 0<age<=600:continue
        counts=profile_counts(cells,pooled,features,r['route'],r['section'],r['at'])
        if not counts:continue
        p=distribution(counts);blend=mixed(p,prior['grade'],age,tau)
        predicted={'history':sum(i*x for i,x in enumerate(p)),'persistence':prior['grade'],'combined':sum(i*x for i,x in enumerate(blend))}
        for k,v in predicted.items():
            errors[k].append(abs(v-r['grade']))
            if r['grade']>=2:miss[k][1]+=1;miss[k][0]+=int(v<1.5)
        ages.append(age);dates.add(r['day'])
    return {'n':len(ages),'dates':sorted(dates),'mean_age_seconds':sum(ages)/len(ages) if ages else None,
        'mae':{k:sum(v)/len(v) if v else None for k,v in errors.items()},
        'congested_miss_rate':{k:v[0]/v[1] if v[1] else None for k,v in miss.items()},
        'coverage':len(ages)/max(1,len(passages(rows))),'evaluation_unit':'observed vehicle-section passages; simulated 10-minute missing updates'}

def train(files):
    rows,days=load(files)
    base={'schema':'ordinal_crowd_v1','model_id':'crowd-'+hashlib.sha256(''.join(hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files).encode()).hexdigest()[:12],
        'unit':'ordinal_vehicle_crowd_grade_0_3','validation':{'eligible':False,'reason':'28개 관측 날짜와 충분한 유효 혼잡 등급이 필요합니다.'}}
    if len(days)<28:return base
    days=days[-28:];tr,tu,te=days[:14],days[14:21],days[21:]
    cells,pooled,features=fit([r for r in rows if r['day'] in tr]);tuning=[r for r in rows if r['day'] in tu]
    trials=[(tau,evaluate(tuning,cells,pooled,features,tau)) for tau in (90,180,300,600)]
    tau,tuned=min(trials,key=lambda x:x[1]['mae']['combined'] if x[1]['mae']['combined'] is not None else math.inf)
    # Test dates cannot change cells, tau or promotion rules.
    test=evaluate([r for r in rows if r['day'] in te],cells,pooled,features,tau)
    mae=test['mae'];miss=test['congested_miss_rate'];eligible=(test['n']>=100 and len(test['dates'])>=3 and
        all(mae[k] is not None for k in mae) and mae['combined']<min(mae['history'],mae['persistence']) and
        miss['combined'] is not None and miss['combined']<=min(miss['history'],miss['persistence']))
    return {**base,'cells':cells,'pooled':pooled,'features':features,'feature_interpretation':'historical volume and modeled class inflow buckets calibrated against ordinal labels; no direct unit conversion','tau_seconds':tau,'validation':{'eligible':eligible,'train_dates':tr,'tune_dates':tu,'test_dates':te,
        'tuning':tuned,'test':test,'promotion_rule':'>=100 matched test passages on >=3 days; MAE beats both baselines and congested miss rate worsens against neither',
        'reason':None if eligible else '독립 검증 기준을 충족하지 않아 기존 예측을 유지합니다.'}}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('inputs',nargs='+');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    model=train(a.inputs);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(model,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps({'model_id':model['model_id'],'validation':model['validation']},ensure_ascii=False))
