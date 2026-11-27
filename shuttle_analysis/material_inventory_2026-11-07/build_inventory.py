"""Index existing research evidence only. No fetching, keys or model execution."""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone,timedelta
from urllib.parse import urlsplit,parse_qsl,urlencode,urlunsplit
import json,csv,math

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent
load=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
def safe_url(value):
    value=str(value or '')
    if not value.startswith(('https://','http://')):return value
    parts=urlsplit(value)
    sensitive={'apikey','servicekey','access_token','token','authorization'}
    pairs=[(k,'REDACTED' if k.lower() in sensitive else v) for k,v in parse_qsl(parts.query,keep_blank_values=True)]
    return urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(pairs),parts.fragment))
def records(value):
    if isinstance(value,list):
        for x in value:yield from records(x)
    elif isinstance(value,dict):
        if any(k in value for k in ('url','source_url')):yield value
        else:
            for x in value.values():
                if isinstance(x,(dict,list)):yield from records(x)
registries=sorted(BASE.glob('*/source_register.json'))+[BASE/'course_demand_2026-11-06/sources/source_register.json']
items=[]
for path in registries:
    if not path.exists():continue
    for r in records(load(path)):
        first=lambda keys:next((r[k] for k in keys if r.get(k) is not None),'')
        items.append({'register':str(path.relative_to(BASE)),'id':first(['id','name']),
            'title':first(['title','name','file','local_file']),
            'publisher':first(['publisher','source']),'date':first(['date','published','survey_year','captured_at']),
            'url':safe_url(first(['url','source_url'])),
            'access':first(['access','level','acquisition','status']),
            'use':first(['supports','use','scope']),
            'limitations':first(['limitations','limitation','limit']),
            'local_file':first(['file','local_file','pdf_file'])})
with (ROOT/'출처등록부_통합.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(items[0]));w.writeheader();w.writerows(items)

families={'재차합':'a18SumLoadPsngNum','평균재차':'a18Num','최대재차':'maxA18Num','운행횟수':'a18FcntNum'}
stats={k:Counter() for k in families};dates=[];routecounts=Counter();total_rows=0
for folder in sorted((BASE/'tdata_calibration_2026-11-07/collected').iterdir()):
    path=folder/'target_routes.json';receipt=folder/'collection_receipt.json'
    if not path.exists() or not receipt.exists() or load(receipt).get('status')!='complete':continue
    rows=load(path);days={r['stdrDe'] for r in rows};assert days=={folder.name}
    dates.append(folder.name);total_rows+=len(rows)
    for r in rows:
        routecounts[str(r['routeId'])]+=1
        for label,prefix in families.items():
            for hour in range(24):
                field=f'{prefix}{hour:02d}h';stats[label]['cells']+=1
                if field not in r:stats[label]['field_absent']+=1;continue
                value=r[field]
                if value is None:stats[label]['null']+=1
                else:
                    number=float(value);assert math.isfinite(number) and number>=0
                    stats[label]['nonnull']+=1;stats[label]['zero' if number==0 else 'positive']+=1
course=load(BASE/'course_demand_2026-11-06/outputs/course_quality.json')
buildings=load(BASE/'course_demand_2026-11-06/sources/campus_buildings.json')
stops=load(BASE/'course_demand_2026-11-06/sources/campus_bus_stops.json')
summary={'asof_kst':datetime.now(timezone(timedelta(hours=9))).isoformat(),
    'scope':'Existing project evidence inventory; no new data collection or model execution.',
    'initial_source_register_entries':len(load(BASE/'research/source_register.json')),
    'merged_register_files':len([p for p in registries if p.exists()]),'merged_register_entries':len(items),
    'merged_exact_url_strings':len({r['url'] for r in items if r['url']}),
    'register_count_is_not_independent_document_count':True,
    'latest_archived_course_rows':course['data_rows'],'latest_main_buildings':course['main_buildings'],
    'official_map_building_rows':len(buildings['rows']),'official_shuttle_stop_records':len(stops['bus_station_list']),
    'tdata_complete_dates':dates,'tdata_date_count':len(dates),'tdata_raw_rows':total_rows,
    'tdata_hour_cells_per_family':total_rows*24,'tdata_route_row_counts':dict(routecounts),
    'tdata_family_cells':{k:dict(v) for k,v in stats.items()},
    'current_student_destination_shares_measured':False,'new_student_interviews_conducted':False,
    'field_shuttle_queues_observed':False,'signed_current_shuttle_contract_acquired':False,
    'network_requests':0,'credentials_read':False}
(ROOT/'inventory_checks.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

path=ROOT/'조사자료_전체목록.md'
text=path.read_text(encoding='utf-8')
assert '<!-- AUTO_APPENDIX -->' in text
appendix=['## 등록부별 개별 출처 전체', '',
 '아래는 기존 출처등록부를 합친 목록입니다. 같은 URL의 재확인·재게시·중복 등록을 보존했으므로 항목 수를 독립 문헌 수로 세면 안 됩니다. 제목·확보 수준이 없는 캡처는 등록부의 파일명·상태를 그대로 남겼습니다.', '',
 f'- 통합 등록부 {summary["merged_register_files"]}개, 등록 항목 {len(items)}개, 서로 다른 URL 문자열 {summary["merged_exact_url_strings"]}개.',
 '- 나라장터 보존 공고, 회의록, API·지도·실측자료 등 등록부 밖의 자료는 앞의 주제별 목록에 별도로 기록했습니다.', '']
for register in dict.fromkeys(r['register'] for r in items):
    appendix += [f'### {register}', '']
    for r in [x for x in items if x['register']==register]:
        title=str(r['title'] or r['id'] or r['url']).replace('\n',' ')
        appendix.append(f'- **{r["id"]} · [{title}]({r["url"]})**')
        if r['access']:appendix.append(f'  - 확보·열람 수준: {r["access"]}')
        if r['use']:appendix.append(f'  - 조사 내용: {r["use"]}')
        if r['limitations']:appendix.append(f'  - 한계: {r["limitations"]}')
    appendix.append('')
appendix+=['## 현재 보존된 T-data 전체 범위', '',
    f'- 완전 수집된 날짜 {len(dates)}일: '+', '.join(dates),
    f'- 원행 {total_rows:,}행; 시간별 계열마다 {total_rows*24:,}셀.', '']
for label,counts in stats.items():
    appendix.append(f'- {label}: 값 있음 {counts["nonnull"]:,}, 그중 관측0 {counts["zero"]:,}, null {counts["null"]:,}, 필드 자체 없음 {counts["field_absent"]:,}.')
appendix+=['', '이 표는 이미 저장된 원자료를 다시 센 결과입니다. 재차합은 구간·시간 합계이며 고유 승객 수, 버스 한 대의 혼잡률, 무료 셔틀 대기열이 아닙니다.', '']
path.write_text(text.replace('<!-- AUTO_APPENDIX -->','\n'.join(appendix)),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
