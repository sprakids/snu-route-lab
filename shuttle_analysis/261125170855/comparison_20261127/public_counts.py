"""Align published daily stop totals and hourly section passenger loads to the V12 ledger."""
from bisect import bisect_left
from collections import Counter
import csv
from datetime import datetime
from card_checks import HERE, MODEL, ROOT, read

def aggregate(case,common):
    audit=read(MODEL/f'runs/candidate/{case}/audit-{case}.json.gz')
    routes=common['city_route_stops']
    offsets={rid:common['route_info'][rid]['offsets'] for rid in routes}
    events={(v,n,t):(rid,i,on) for t,n,v,_,_,_,on,_,_,_,_,rid,i in audit['events'] if rid in routes}
    ons,offs,loads,check=Counter(),Counter(),Counter(),Counter()
    for trip in audit['legs']:
        w=trip['weight']
        for mode,t,end,path,n,_,v,*_ in trip['legs']:
            if mode!=3 or not common['nodes'][n].get('city'):continue
            rid,i,_=events[v,n,t]; times=offsets[rid]
            j=bisect_left(times,times[i]+end-t-1e-5)
            assert i<j and abs(times[j]-times[i]-(end-t))<1e-5
            check[v,n,t]+=w
            if 0<=t<86400:ons[rid,i]+=w
            if 0<=end<86400:offs[rid,j]+=w
            for k in range(i,j):
                hour=int((t+(times[k]-times[i]))//3600)
                if 0<=hour<24:loads[rid,k,hour]+=w
    assert all(abs(check[key]-row[2])<1e-5 for key,row in events.items())
    return ons,offs,loads

def main():
    common=read(MODEL/'viewer-data/common.json.gz')
    routes=common['city_route_stops']
    id_by_name={r['name']:r['id'] for r in read(ROOT/'app/data/network.json')['routes']}
    index={(rid,s['seq'],s['id']):k for rid,stops in routes.items() for k,s in enumerate(stops)}
    models={(wd,sc):aggregate(sc+'-'+wd,common) for wd in ('mon','tue','wed','thu','fri') for sc in ('regular','peak')}
    def daykey(d):
        i=datetime.strptime(d,'%Y%m%d').weekday()
        return ('mon','tue','wed','thu','fri','sat','sun')[i]
    out=ROOT/'seoul_boardings_2026-11-10/outputs'
    with (HERE/'일자별_정류장승하차.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(['날짜','노선','순번','정류장ID','정류장','실측승차','실측하차','기준모의승차','기준모의하차','피크모의승차','피크모의하차','비교상태'])
        for prefix in ('campus','nearby_8_routes'):
            with (out/f'{prefix}_daily_20261013_20261109_available.csv').open(encoding='utf-8-sig') as src:
                for r in csv.DictReader(src):
                    d,name,s=r['사용일자'],r['노선번호'],r['표준버스정류장ID']
                    idx=int(r['stop_sequence']); rid=id_by_name.get(name); wd=daykey(d)
                    k=index.get((rid,idx,s)); vals=[]
                    valid=k is not None and (wd,'regular') in models
                    for sc in ('regular','peak'):
                        if valid:vals.extend(round(table[rid,k],3) for table in models[wd,sc][:2])
                        else:vals.extend(['',''])
                    w.writerow([d,name,idx,s,r['역명'],r['승차총승객수'],r['하차총승객수'],*vals,
                                '동일순번·정류장' if valid else ('주말' if wd in ('sat','sun') else '노선·순번·정류장 미대응')])
    with (ROOT/'tdata_calibration_2026-11-07/observations/hourly_observations.csv').open(encoding='utf-8-sig') as src, (HERE/'일자별_구간시간별_재차합.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(['날짜','노선','출발순번','출발지ID','도착지ID','시작시','실측재차합','실측운행수','V12기준_재차합','V12피크_재차합','비교상태'])
        for r in csv.DictReader(src):
            d,rid,h=r['date'],r['route_id'],int(r['hour'])
            wd=daykey(d); k=index.get((rid,int(r['sta_sn']),r['from_stop_id']))
            pair=k is not None and k+1<len(routes[rid]) and routes[rid][k+1]['id']==r['to_stop_id']
            vals=[round(models[wd,sc][2][rid,k,h],3) if pair else '' for sc in ('regular','peak')]
            w.writerow([d,r['route_name'],r['sta_sn'],r['from_stop_id'],r['to_stop_id'],h,r['sum_load'],r['runs'],*vals,
                        '노선구간 미대응' if not pair else ('실측 결측' if r['sum_load']=='' else '동일구간·시간')])

if __name__=='__main__':main()
