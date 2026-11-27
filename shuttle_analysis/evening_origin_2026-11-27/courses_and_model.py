"""Compare Thursday timetables, course-generated departures and realised vehicle boardings."""
from bisect import bisect_left
from collections import Counter
import csv
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
RESEARCH=ROOT/'261127170244'
TARGET='120000173'
UPPER={'300','301','302'}
ENDPOINTS={'120900119':'낙성대','120900110':'낙성대','120000150':'서울대입구'}
spec=importlib.util.spec_from_file_location('research_inputs',RESEARCH/'run.py')
engine=importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
core=engine.core


def write(name,header,rows):
    with (HERE/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(header);w.writerows(rows)


def main():
    courses_dir=ROOT/'course_demand_2026-11-06'
    quality=core.read(courses_dir/'outputs/course_quality.json')
    archive=courses_dir/'sources/courses_2026-2_20261106.xls'
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==quality['source_sha256']
    courses=core.timing.ref.ref.class_events(core.timing.ref.load(core.timing.ref.ref.COURSES))
    original=core.read(ROOT/'scenario_comparison_2026-11-07/simulation_outputs/input_snapshot/course_endings_current.json')
    assert [r['section_id'] for r in original if r['included_main'] and r['weekday'] in '월화수목금' and r['end_minute']<=1390]==[r['section_id'] for r in courses]
    sections={r['source_excel_row']:r for r in csv.DictReader((courses_dir/'outputs/sections_current.csv').open(encoding='utf-8-sig'))}
    selected=[r for r in original if r['weekday']=='목' and r['building'] in UPPER]
    for r in selected:
        src=sections[str(r['source_excel_row'])]
        assert int(src['수강신청인원'])==r['enrollment'] and r['end'] in src['수업교시'] and r['course_title']==src['교과목명']
    fields=('building','end','section_id','course_title','degree_level','enrollment','included_main','exclusion_reasons')
    write('윗공대_목요일_종료강좌.csv',fields,([r[k] for k in fields] for r in sorted(selected,key=lambda x:(x['end'],x['building'],x['section_id']))))
    totals=Counter()
    for r in selected:
        if r['included_main']:totals[r['building'],r['end']]+=r['enrollment']
    write('목요일_종료시각별_등록인원.csv',('building','end','enrollments'),([*k,v] for k,v in sorted(totals.items())))
    weekday=core.official.prior.DAYS['thu']
    _,_,donors,_=core.timing.inputs(weekday,'peak')
    net=core.read(ROOT/'261125170855/viewer-data/common.json.gz')
    route_stops=net['city_route_stops']
    results=[];focus=Counter()
    for model,folder in [('직전 R',ROOT/'261127162719/runs/october/peak-thu'),('체류·거리별 접근 R',RESEARCH/'runs/joint_soft/peak-thu')]:
        a=core.read(folder/'audit-peak-thu.json.gz')
        events={(e[2],e[1],e[0]):(e[11],e[12],e[6]) for e in a['events'] if e[11] in route_stops}
        generated=Counter();arrivals=Counter();direct=Counter();verified=Counter()
        with gzip.open(RESEARCH/'runs/joint_soft/peak-thu/inputs.csv.gz','rt',encoding='utf8') as f:
            identities={int(r['uid']):r['building'] for r in csv.DictReader(f)}
        for trip in a['legs']:
            uid=trip['id'];cr=courses[(donors.get(uid,uid)-1)//48];building=cr['building'];weight=trip['weight']
            assert cr['weekday']==weekday and building==identities[uid]
            key=building,cr['end']
            if building in UPPER:generated[key]+=weight
            cohort=key==('302','18:15')
            def slot(t):
                q=int(t//900)*15
                return f'{q//60:02d}:{q%60:02d}'
            if cohort:focus[model,'건물 출발',slot(trip['start'])]+=weight
            boarded_target=False
            for l in trip['legs']:
                if l[0]!=3:continue
                e=events.get((l[6],l[4],l[1]))
                if not e:continue
                rid,idx,n=e
                if route_stops[rid][idx]['id']!=TARGET:continue
                if cohort and not boarded_target:
                    focus[model,'제2공학관 첫 이용',slot(l[1])]+=weight
                    boarded_target=True
                if not 19*3600<=l[1]<20*3600:continue
                verified[l[6],l[4],l[1]]+=weight
                off=net['route_info'][rid]['offsets'];j=bisect_left(off,off[idx]+l[2]-l[1]-1e-5)
                assert j>idx and abs(off[j]-off[idx]-l[2]+l[1])<1e-5
                endpoint=route_stops[rid][j]['id']
                arrivals[key]+=weight;direct[key,ENDPOINTS.get(endpoint,'기타')]+=weight
            if cohort and not boarded_target:focus[model,'제2공학관 미이용','전체']+=weight
        target_events={k:v for k,v in events.items() if 19*3600<=k[2]<20*3600 and route_stops[v[0]][v[1]]['id']==TARGET}
        assert all(abs(verified[k]-v[2])<1e-6 for k,v in target_events.items())
        for k in sorted(set(totals)|set(arrivals)):
            results.append([model,*k,totals.get(k,''),generated[k] if k in totals else '',arrivals[k],*[direct[k,label] for label in ('낙성대','서울대입구','기타')]])
        assert abs(sum(n for (m,action,_),n in focus.items() if m==model and action.startswith('제2공학관'))-generated['302','18:15'])<1e-6
    write('모형_19시_승객의_수업출발지.csv',('model','building','scheduled_end','enrollment','modeled_all_day_departures','modeled_19h_boardings','nak','snu','other'),results)
    write('302동_18시15분반_모의이동.csv',('model','measure','time_bin_start','modeled_mass'),([*k,n] for k,n in sorted(focus.items())))
    print('Verified',len(selected),'schedule rows and both event ledgers',flush=True)

if __name__=='__main__':main()
