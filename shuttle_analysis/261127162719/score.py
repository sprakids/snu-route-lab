"""Score the actual vehicle ledgers against independent stop, route and alighting counts."""
from bisect import bisect_left
from collections import Counter,defaultdict
from datetime import date
import hashlib
from pathlib import Path
from statistics import mean
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
V12=ROOT/'261125170855'
OLD=ROOT/'261127160713'
ACC=V12/'comparison_20261127/accuracy'
sys.path.insert(0,str(ACC))
from check_r_regressions import card_observations,field_rows
from score_versions import read,records,write_rows,save_json,DAYS,SERVICES

TARGET='120000173'; NEAR='120000174'; G='120900011'
POLICIES=('V12','previous','adjacent','direct','october')
HOURS=range(15,19)
def loc(v,key):
    if v=='V12':return V12/'runs/candidate'/key
    old=OLD/'runs/choice'/key
    if v=='previous' and (old/'summary.json').exists():return old
    return HERE/'runs'/v/key

def extract(v,service,day):
    key=service+'-'+day
    folder=loc(v,key)
    common=read(V12/'viewer-data/common.json.gz')
    names,_,campus=card_observations()
    a=read(folder/f'audit-{key}.json.gz')
    summary=read(folder/'summary.json')
    routes=common['city_route_stops']
    pair={rid:[i,i+1] for rid,rr in routes.items() for i in range(len(rr)-1)
          if [s['id'] for s in rr[i:i+2]]==[TARGET,NEAR]}
    pair_day=Counter(); pair_hour=Counter(); events={}
    for e in a['events']:
        rid,i=e[11:13]
        if rid not in routes:continue
        if rid in pair and i in pair[rid] and 0<=e[0]<86400:
            flag=routes[rid][i]['id']
            pair_day[rid,flag]+=e[6]
            pair_hour[rid,flag,int(e[0]//3600)]+=e[6]
        if day=='thu' and int(e[0]//3600) in HOURS:
            events[e[2],e[1],e[0]]=(rid,i,e[6])
    od=Counter(); route_od=Counter(); observed_board=Counter()
    mass=Counter(); clocks={}
    for trip in a['legs']:
        w=trip['weight']; uid=trip['id']
        mass[uid]+=w
        assert clocks.setdefault(uid,trip['start'])==trip['start']
        if day!='thu':continue
        for leg in trip['legs']:
            if leg[0]!=3:continue
            _,t,end,_,node,_,vehicle,*_=leg
            evt=events.get((vehicle,node,t))
            if evt is None:continue
            rid,i,_=evt; offsets=common['route_info'][rid]['offsets']
            j=bisect_left(offsets,offsets[i]+end-t-1e-5)
            assert j>i and abs(offsets[j]-offsets[i]-(end-t))<1e-5
            observed_board[vehicle,node,t]+=w
            start,finish=routes[rid][i]['id'],routes[rid][j]['id']
            h=int(t//3600)
            if start in names and finish not in campus:
                od[start,h]+=w
                if start==TARGET:
                    route_od[rid,h,'outside']+=w
                    if finish in ('120900119','120900110'):
                        route_od[rid,h,'station_or_entry']+=w
    assert all(abs(observed_board[k]-e[2])<1e-5 for k,e in events.items())
    assert abs(sum(mass.values())-summary['daily'])<1e-5
    start_id=hashlib.sha256(''.join(f'{uid},{clocks[uid]:.9f}\n' for uid in sorted(clocks)).encode()).hexdigest()
    # Decimal rounding can straddle an exact half during capacity splits; compare each weight numerically later.
    path=HERE/'scores'/f'{v}_{key}.json'
    path.parent.mkdir(exist_ok=True)
    weight_file=path.with_suffix('.weights')
    from array import array
    weight_file.write_bytes(array('d',(mass[k] for k in sorted(mass))).tobytes())
    result=dict(start_id=start_id,daily=summary['daily'],capacity=summary['capacity_violations'],
                over20=summary['over20_weight'],unserved=summary['unserved'],maxwait=summary['max_continuous_wait'],
                upper=summary.get('upper_actual',summary.get('upper_actual_v12',{})),
                pair_day=[[r,s,pair_day[r,s]] for r in pair for s in (TARGET,NEAR)],
                pair_hour=[[r,s,h,pair_hour[r,s,h]] for r in pair for s in (TARGET,NEAR) for h in HOURS],
                stops=[[s,h,od[s,h]] for s in names for h in HOURS] if day=='thu' else [],
                route_od=[[r,h,k,route_od[r,h,k]] for r in pair for h in HOURS for k in ('outside','station_or_entry')] if day=='thu' else [])
    save_json(path,result)


def aggregate(policies=POLICIES):
    from array import array
    names,obs,_=card_observations()
    raw=records(HERE/'11월5일_두정류장_하차지.csv')
    od=Counter(); hour_all=Counter()
    for r in raw:
        rid,h,s=r['route_id'],int(r['hour']),r['board_id']; n=int(r['measured'])
        hour_all[rid,s,h]+=n
        if s==TARGET and r['zone']=='outside':
            od[rid,h,'outside']+=n
            if r['alight_id'] in ('120900110','120900119'):od[rid,h,'station_or_entry']+=n
    actual=defaultdict(Counter)
    network=read(ROOT/'app/data/network.json')['routes']
    ids={r['name']:r['id'] for r in network}
    ids_to_name={v:k for k,v in ids.items()}
    routes=read(V12/'viewer-data/common.json.gz')['city_route_stops']
    seq={(rid,s['id'],s['seq']) for rid,rr in routes.items() for i in range(len(rr)-1)
         if (rr[i]['id'],rr[i+1]['id'])==(TARGET,NEAR) for s in rr[i:i+2]}
    for r in records(ACC.parent/'일자별_정류장승하차.csv'):
        rid,s=ids[r['노선']],r['정류장ID']
        if (rid,s,int(r['순번'])) in seq and r['비교상태'].startswith('동일'):
            actual[r['날짜']][rid,s]+=int(r['실측승차'])
    assert len(actual)==18 and all(len(row)==8 for row in actual.values())
    src=[records(ACC/f) for f in ['queue.csv','departures.csv','personal.csv']]
    field=[]; stops=[]; routerows=[]; dates=[]; checks=[]; scores=[]
    for service in SERVICES:
        for v in policies[1:]:
            old=v=='previous' and service=='peak'
            variant='choice' if old else v
            rows=field_rows([(OLD if old else HERE)/'runs'],variant,service,*src)
            for r in rows:r['연구조건']=v
            field.extend(rows)
        for v in policies:
            for day in DAYS:
                name=f'{service}-{day}'
                prefix=HERE/'scores'
                f=prefix/f'{v}_{name}.json'; base=prefix/f'V12_{name}.json'
                d=read(f); ref=read(base)
                assert d['start_id']==ref['start_id'] and d['daily']==ref['daily']
                w,b=[array('d',x.with_suffix('.weights').read_bytes()) for x in (f,base)]
                assert len(w)==len(b) and max(abs(x-y) for x,y in zip(w,b))<1e-6
                checks.append(dict(service=service,day=day,model=v,**{k:d[k] for k in ('daily','capacity','unserved','over20','maxwait')}))
                by={(r,s):z for r,s,z in d['pair_day']}
                for date_key,y in actual.items():
                    if DAYS[date.fromisoformat(date_key).weekday()]!=day:continue
                    for (rid,s),m in by.items():
                        dates.append(dict(service=service,model=v,date=date_key,route=ids_to_name[rid],stop=s,observed=y[rid,s],modeled=m))
                if day!='thu':continue
                predicted={(s,h):z for s,h,z in d['stops']}
                for s,h,z in d['stops']:
                    stops.append(dict(service=service,model=v,stop=names[s],stop_id=s,hour=h,observed=obs[s,h],modeled=z))
                for r,h,k,z in d['route_od']:
                    routerows.append(dict(service=service,model=v,route=ids_to_name[r],stop=TARGET,hour=h,metric=k,observed=od[r,h,k],modeled=z))
                for r,s,h,z in d['pair_hour']:
                    # 5511 serves the same downstream stop twice. The OD cards have no sequence.
                    if ids_to_name[r]=='5511' and s==NEAR:continue
                    routerows.append(dict(service=service,model=v,route=ids_to_name[r],stop=s,hour=h,metric='all',observed=hour_all[r,s,h],modeled=z))
                assert all(abs(sum(m for r,hh,k,m in d['route_od'] if hh==h and k=='outside')-predicted[TARGET,h])<1e-5 for h in HOURS)
                guard=[r for r in field if r['배차']==service and r['연구조건']==('previous' if v=='V12' else v) and r['항목']=='바깥줄 분내 MAE']
                assert len(guard)==7
                vals=[m for r,h,k,m in d['route_od'] if r==G and k=='outside']
                pair_ob=[sum(hour_all[G,s,h] for h in HOURS) for s in (TARGET,NEAR)]
                pair_mod=[sum(m for r,st,h,m in d['pair_hour'] if r==G and st==s) for s in (TARGET,NEAR)]
                scores.append(dict(service=service,model=v,obs_hours=[obs[TARGET,h] for h in HOURS],
                    hours=[predicted[TARGET,h] for h in HOURS],gwanak02_out_hours=vals, gwanak02_out_4h=sum(vals),
                    gwanak02_observed_share=100*pair_ob[0]/sum(pair_ob),gwanak02_modeled_share=100*pair_mod[0]/sum(pair_mod),
                    gwanak02_pair=pair_mod,gwanak02_obs_pair=pair_ob,
                    target_mae=mean(abs(predicted[TARGET,h]-obs[TARGET,h]) for h in HOURS),
                    near_mae=mean(abs(predicted[NEAR,h]-obs[NEAR,h]) for h in HOURS),
                    campus_mae=mean(abs(predicted[s,h]-obs[s,h]) for s in names for h in HOURS),
                    queue_mae=mean(float(r['V12오차' if v=='V12' else 'R오차']) for r in guard)))
    for score in scores:
        dy=defaultdict(lambda:[0.,0.])
        shares=defaultdict(dict)
        for row in dates:
            if (row['service'],row['model'])!=(score['service'],score['model']):continue
            if row['date']<'20261101' or row['date']=='20261105':continue
            if row['stop']==TARGET:
                cell=dy[row['date']];cell[0]+=row['observed'];cell[1]+=row['modeled']
            if row['route']=='관악02-1':
                shares[row['date']][row['stop']]=(row['observed'],row['modeled'])
        assert len(dy)==4
        score['other_november_mae']=mean(abs(y-m) for y,m in dy.values())
        assert len(shares)==4
        diffs=[]
        for pair in shares.values():
            first,second=pair[TARGET],pair[NEAR]
            y,m=(100*a/(a+b) for a,b in zip(first,second))
            diffs.append(abs(m-y))
        score['other_november_route_share_mae_pp']=mean(diffs)
    for name,rows in [('목요일_승차지.csv',stops),('목요일_노선과하차지.csv',routerows),('일별_두정류장.csv',dates),('현장관측.csv',field),('운영검산.csv',checks)]:
        write_rows(HERE/name,rows)
    save_json(HERE/'result.json',scores)


if __name__=='__main__':
    if len(sys.argv)==4:
        extract(*sys.argv[1:])
    elif '--include-local' in sys.argv:
        aggregate((*POLICIES,'october02'))
    else:
        aggregate()
