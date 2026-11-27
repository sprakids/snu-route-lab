"""Summarize integrated demand and the matched counterfactual without rail."""
import csv
import math
from pathlib import Path

from model import HERE, DATA, INPUTS, REFERENCE, DAYS, MODEL, DEST, HOURS, load, SAVE


def csv_file(filename, rows):
    with (HERE/filename).open('w',encoding='utf-8-sig',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def weekly_dorm(rows):
    sums = {}
    for condition in ('이전 R','새 기숙사 곡선','신림선 통합 R'):
        sums[condition] = {}
        for dest in ('dorm_ug','dorm_grad','전체'):
            sub = [r for r in rows if r['조건']==condition and (dest=='전체' or r['기숙사']==dest)]
            total = math.fsum(r['하교건수'] for r in sub)
            sums[condition][dest] = dict(total=total, initial_walk=math.fsum(r['첫선택_도보건수'] for r in sub)/total,
                                         completed_walk=math.fsum(r['끝까지_차량미탑승'] for r in sub)/total)
    return sums


def main():
    common = load(DATA/'common.json.gz')
    assert common['dorm_choice']['rate_at_1000m']==.25
    nodes = common['nodes']
    cases, stops, dorms, destinations, long_waits = [], [], [], [], []
    with (REFERENCE/'요일별_기숙사_대학동_교통수단.csv').open(encoding='utf-8-sig') as stream:
        for r in csv.DictReader(stream):
            if r['조건']=='기숙사 보정 후' and r['목적지'].startswith('dorm'):
                dorms.append(dict(요일=r['요일'],조건='이전 R',기숙사=r['목적지'],하교건수=float(r['전체']),
                                  첫선택_도보건수=float(r['첫선택_도보']),끝까지_차량미탑승=float(r['끝까지_미승차_도보'])))
    for day in '월화수목금':
        did = DAYS[day]
        patch = load(INPUTS/f'{did}.json.gz')
        for service in ('regular','peak'):
            case = f'{service}-{did}'
            files = [next((HERE/k/case).glob('attempt-*/result.json')) for k in ('controls','runs')]
            control, run = (load(f) for f in files)
            assert control['weekday_demand']==run['weekday_demand'] and run['rail_target']==patch['station_demand']
            assert all(r['status']=='verified' and r['model']==MODEL and r['capacity_violations']==0 for r in (control,run))
            assert run['initial']['dorm_ug']==control['initial']['dorm_ug'] and run['initial']['dorm_grad']==control['initial']['dorm_grad']
            assert math.isclose(run['initial']['daehak']['total'],control['initial']['daehak']['total'])
            lost = math.fsum(control['initial'][d]['total']-run['initial'][d]['total'] for d in ('snu','nak'))
            assert math.isclose(lost,run['rail_target'],abs_tol=1e-7)
            center = run['completed'][DEST]
            baseline_area = math.fsum(control['stop_person_minutes'])
            area = math.fsum(run['stop_person_minutes'])
            arrivals = run['station_arrivals']
            cases.append(dict(요일=day,배차=service,전체_하교건수=run['weekday_demand'],관악산역_배정=run['rail_target'],
                              역도달_15시대=arrivals.get('15',0),역도달_16시대=arrivals.get('16',0),
                              역도달_17시대=arrivals.get('17',0),역도달_18시대=arrivals.get('18',0),
                              역도달_창밖=math.fsum(v for k,v in arrivals.items() if int(k) not in HOURS),
                              직접도보_또는_대기후도보=center.get('walk',0),교내셔틀_후_도보=center.get('shuttle',0),
                              시내버스_후_도보=center.get('city',0),
                              역까지_평균분=run['access_person_minutes']/math.fsum(arrivals.values()),
                              대조_15시19시_대기인분=baseline_area,통합_15시19시_대기인분=area,대기인분_변화=area-baseline_area,
                              한정류장_최장대기_분=run['max_continuous_wait'],이십분초과_대기사건=run['over20_weight'],
                              정원초과=run['capacity_violations'],미완료=run['unserved']))
            for i,(a,b) in enumerate(zip(control['stop_person_minutes'],run['stop_person_minutes'],strict=True)):
                stops.append(dict(요일=day,배차=service,정류장=nodes[i]['label'],노드=i,
                                  대조_대기인분=a,통합_대기인분=b,변화_대기인분=b-a))
            for file,r,label in zip(files,(control,run),('새 기숙사 곡선','신림선 통합 R'),strict=True):
                for i,v in load(file.parent/'all_stop_waits.json').items():
                    if v['over_20_minute_weight']>0:
                        long_waits.append(dict(condition=label,day=day,service=service,stop=nodes[int(i)]['label'],
                                               weight=v['over_20_minute_weight'],minutes=v['max_continuous_wait_min']))
                if service == 'regular':
                    for dest,initial in r['initial'].items():
                        finished=r['completed'][dest]
                        destinations.append(dict(요일=day,조건=label,목적지=dest,하교건수=initial['total'],
                                                 최초도보=initial.get('walk',0),완료도보=finished.get('walk',0),
                                                 셔틀접근=finished.get('shuttle',0),시내버스접근=finished.get('city',0),
                                                 미완료=finished.get('unserved',0)))
                        if dest in ('dorm_ug','dorm_grad'):
                            dorms.append(dict(요일=day,조건=label,기숙사=dest,하교건수=initial['total'],
                                              첫선택_도보건수=initial.get('walk',0),끝까지_차량미탑승=finished.get('walk',0)))
    csv_file('평일_통합하교_요약.csv',cases)
    csv_file('정류장별_신림선_통합효과.csv',stops)
    csv_file('요일별_기숙사도보.csv',dorms)
    csv_file('요일별_목적지수요.csv',destinations)
    summary = dict(model=MODEL,verified_integrated=len(cases),verified_controls=len(cases),
                   dorm=weekly_dorm(dorms),long_waits=long_waits,
                   weekday_total=sum(r['전체_하교건수'] for r in cases if r['배차']=='regular'),
                   regular=[r for r in cases if r['배차']=='regular'],
                   longest_wait=max(r['한정류장_최장대기_분'] for r in cases),
                   unserved=sum(r['미완료'] for r in cases),capacity_violations=sum(r['정원초과'] for r in cases))
    SAVE(HERE/'summary.json',summary)


if __name__=='__main__':
    main()
