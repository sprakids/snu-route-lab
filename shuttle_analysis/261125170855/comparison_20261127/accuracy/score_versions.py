"""Score the saved V10, V11 and V12 runs against the same observations."""
from bisect import bisect_left
from collections import Counter, defaultdict
import csv
from datetime import date
import math
from pathlib import Path
from statistics import mean
import sys

OUT = Path(__file__).resolve().parent
OBS = OUT.parent
V12 = OBS.parent
ROOT = V12.parent
SIM = ROOT / 'simulation_viewer_2026-11-07'
sys.path.insert(0, str(ROOT/'261124160531/report'))
from compare import Curve, field_records, read, riders, seconds, save_json

VERSIONS = {'V10': SIM/'capacity44_correction_2026-11-10',
            'V11': SIM/'peak_pair_correction_2026-11-10', 'V12': V12}
DAYS = ('mon','tue','wed','thu','fri')
SERVICES = ('regular','peak')


def records(path):
    with path.open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))


def write_rows(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def queue_row(curve, start, lo, hi):
    """Integrate over one observation minute using the time spent at each queue size."""
    end = start + 60
    stats = curve.stats(start, end, (lo, hi))
    changes = [t for t in curve.times if start < t < end]
    boundaries = [start, *changes, end]
    intervals = []
    for left, right in zip(boundaries, boundaries[1:]):
        count = curve.at(left)
        error = max(lo - count, count - hi, 0)
        intervals.append(((right - left) / 60, error))
    assert math.isclose(sum(w * e for w, e in intervals), stats['expected_abs_error'], abs_tol=1e-8)
    return {
        **stats,
        'expected_squared_error': sum(w * e**2 for w, e in intervals),
        'within_5': sum(w for w, e in intervals if e <= 5),
        'within_10': sum(w for w, e in intervals if e <= 10),
    }


def queue_score(rows):
    return {
        'n': len(rows),
        'mae': mean(r['expected_abs_error'] for r in rows),
        'rmse': math.sqrt(mean(r['expected_squared_error'] for r in rows)),
        'within_5_pct': 100 * mean(r['within_5'] for r in rows),
        'within_10_pct': 100 * mean(r['within_10'] for r in rows),
    }


def measures(pairs):
    errors = [predicted - observed for predicted, observed in pairs]
    return {
        'n': len(errors),
        'mae': mean(abs(e) for e in errors),
        'rmse': math.sqrt(mean(e**2 for e in errors)),
        'bias': mean(errors),
        'observed_sum': sum(observed for _, observed in pairs),
        'model_sum': sum(predicted for predicted, _ in pairs),
    }


def transit(audit,common,core,bounds):
    routes=common['city_route_stops']; info=common['route_info']
    events={(e[2],e[1],e[0]):(e[11],e[12],e[6]) for e in audit['events'] if e[11] in routes}
    check=Counter(); boards=Counter(); off=Counter();loads=Counter();od=Counter()
    for trip in audit['legs']:
        weight=trip['weight']
        for mode,start,end,path,n,_,v,*_ in trip['legs']:
            if mode!=3 or not common['nodes'][n].get('city'):continue
            rid,i,_=events[v,n,start]; times=info[rid]['offsets']; stops=routes[rid]
            j=bisect_left(times,times[i]+end-start-1e-5)
            assert i<j<len(times) and abs((times[j]-times[i])-(end-start))<1e-5
            check[v,n,start]+=weight
            src,dst=stops[i],stops[j]
            if 0<=start<86400:boards[rid,src['seq'],src['id']]+=weight
            if 0<=end<86400:off[rid,dst['seq'],dst['id']]+=weight
            if src['id'] in core and dst['id'] not in bounds:
                od[src['id'],int(start//3600)]+=weight
            for k in range(i,j):
                h=int((start+(times[k]-times[i]))//3600)
                loads[rid,stops[k]['seq'],stops[k]['id'],stops[k+1]['id'],h]+=weight
    assert all(abs(check[k]-v[2])<1e-5 for k,v in events.items())
    return boards,off,loads,od


def compare():
    field=field_records()
    actual=Counter()
    for r in records(OBS/'교내정류장별_5분_승차대조.csv'):
        if r['V12_승차지지원']=='1':
            actual[r['승차정류장ID'],int(r['시작시각'][:2])]+=int(r['교외하차_카드승객수'])
    ids={s for s,h in actual}
    assert len(ids)==38
    scope=read(ROOT/'seoul_boardings_2026-11-10/stop_scope.json')['stops']
    bounds={s['stop_id'] for s in scope if s['zone'] in ('campus_core','campus_annex')}
    names={r['name']:r['id'] for r in read(ROOT/'app/data/network.json')['routes']}
    daily=defaultdict(list); section=defaultdict(list); departures=defaultdict(list)
    for name,groups in [('일자별_정류장승하차.csv',daily),('일자별_구간시간별_재차합.csv',section)]:
        for r in records(OBS/name):
            if r['비교상태'].startswith('동일'):
                groups[DAYS[date.fromisoformat(r['날짜']).weekday()]].append(r)
    for r in records(OBS/'행정관_차량위치_시각구간.csv'):
        if r['사건']=='exit' and 54000<=float(r['실측구간시작_자정후초'])<=float(r['실측구간끝_자정후초'])<=68400:
            departures[DAYS[date.fromisoformat(r['날짜']).weekday()]].append(r)
    segments=records(OBS/'시내버스_동일차량_운행시간.csv')
    base=read(V12/'viewer-data/common.json.gz')
    queue=[]; personal=[]; residual=[]; distribution=[]; results={}
    for version,folder in VERSIONS.items():
        is12=version=='V12'
        data=folder/('viewer-data' if is12 else 'public_data')
        common=read(data/'common.json.gz');hot=common['hot_nodes']
        if not is12:
            assert read(data/'half_hour.json.gz')['original_dataset']=='capacity_'+version.lower()
            assert read(folder/'independent_verification.json')['status']=='PASS'
        else:assert common['candidate_id']=='R261125170855'
        assert common['city_route_stops']==base['city_route_stops'] and hot==base['hot_nodes']
        for rid in common['city_route_stops']:
            assert common['route_info'][rid]['offsets']==base['route_info'][rid]['offsets']
        model=results[version]={}
        for service in SERVICES:
            matched=defaultdict(list); timing=defaultdict(list)
            for day in DAYS:
                key=f'{service}-{day}'; replay=read(data/(key+'.json.gz'))
                archive=folder/'runs/candidate'/key if is12 else folder
                audit=read(archive/f'audit-{key}.json.gz')
                for oid,wd,stop,hhmm,kind,span in field['records']:
                    if kind=='outside' and day==wd:
                        row=queue_row(Curve(replay['queue_timeline'][hot[stop]]),seconds(hhmm),*span)
                        queue.append(dict(version=version,service=service,observation=oid,day=day,stop=stop,
                                          clock=hhmm,observed_min=span[0],observed_max=span[1],**row))
                if day in ('mon','tue','wed'):
                    hhmm={'mon':'12:20','tue':'15:23','wed':'16:00'}[day]
                    a=riders(audit,replay['events'],hot['admin_snu'],seconds(hhmm))
                    for item,k in [('outside','wait_seconds'),('aboard','onboard_seconds'),('combined','combined_seconds')]:
                        summary=a[{'outside':'outside_s','aboard':'onboard_s','combined':'combined_s'}[item]]
                        numeric=day=='tue' and (is12 or item!='aboard')
                        obs=field['personal'][k] if numeric else None
                        personal.append(dict(version=version,service=service,day=day,clock=hhmm,metric=item,
                            observed_seconds=obs,median_seconds=summary['median'] if summary and (is12 or item!='aboard') else None,
                            abs_error=abs(summary['median']-obs) if summary and numeric else None,
                            served_joiners=a['boarded_mass'],same_minute_boards=a['same_minute_boards_mass']))
                if day=='mon':
                    node=hot['admin_daehak'];q=Curve(replay['queue_timeline'][node])
                    event=min((e for e in replay['events'] if e[1]==node),key=lambda e:abs(e[0]-17*3600))
                    residual.append(dict(version=version,service=service,departure_second=event[0],capacity=event[3],
                                departing_load=event[7],residual=q.at(event[0]),observed_residual=1))
                boards,off,loads,od=transit(audit,common,ids,bounds)
                for r in daily[day]:
                    k=names[r['노선']],int(r['순번']),r['정류장ID']
                    for source,metric,fieldkey in [(boards,'daily_board','승차'),(off,'daily_alight','하차')]:
                        if is12:
                            assert abs(source[k]-float(r[('기준' if service=='regular' else '피크')+'모의'+fieldkey]))<=.000501
                        matched[metric].append((source[k],float(r['실측'+fieldkey])))
                for r in section[day]:
                    k=names[r['노선']],int(r['출발순번']),r['출발지ID'],r['도착지ID'],int(r['시작시'])
                    if is12:assert abs(loads[k]-float(r['V12'+('기준' if service=='regular' else '피크')+'_재차합']))<=.000501
                    matched['section_hour_load'].append((loads[k],float(r['실측재차합'])))
                if day=='thu':
                    pred=[sum(od[s,h] for s in ids) for h in range(15,19)]
                    obs=[sum(actual[s,h] for s in ids) for h in range(15,19)]
                    assert obs==[810,996,1336,1321]
                    tv=50*sum(abs(p/sum(pred)-y/sum(obs)) for p,y in zip(pred,obs))
                    for h,p,y in zip(range(15,19),pred,obs):
                        distribution.append(dict(version=version,service=service,hour=h,observed=y,model=p,
                            observed_share=100*y/sum(obs),model_share=100*p/sum(pred),tv_percentage_points=tv))
                    matched['card_38_stops_x_4_hours'] += [(od[s,h],actual[s,h]) for s in sorted(ids) for h in range(15,19)]
                for r in departures[day]:
                    lo,hi=float(r['실측구간시작_자정후초']),float(r['실측구간끝_자정후초'])
                    node=hot['admin_snu' if r['노선']=='41841' else 'admin_daehak']
                    hit=any(lo<=e[0]<=hi and e[1]==node for e in replay['events'])
                    if is12:assert hit == (int(r[('기준' if service=='regular' else '피크')+'_구간내모의차량수'])>0)
                    timing[r['노선']].append(hit)
            qrows=[r for r in queue if r['version']==version and r['service']==service]
            assert len(qrows)==7
            model[service]={'queue':queue_score(qrows),'transit':{k:measures(v) for k,v in matched.items()},
                'omit_one_field_date_mae':{ymd:queue_score([r for r in qrows if not r['observation'].startswith(ymd)])['mae']
                                          for ymd in sorted({r['observation'][:8] for r in qrows})},
                'shuttle_exit':{k:{'n':len(v),'interval_hits':sum(v)} for k,v in timing.items()}}
            print(version,service,model[service]['queue'],flush=True)
        model['section_time_seconds']=measures([(float(r['모형구간초']),float(r['관측경과초'])) for r in segments])
    # Independent cross-check against the earlier two-version queue calculation.
    prior=read(V12/'v11_comparison/비교결과.json')['scores']
    for version,label in [('V11','V11'),('V12','R')]:
        for s in SERVICES:assert abs(results[version][s]['queue']['mae']-prior[s][label])<1e-8
    for name,rows in [('queue',queue),('personal',personal),('departures',residual),('card_hours',distribution)]:
        write_rows(OUT/(name+'.csv'),rows)
    save_json(OUT/'scores.json',results)


if __name__=='__main__':
    compare()
