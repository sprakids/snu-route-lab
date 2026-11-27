from array import array
from bisect import bisect_left
from collections import Counter,defaultdict
from datetime import date
import hashlib
from math import hypot,cos,radians
from pathlib import Path
from statistics import mean
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
PARENT=ROOT/'261127162719'
V12=ROOT/'261125170855'
ACC=V12/'comparison_20261127/accuracy'
sys.path.insert(0,str(ACC))
from score_versions import read,records,write_rows,save_json,DAYS,SERVICES
from check_r_regressions import card_observations,field_rows

G='120900011'
TARGET='120000173'
NEAR='120000174'
ENDS={'120900119','120900110'}
PRIMARY=('baseline','station','route','both')
EXTRA=('alternative','station_alternative')

def folder(v,key):
    return PARENT/'runs/october'/key if v=='baseline' else HERE/'runs'/v/key


def extract(v,service,day):
    key=service+'-'+day
    f=folder(v,key)
    meta=folder('route',key) if v=='baseline' else f
    cohorts={int(r['uid']):r for r in records(meta/'evening_cohorts.csv')}
    destcol='dest_before' if v=='baseline' else 'dest_after'
    common=read(V12/'viewer-data/common.json.gz')
    names,_,campus=card_observations()
    a=read(f/f'audit-{key}.json.gz');summary=read(f/'summary.json')
    routes=common['city_route_stops']
    vehicles={e[2]:e[11] for e in a['events']}
    events={(e[2],e[1],e[0]):(e[11],e[12],e[6]) for e in a['events'] if e[11] in routes}
    mass=Counter(); starts={}; follow=defaultdict(Counter)
    paired=defaultdict(Counter); stop_counts=Counter(); line_counts=Counter()
    daily=Counter(); boarded=Counter(); max_endpoint=0.
    for trip in a['legs']:
        uid=trip['id'];w=trip['weight'];mass[uid]+=w
        assert starts.setdefault(uid,trip['start'])==trip['start']
        rides=[leg for leg in trip['legs'] if leg[0]==3]
        city=[]
        for leg in rides:
            _,t,end,_,node,_,vehicle,*_=leg
            if vehicles[vehicle] not in routes:continue
            rid,i,_=events[vehicle,node,t]
            boarded[vehicle,node,t]+=w
            off=common['route_info'][rid]['offsets'];j=bisect_left(off,off[i]+end-t-1e-5)
            assert j>i and abs(off[j]-off[i]-(end-t))<1e-5
            start,finish=routes[rid][i]['id'],routes[rid][j]['id']
            h=int(t//3600);city.append((rid,start,finish,h,t))
            if 0<=h<24 and start in (TARGET,NEAR):daily[rid,routes[rid][i]['seq'],start]+=w
            if day=='thu' and 15<=h<21 and start in names and finish not in campus:
                stop_counts[start,h]+=w
                if rid==G and start in (TARGET,NEAR):
                    line_counts[start,h,'outside']+=w
                    if finish in ENDS:line_counts[start,h,'station']+=w
        if day=='thu' and city and city[0][1] in (TARGET,NEAR) and 17<=city[0][3]<21:
            _,stop,_,h,_=city[0];z=paired[h,stop]
            z['first_paid_journeys']+=w
            for k,(_,_,finish,_,_) in enumerate(city):
                if finish in ENDS:
                    z['bus_alight']+=w
                    z['bus_alight_used_line']+=w*any(s[0]==G for s in city[:k+1])
                    z['bus_alight_first_line']+=w*(city[0][0]==G)
                    break
        if uid not in cohorts:continue
        row=cohorts[uid];h=int(trip['start']//3600)
        assert 17<=h<21 and abs(trip['start']-float(row['start']))<1e-6
        z=follow[h];z['upper']+=w
        if row[destcol]!='nak':continue
        z['nak']+=w
        last=common['paths'][trip['legs'][-1][3]][-1];marker=common['destinations']['nak']
        distance=111320*hypot(last[0]-marker[0],(last[1]-marker[1])*cos(radians(marker[0])))
        max_endpoint=max(max_endpoint,distance)
        z['arrived_within_50m']+=w*(distance<=50 and not trip['unserved'])
        line_used=any(c[0]==G for c in city)
        z['any_line']+=w*line_used
        first=bool(rides and vehicles[rides[0][6]]==G)
        z['first_line']+=w*first
        z['single_line']+=w*(first and len(rides)==1)
        z['toward_station_on_line']+=w*any(c[0]==G and c[2] in ENDS for c in city)
        z['planned_line']+=w*int(row['uses_before' if v=='baseline' else 'uses_after'])
        z['planned_direct']+=w*int(row['direct_before' if v=='baseline' else 'direct_after'])
    assert max(abs(boarded[k]-e[2]) for k,e in events.items())<1e-5
    assert all(abs(float(r['weight'])-mass[uid])<1e-6 for uid,r in cohorts.items())
    assert abs(sum(mass.values())-summary['daily'])<1e-5
    cohort_keys=sorted(cohorts)
    digest=hashlib.sha256(''.join(f'{uid},{starts[uid]:.9f}\n' for uid in sorted(starts)).encode()).hexdigest()
    desthash=hashlib.sha256(''.join(f'{uid},{cohorts[uid][destcol]}\n' for uid in cohort_keys).encode()).hexdigest()
    out=HERE/'scores';out.mkdir(exist_ok=True)
    (out/f'{v}_{key}.weights').write_bytes(array('d',(mass[k] for k in sorted(mass))).tobytes())
    save_json(out/f'{v}_{key}.json',dict(start_id=digest,destination_hash=desthash,max_endpoint_m=max_endpoint,
        daily=summary['daily'],over20=summary['over20_weight'],unserved=summary['unserved'],capacity=summary['capacity_violations'],
        maxwait=summary['max_continuous_wait'],cohorts={str(h):dict(z) for h,z in follow.items()},
        stops=[[s,h,stop_counts[s,h]] for s in names for h in range(15,21)] if day=='thu' else [],
        line=[[s,h,k,line_counts[s,h,k]] for s in (TARGET,NEAR) for h in range(15,21) for k in ('outside','station')] if day=='thu' else [],
        actual_days=[[rid,i,s,n] for (rid,i,s),n in daily.items()],
        linked=[[h,s,dict(z)] for (h,s),z in paired.items()]))


def aggregate(extra=EXTRA):
    names,_,_=card_observations()
    obs=Counter()
    for r in records(ACC.parent/'교내정류장별_5분_승차대조.csv'):
        if r['V12_승차지지원']=='1':
            obs[r['승차정류장ID'],int(r['시작시각'][:2])]+=int(r['교외하차_카드승객수'])
    matched=Counter()
    for r in records(PARENT/'11월5일_두정류장_하차지.csv'):
        if r['zone']=='outside' and r['route_id']==G:
            s=r['board_id'];h=int(r['hour']);n=int(r['measured'])
            matched[s,h,'outside']+=n
            if r['alight_id'] in ENDS:matched[s,h,'station']+=n
    linked_obs={(int(r['first_board_hour']),r['first_board_stop'],r['metric']):int(r['passengers']) for r in records(HERE/'11월5일_카드연결_시간별.csv')}
    date_rows=[r for r in records(ACC.parent/'일자별_정류장승하차.csv') if r['비교상태'].startswith('동일') and
               r['날짜'] in ('20261102','20261103','20261104','20261106') and r['정류장ID'] in (TARGET,NEAR)]
    ids={r['name']:r['id'] for r in read(ROOT/'app/data/network.json')['routes']}
    sources=[records(ACC/f) for f in ('queue.csv','departures.csv','personal.csv')]
    field=[]; scored=[]; cohorts=[]; stops=[]; lines=[]; safety=[]; dates=[]; links=[]
    keys=('upper','nak','planned_line','planned_direct','any_line','first_line','single_line','toward_station_on_line','arrived_within_50m')
    for service in SERVICES:
        for v in PRIMARY+extra:
            if v in PRIMARY:
                variant='october' if v=='baseline' else v
                rfield=field_rows([(PARENT if v=='baseline' else HERE)/'runs'],variant,service,*sources)
                for r in rfield:r['연구조건']=v
                field.extend(rfield)
            for day in (('thu',) if v in extra else DAYS):
                key=f'{service}-{day}'
                def file(k):return HERE/'scores'/f'{k}_{key}.json'
                d=read(file(v));ref=read(file('baseline'))
                assert d['start_id']==ref['start_id'] and d['daily']==ref['daily']
                assert d['max_endpoint_m']<50
                assert all(abs(z.get('nak',0)-z.get('arrived_within_50m',0))<1e-6 for z in d['cohorts'].values())
                if day=='thu':
                    assert [z for z in d['stops'] if z[1]<17]==[z for z in ref['stops'] if z[1]<17]
                weights=[array('d',f.with_suffix('.weights').read_bytes()) for f in (file(v),file('baseline'))]
                assert len(weights[0])==len(weights[1]) and max(abs(a-b) for a,b in zip(*weights))<1e-6
                intended='station' if v in ('station','both','station_alternative','station_law') else 'baseline'
                assert d['destination_hash']==read(file(intended))['destination_hash']
                safety.append(dict(service=service,model=v,day=day,**{k:d[k] for k in ('daily','over20','capacity','unserved','maxwait','max_endpoint_m')}))
                for h in range(17,21):
                    z=d['cohorts'].get(str(h),{})
                    cohorts.append(dict(service=service,model=v,day=day,hour=h,**{k:z.get(k,0.) for k in keys}))
                modelday={(rid,i,s):n for rid,i,s,n in d['actual_days']}
                for r in date_rows:
                    if DAYS[date.fromisoformat(r['날짜']).weekday()]!=day:continue
                    rid=ids[r['노선']];s=r['정류장ID'];i=int(r['순번'])
                    dates.append(dict(service=service,model=v,date=r['날짜'],stop_id=s,route=r['노선'],seq=i,
                                      measured=int(r['실측승차']),modeled=modelday.get((rid,i,s),0.)))
                if day!='thu':continue
                for s,h,m in d['stops']:
                    stops.append(dict(service=service,model=v,stop_id=s,stop=names[s],hour=h,measured=obs[s,h],modeled=m))
                for s,h,k,m in d['line']:
                    lines.append(dict(service=service,model=v,stop_id=s,hour=h,metric=k,measured=matched[s,h,k],modeled=m))
                flow={(h,s,k):n for h,s,z in d['linked'] for k,n in z.items()}
                for (h,s,k),y in linked_obs.items():
                    if k in ('first_paid_journeys','bus_alight','bus_alight_used_line','bus_alight_first_line'):
                        links.append(dict(service=service,model=v,hour=h,first_stop=s,metric=k,measured=y,modeled=flow.get((h,s,k),0.)))
            selected=[r for r in cohorts if r['service']==service and r['model']==v and r['day']=='thu']
            total={k:sum(r[k] for r in selected) for k in keys}
            def subset(rows,**kw):
                return [r for r in rows if r['model']==v and r['service']==service and all(r[k]==x for k,x in kw.items())]
            def mae(rows):return mean(abs(r['measured']-r['modeled']) for r in rows)
            def evening(rows):return [r for r in rows if r['hour']>=17]
            us=evening(subset(stops,stop_id=TARGET)); near=evening(subset(stops,stop_id=NEAR))
            g=evening(subset(lines,stop_id=TARGET,metric='station'))
            other=[r for r in evening(subset(stops)) if r['stop_id'] not in (TARGET,NEAR)]
            checks=dict(route_station_mae=mae(g),target_mae=mae(us),near_mae=mae(near),other36_mae=mae(other),
                        campus_mae=mae(evening(subset(stops))),g_station_hours=[r['modeled'] for r in g],
                        observed_g_station=[r['measured'] for r in g],all_out_hours=[r['modeled'] for r in us])
            if v in PRIMARY:
                for what,subset_dates in [('line_other_days',[r for r in subset(dates,stop_id=TARGET,route='관악02-1')]),
                                          ('all_other_days',subset(dates,stop_id=TARGET))]:
                    daily=defaultdict(lambda:[0.,0.])
                    for r in subset_dates:
                        daily[r['date']][0]+=r['measured'];daily[r['date']][1]+=r['modeled']
                    assert len(daily)==4
                    checks[what]=mean(abs(y-m) for y,m in daily.values())
                checks['queue_mae']=mean(float(r['R오차']) for r in field if r['연구조건']==v and r['배차']==service and r['항목']=='바깥줄 분내 MAE')
            scored.append(dict(service=service,model=v,**total,**checks))
    for name,rows in [('요일_출발시간별.csv',cohorts),('목요일_정류장별.csv',stops),('목요일_관악02-1.csv',lines),('카드연결_동일기준대조.csv',links),
                      ('별도4일_검증.csv',dates),('현장관측.csv',field),('운영검산.csv',safety)]:
        write_rows(HERE/name,rows)
    save_json(HERE/'results.json',scored)
    assert len(safety)==40+2*len(extra) and all(r['capacity']==0 and r['unserved']==0 for r in safety)
    # The newly reconstructed control has exactly the behavior of the archived research baseline.
    for service in ('peak',):
        d=read(HERE/'scores'/f'control_{service}-thu.json')
        ref=read(HERE/'scores'/f'baseline_{service}-thu.json')
        assert d==ref


if __name__=='__main__':
    if len(sys.argv)==4:extract(*sys.argv[1:])
    elif sys.argv[1:]==['--law']:aggregate((*EXTRA,'law_transfer','station_law'))
    else:aggregate()
