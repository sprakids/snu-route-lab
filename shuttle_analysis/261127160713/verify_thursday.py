"""Independent per-trip comparison from realized vehicle events and course records."""
from bisect import bisect_left
from collections import Counter, defaultdict
from math import isclose
from evaluate import HERE, V12, TARGET, HOURS, SERVICES, card_observations, folder, read, records, write_rows


def run():
    root=HERE.parent
    courses=[r for r in read(root/'scenario_comparison_2026-11-07/simulation_outputs/input_snapshot/course_endings_current.json')
             if r['included_main'] and r['weekday'] in '월화수목금' and r['end_minute']<=1390]
    repl=read(root/'261124103744/inputs/thu.json.gz')['replacements']
    parents={r['plan'][0]:r['donor'] for r in repl}
    rail=set(parents)
    common=read(V12/'viewer-data/common.json.gz')
    routes=common['city_route_stops']
    _,_,campus=card_observations()
    export={(r['service'],r['model'],int(r['hour'])):float(r['modeled'])
            for r in records(HERE/'목요일_38곳_시간별.csv') if r['stop_id']==TARGET}
    design={(r['service'],r['model']):r for r in records(HERE/'윗공대_출발과_실제승차.csv') if r['day']=='thu'}
    detail=[]
    for service in SERVICES:
        key=service+'-thu'
        clocks={}
        mass={}
        for v in ('V12','origin','choice','both'):
            a=read(folder(v,key)/f'audit-{key}.json.gz')
            events={(e[2],e[1],e[0]):(e[11],e[12]) for e in a['events'] if e[11] in routes}
            counts=Counter()
            per_id=Counter()
            upper_first=upper_ever=0.
            for p in a['legs']:
                uid,w=p['id'],p['weight']
                course=courses[(parents.get(uid,uid)-1)//48]
                assert course['weekday']=='목'
                upper=str(course['building']) in ('300','301','302')
                per_id[uid]+=w
                if v=='V12':
                    clocks.setdefault(uid,p['start'])
                assert p['start']==clocks[uid]
                rides=[l for l in p['legs'] if l[0]==3]
                hit=False
                for j,leg in enumerate(rides):
                    _,t,end,_,node,_,vehicle,*_=leg
                    event=events.get((vehicle,node,t))
                    if not event:
                        continue
                    rid,i=event
                    stops=routes[rid]
                    if stops[i]['id']!=TARGET:
                        continue
                    hit=True
                    if j==0 and upper:
                        upper_first+=w
                    offsets=common['route_info'][rid]['offsets']
                    index=bisect_left(offsets,offsets[i]+end-t-1e-5)
                    assert abs(offsets[index]-offsets[i]-(end-t))<1e-5
                    if stops[index]['id'] not in campus:
                        counts[int(t//3600),upper]+=w
                if hit and upper:
                    upper_ever+=w
            mass[v]=per_id
            assert set(per_id)==set(clocks)
            d=design[service,v]
            assert abs(upper_first-float(d['actual_first_target']))<1e-6
            assert abs(upper_ever-float(d['actual_ever_target']))<1e-6
            assert abs(sum(per_id[k] for k in rail)-320)<1e-6
            for hour in HOURS:
                total=counts[hour,True]+counts[hour,False]
                assert abs(total-export[service,v,hour])<1e-6
                detail.append(dict(service=service,model=v,hour=hour,upper_origin=counts[hour,True],
                                   other_origin=counts[hour,False],total=total))
        for uid in clocks:
            assert isclose(mass['V12'][uid],mass['choice'][uid],abs_tol=1e-7)
            assert isclose(mass['origin'][uid],mass['both'][uid],abs_tol=1e-7)
    write_rows(HERE/'제2공학관_출발권역별.csv',detail)


if __name__=='__main__':
    run()
