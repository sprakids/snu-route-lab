"""Read realised vehicle legs, using identical observation definitions in each condition."""
from bisect import bisect_left
from collections import Counter,defaultdict
import csv
from datetime import date
import gzip
import hashlib
from pathlib import Path
from statistics import mean
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
PARENT=ROOT/'261127162719'
LAST=ROOT/'261127164440'
ACC=ROOT/'261125170855/comparison_20261127/accuracy'
sys.path.insert(0,str(ACC))
from score_versions import read,records,write_rows,save_json,DAYS,SERVICES
from check_r_regressions import field_rows,card_observations

PAIR=('120000173','120000174')
UPPER=('300','301','302')
NAK={'120900119','120900110'}
SNU='120000150'
LINE='120900011'
MAIN=('base','stay','access','joint')
FOLLOWUP='joint_soft'


def folder(policy,key):
    return PARENT/'runs/october'/key if policy=='base' else HERE/'runs'/policy/key


def access_outcomes():
    common=read(ROOT/'261125170855/viewer-data/common.json.gz')
    f=folder('joint_soft','peak-thu')
    with gzip.open(f/'inputs.csv.gz','rt',encoding='utf8') as stream:
        picked={int(r['uid']):r['building'] for r in csv.DictReader(stream) if r['new_access']=='1'}
    counts=Counter()
    for trip in read(f/'audit-peak-thu.json.gz')['legs']:
        uid=trip['id']
        if uid not in picked:continue
        ride=next((l for l in trip['legs'] if l[0]==3),None)
        if ride is None:outcome='차량 없이 도착'
        elif common['nodes'][ride[4]].get('stop_id') not in PAIR:outcome='다른 승차지에서 첫 승차'
        elif ride[1]>=21*3600:outcome='두 공학관에서 21시 이후 첫 승차'
        else:outcome='두 공학관에서 17~21시 첫 승차'
        stop=common['nodes'][ride[4]].get('stop_id','') if ride else ''
        counts[picked[uid],outcome,stop]+=trip['weight']
    assert abs(sum(counts.values())-read(f/'treatment.json')['access_changed'])<1e-6
    write_rows(HERE/'목요일_접근선택후_행동.csv',[dict(building=b,outcome=k,stop=s,weight=n) for (b,k,s),n in sorted(counts.items())])


def extract(policy,service,day):
    key=service+'-'+day
    f=folder(policy,key)
    donor=folder('stay',key) if policy=='base' else f
    with gzip.open(donor/'inputs.csv.gz','rt',encoding='utf8',newline='') as stream:
        inputs={int(r['uid']):r for r in csv.DictReader(stream)}
    if policy!='base':
        for r in inputs.values():
            start=float(r['start']);old=float(r['old_start'])
            if start!=old:assert policy in ('stay','joint','joint_soft','joint_wide') and r['building'] in UPPER and 3600<=start-old<=7200
            if r['new_access']=='1':assert r['building'] not in UPPER and 17*3600<=start<21*3600 and r['dest'] in ('snu','nak')
    common=read(ROOT/'261125170855/viewer-data/common.json.gz')
    names,_,campus=card_observations()
    routes=common['city_route_stops']
    audit=read(f/f'audit-{key}.json.gz')
    summary=read(f/'summary.json')
    all_vid={e[2]:e[11] for e in audit['events']}
    events={(e[2],e[1],e[0]):(e[11],e[12],e[6]) for e in audit['events'] if e[11] in routes}
    stops=Counter();od=Counter();tripstats=Counter();by_date=Counter();demand=Counter()
    building=Counter();mass=Counter();boarded=Counter()
    for trip in audit['legs']:
        uid=trip['id'];r=inputs[uid];w=trip['weight'];mass[uid]+=w
        assert abs(trip['start']-float(r['old_start' if policy=='base' else 'start']))<1e-6
        upper=r['building'] in UPPER; depart=int(trip['start']//3600);dest=r['dest']
        rides=[l for l in trip['legs'] if l[0]==3]
        city=[]
        for l in rides:
            _,t,end,_,node,_,vid,*_=l
            if all_vid[vid] not in routes:continue
            rid,i,_=events[vid,node,t];boarded[vid,node,t]+=w
            offsets=common['route_info'][rid]['offsets']
            j=bisect_left(offsets,offsets[i]+end-t-1e-5)
            assert j>i and abs(offsets[j]-offsets[i]-(end-t))<1e-5
            a,b=routes[rid][i]['id'],routes[rid][j]['id'];h=int(t//3600)
            city.append((rid,a,b,h))
            if a in names and b not in campus:stops[a,h]+=w
            if a in PAIR:
                by_date[rid,routes[rid][i]['seq'],a]+=w
                if b==SNU or b in NAK:
                    od[a,h,'snu' if b==SNU else 'nak']+=w
                    if b in NAK and rid==LINE:od[a,h,'line_nak']+=w
        used=any(c[0]==LINE for c in city)
        if upper:
            demand[depart,'upper']+=w
            if dest=='nak':
                demand[depart,'nak']+=w;demand[depart,'nak_line']+=w*used
            if dest=='snu':demand[depart,'snu']+=w
        if city and city[0][1] in PAIR:
            h=city[0][3]
            if 17<=h<21 and any(c[2] in NAK for c in city):tripstats['linked_nak']+=w
            if 17<=h<21 and all_vid[rides[0][6]] in routes:
                building[r['building'],dest]+=w
                if not upper:
                    tripstats['other_first']+=w
                    if policy!='base' and r['new_access']=='1':tripstats['other_changed_first']+=w
        if policy!='base' and float(r['start'])>float(r['old_start']) and 17<=depart<21 and float(r['old_start'])<17*3600:
            tripstats['moved_into_evening']+=w
    assert mass.keys()==inputs.keys()
    assert max(abs(mass[k]-float(inputs[k]['weight'])) for k in mass)<1e-6
    assert max(abs(boarded[k]-e[2]) for k,e in events.items())<1e-5
    def digest(cols):
        return hashlib.sha256(''.join(','.join(inputs[k][c] for c in cols)+'\n' for k in sorted(inputs)).encode()).hexdigest()
    meta=read(f/'treatment.json') if policy!='base' else {}
    signature=digest(('uid','building','dest','weight','old_start'))
    data=dict(model=policy,service=service,day=day,identity=signature,departure=digest(('old_start' if policy=='base' else 'start',)),
              access=digest(('new_access',)),daily=summary['daily'],maxwait=summary['max_continuous_wait'],
              capacity=summary['capacity_violations'],over20=summary['over20_weight'],unserved=summary['unserved'],
              treatment=meta,tripstats=tripstats,od=[[*k,v] for k,v in od.items()],stops=[[*k,v] for k,v in stops.items()],
              dates=[[*k,v] for k,v in by_date.items()],demand=[[*k,v] for k,v in demand.items()],
              buildings=[[*k,v] for k,v in building.items()])
    (HERE/'scores').mkdir(exist_ok=True)
    save_json(HERE/'scores'/f'{policy}_{key}.json',data)


def aggregate():
    def result(v,k):return read(HERE/'scores'/f'{v}_{k}.json')
    names,_,_=card_observations()
    obs=Counter()
    for r in records(ACC.parent/'교내정류장별_5분_승차대조.csv'):
        if r['V12_승차지지원']=='1':obs[r['승차정류장ID'],int(r['시작시각'][:2])]+=int(r['교외하차_카드승객수'])
    observed_od=Counter()
    for r in records(PARENT/'11월5일_두정류장_하차지.csv'):
        a,b,h,n=r['board_id'],r['alight_id'],int(r['hour']),int(r['measured'])
        if b==SNU or b in NAK:
            observed_od[a,h,'snu' if b==SNU else 'nak']+=n
            if b in NAK and r['route_id']==LINE:observed_od[a,h,'line_nak']+=n
    sources=[records(ACC/f) for f in ('queue.csv','departures.csv','personal.csv')]
    dated=[r for r in records(ACC.parent/'일자별_정류장승하차.csv') if r['날짜'] in ('20261102','20261103','20261104','20261106') and
           r['비교상태'].startswith('동일') and r['정류장ID'] in PAIR]
    route_ids={r['name']:r['id'] for r in read(ROOT/'app/data/network.json')['routes']}
    rows=[];supply=[];field=[];station=[];hour_od=[];other_days=[];weekday=[];buildings=[]
    for service in SERVICES:
        for v in (*MAIN,FOLLOWUP):
            rfield=field_rows([PARENT/'runs' if v=='base' else HERE/'runs'],
                              'october' if v=='base' else v,service,*sources)
            field.extend(dict(model=v,**r) for r in rfield)
            checks=[]
            for day in DAYS:
                key=f'{service}-{day}';d=result(v,key);ref=result('base',key)
                assert d['identity']==ref['identity'] and d['daily']==ref['daily']
                assert d['departure']==result('stay' if v in ('joint','stay',FOLLOWUP) else 'base',key)['departure']
                if v!=FOLLOWUP:assert d['access']==result('access' if v in ('access','joint') else 'base',key)['access']
                assert d['capacity']==0 and d['unserved']==0
                supply.append({k:d[k] for k in ('model','service','day','daily','maxwait','capacity','unserved','over20')})
                stats=Counter({(h,k):n for h,k,n in d['demand']})
                weekday.append(dict(model=v,service=service,day=day,**{k:sum(stats[h,k] for h in range(17,21)) for k in ('upper','nak','snu','nak_line')},
                                    **{k:d['treatment'].get(k,0) for k in ('stay_changed','access_800m','access_eligible','access_changed')},
                                    **{k:d['tripstats'].get(k,0) for k in ('other_first','other_changed_first','moved_into_evening')}))
                buildings.extend(dict(model=v,service=service,day=day,building=b,destination=dst,first_board=n) for b,dst,n in d['buildings'])
                actual=Counter({(rid,i,s):n for rid,i,s,n in d['dates']})
                for r in dated:
                    if DAYS[date.fromisoformat(r['날짜']).weekday()]!=day:continue
                    rid=route_ids[r['노선']];stop=r['정류장ID']
                    other_days.append(dict(model=v,service=service,date=r['날짜'],stop=stop,route=r['노선'],
                                           measured=int(r['실측승차']),modeled=actual[rid,int(r['순번']),stop]))
                if day!='thu':continue
                model_stops=Counter({(s,h):n for s,h,n in d['stops']})
                for s in names:
                    for h in range(24):
                        station.append(dict(model=v,service=service,stop=s,name=names[s],hour=h,measured=obs[s,h],modeled=model_stops[s,h]))
                pred=Counter({(s,h,k):n for s,h,k,n in d['od']})
                for s in PAIR:
                    for h in range(24):
                        for k in ('snu','nak','line_nak'):
                            hour_od.append(dict(model=v,service=service,stop=s,hour=h,metric=k,measured=observed_od[s,h,k],modeled=pred[s,h,k]))
                row=dict(service=service,model=v,linked_nak=d['tripstats'].get('linked_nak',0),
                         nak=sum(pred[s,h,'nak'] for s in PAIR for h in range(17,21)),
                         snu=sum(pred[s,h,'snu'] for s in PAIR for h in range(17,21)),line18=pred[PAIR[0],18,'line_nak'],
                         od_cell_mae=mean(abs(pred[s,h,k]-observed_od[s,h,k]) for s in PAIR for h in range(17,21) for k in ('nak','snu')))
                for tag,sites,hours in [('two_afternoon',PAIR,range(15,17)),('two_evening',PAIR,range(17,21)),
                                        ('two_late',PAIR,range(21,23)),('other36',[s for s in names if s not in PAIR],range(17,21)),
                                        ('two_window',PAIR,range(15,23))]:
                    row[tag]=mean(abs(obs[s,h]-model_stops[s,h]) for s in sites for h in hours)
                row['field_mae']=mean(float(r['R오차']) for r in rfield if r['항목']=='바깥줄 분내 MAE')
                checks.append(row)
            for s,col in zip(PAIR,('date2','date1')):
                errors=Counter()
                for r in other_days:
                    if r['model']==v and r['service']==service and r['stop']==s:errors[r['date']]+=r['measured']-r['modeled']
                assert len(errors)==4
                checks[0][col]=mean(map(abs,errors.values()))
            rows.extend(checks)
    no_op=result('control','peak-thu');base=result('base','peak-thu')
    for k in ('daily','identity','departure','access','maxwait','over20','capacity','unserved','od','stops','dates','buildings','demand','tripstats'):
        assert no_op[k]==base[k],k
    previous=records(LAST/'두역방면_동일승하차.csv')
    for r in previous:
        if r['model']!='baseline':continue
        label='snu' if r['gateway']=='서울대입구역2번출구' else 'nak'
        same=next(row for row in hour_od if row['model']=='base' and row['service']==r['service'] and
                  row['stop']==r['board'] and row['hour']==int(r['hour']) and row['metric']==label)
        assert int(r['measured'])==same['measured'] and abs(float(r['modeled'])-same['modeled'])<1e-6
    wide=[]
    for service in SERVICES:
        key=f'{service}-thu'
        for v in ('access_wide','joint_wide','access_soft','joint_soft'):
            d=result(v,key);ref=result('base',key)
            assert d['identity']==ref['identity'] and d['departure']==result('stay' if v.startswith('joint') else 'base',key)['departure']
            assert d['access']==result(v.replace('joint','access'),key)['access'] and d['daily']==ref['daily']
            assert d['capacity']==0 and d['unserved']==0
            pred=Counter({(s,h,k):n for s,h,k,n in d['od']})
            wide.append(dict(model=v,service=service,**d['treatment'],linked=d['tripstats'].get('linked_nak',0),
                             nak=sum(pred[s,h,'nak'] for s in PAIR for h in range(17,21)),
                             snu=sum(pred[s,h,'snu'] for s in PAIR for h in range(17,21)),
                             other_first=d['tripstats'].get('other_first',0),maxwait=d['maxwait'],over20=d['over20']))
    wide_cols=list(dict.fromkeys(k for r in wide for k in r))
    write_rows(HERE/'접근조건_민감도.csv',[{k:r.get(k,0) for k in wide_cols} for r in wide])
    for f,r in [('요일별_수요.csv',weekday),('목요일_38개정류장.csv',station),('목요일_두역방면.csv',hour_od),
                ('다른날_승차.csv',other_days),('현장관측.csv',field),('출발건물별_첫승차.csv',buildings),
                ('운영검산.csv',supply),('조건별_결과.csv',rows)]:
        write_rows(HERE/f,r)
    access_outcomes()
    print(len(supply),'comparison cases; unchanged replay verified')

if __name__=='__main__':
    if len(sys.argv)==4:extract(*sys.argv[1:])
    else:aggregate()
