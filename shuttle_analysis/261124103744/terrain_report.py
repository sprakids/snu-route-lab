"""Report terrain choices and the matched station counterfactual for all ten services."""
from collections import Counter, defaultdict
import csv
import math

from slope_model import HERE, DAYS, MODEL, previous, load


def write_csv(name,rows):
    with (HERE/name).open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    rows=[]
    by_pair=defaultdict(Counter)
    nodes=load(HERE/'viewer-data/common.json.gz')['nodes']
    stops=[]
    for did in DAYS.values():
        for service in ('regular','peak'):
            key=f'{service}-{did}'
            paired=[load(next((HERE/k/key).glob('attempt-*/result.json'))) for k in ('runs','controls')]
            current,control=paired
            old=load(next((previous.HERE/'runs'/key).glob('attempt-*/result.json')))
            assert all(r['model']==MODEL and r['status']=='verified' and r['capacity_violations']==0 for r in paired)
            assert current['weekday_demand']==control['weekday_demand']==old['weekday_demand']
            assert current['initial']['dorm_ug']==control['initial']['dorm_ug'] and current['initial']['dorm_grad']==control['initial']['dorm_grad']
            rail=current['completed'][previous.DEST]
            arrived=sum(current['station_arrivals'].values())
            assert math.isclose(sum(rail.values()),current['rail_target'],abs_tol=1e-6)
            shift=math.fsum(a-b for a,b in zip(current['stop_person_minutes'],control['stop_person_minutes'],strict=True))
            row=dict(요일=current['day'],배차=service,전체_하교=current['weekday_demand'],관악산역_배정=current['rail_target'],
                     관악산역_도달=arrived,역접근_평균분=current['access_person_minutes']/arrived,
                     역접근_차량미이용=rail.get('walk',0),역접근_교내셔틀=rail.get('shuttle',0),역접근_시내버스=rail.get('city',0),
                     신림선재배정_대기인분변화=shift,지형전_최장연속대기분=old['max_continuous_wait'],
                     지형후_최장연속대기분=current['max_continuous_wait'],이십분초과_대기가중건=current['over20_weight'],
                     미완료=current['unserved'],정원위반=current['capacity_violations'])
            rows.append(row)
            for i,(a,b) in enumerate(zip(current['stop_person_minutes'],control['stop_person_minutes'],strict=True)):
                stops.append(dict(요일=current['day'],배차=service,노드=i,정류장=nodes[i]['label'],신림선포함_인분=a,대조_인분=b,증감_인분=a-b))
            if service=='regular':
                for k,r in current['upper_initial'].items():
                    v=by_pair[k]
                    v['total']+=r['total']
                    v['old_direct']+=r['old_direct']
                    v['new_direct']+=r['new_direct']
                    v['end_to_end_walk']+=current['upper_completed'][k].get('end_to_end_walk',0)
                    assert math.isclose(current['upper_completed'][k]['total'],r['total'],abs_tol=1e-5)
    terrain=load(HERE/'terrain.json')
    dorms=[]
    for r in terrain['rows']:
        if 'path' not in r:
            continue
        v=by_pair[r['building']+'|'+r['dorm']]
        dorms.append(dict(출발=r['name'],도착=r['dorm'],평면거리m=r['planar_m'],경사면거리m=r['surface_m'],누적상승m=r['ascent_m'],
                          누적하강m=r['descent_m'],선택용거리m=r['choice_m'],지형전_전환확률=previous.dorm_distance.probability(r['meters']),
                          지형후_전환확률=previous.dorm_distance.probability(r['choice_m']),평일총건수=v['total'],
                          지형전_최초도보건수=v['old_direct'],지형후_최초도보건수=v['new_direct'],지형후_무승차완료=v['end_to_end_walk']))
    write_csv('요일별_통합결과.csv',rows)
    write_csv('요일별_신림선_대기변화.csv',stops)
    write_csv('윗공대_기숙사_도보변화.csv',dorms)
    previous.SAVE(HERE/'terrain_results.json',dict(model=MODEL,runs=10,controls=10,cases=rows,dorms=dorms))


if __name__=='__main__':
    main()
