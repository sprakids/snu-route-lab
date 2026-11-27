"""Public Seoul CSV exports, filtered to campus stops without changing model inputs.

OA-12913 monthly hourly counts and OA-12912 daily counts remain distinct tables.
The site's public search form is reproduced unchanged except for its route filter.
No private API key, account, SQL change, or retry is used.
"""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import csv
import hashlib
import io
import json
import re
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
ANALYSIS = ROOT.parent
ROUTES = ['5511','5513','5516','관악02-1','관악02-2','5515','5528','6515']
START, END = '20261013', '20261109'
RAW = ROOT/'sources'
OUT = ROOT/'outputs'
RAW.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)
OUTSIDE = {'120000028','120000029','120000670','120000058','120900090',
           '120900095','120900140','120000665','120000668'}
ANNEX = {'120900003','120900157','120900153','120900185','120900009'}


def dump(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),encoding='utf-8')


def read_csv(data):
    try:
        text=data.decode('utf-8-sig');encoding='utf-8-sig'
    except UnicodeDecodeError:
        text=data.decode('cp949');encoding='cp949'
    reader=csv.DictReader(io.StringIO(text))
    return reader.fieldnames,list(reader),encoding


def write_csv(path, rows, fields):
    with path.open('w',encoding='utf-8-sig',newline='') as output:
        writer=csv.DictWriter(output,fieldnames=fields,extrasaction='raise')
        writer.writeheader();writer.writerows(rows)


def stop_index():
    roster=json.loads((ANALYSIS/'collector/route_stops.json').read_text(encoding='utf-8-sig'))
    index={}
    for route_id, stops in roster.items():
        for stop in stops:
            if not(37.445<=stop['lat']<=37.472 and 126.946<=stop['lon']<=126.968):continue
            sid=stop['id']
            item=index.setdefault(sid,{'stop_id':sid,'name':stop['name'],'ars':stop['ars'],
                'lat':stop['lat'],'lon':stop['lon'],'route_ids':[],
                'zone':'outside_context' if sid in OUTSIDE else ('campus_annex' if sid in ANNEX else 'campus_core')})
            if route_id not in item['route_ids']:item['route_ids'].append(route_id)
    dump(ROOT/'stop_scope.json',{'source':'../collector/route_stops.json',
        'selection':'Campus core plus SNU residence/Hoam annex; nearby public-road stops stored separately',
        'warning':'This is a reviewed project stop list, not an official cadastral boundary',
        'counts':dict(Counter(s['zone'] for s in index.values())),
        'stops':sorted(index.values(),key=lambda x:x['stop_id'])})
    return index


def fetch_daily(route):
    target=RAW/f'daily_route_{route}.csv'
    if target.exists():return route,target.read_bytes(),True
    if route=='5511':
        seed=ROOT/'daily_5511_response.bin'
        if seed.exists():
            data=seed.read_bytes();target.write_bytes(data);return route,data,True
    page=(ROOT/'daily_sheet_post.html').read_text(encoding='utf-8')
    form=re.search(r'<form[^>]*name="frmSheet"[^>]*>([\s\S]*?)</form>',page).group(1)
    params={}
    for tag in re.findall(r'<input[^>]+>',form):
        name=re.search(r'\bname="([^"]+)"',tag)
        value=re.search(r'\bvalue="([^"]*)"',tag)
        if name:params[name.group(1)]=value.group(1) if value else ''
    params.update(filterCol='RTE_NO',txtFilter=route)
    url='https://datafile.seoul.go.kr/bigfile/iot/sheet/csv/download.do'
    req=urllib.request.Request(url,data=urllib.parse.urlencode(params).encode('ascii'),headers={
        'User-Agent':'Mozilla/5.0',
        'Referer':'https://data.seoul.go.kr/dataList/OA-12912/S/1/datasetView.do'})
    with urllib.request.urlopen(req,timeout=40) as response:
        data=response.read(20_000_001)
        if response.status!=200 or len(data)>20_000_000:raise ValueError('Unexpected/bounded response')
    if data.lstrip().startswith(b'<'):raise ValueError('HTML response is not data')
    fields,rows,encoding=read_csv(data)
    if not fields or '사용일자' not in fields:raise ValueError('Unexpected daily schema')
    if any(r['노선번호']!=route for r in rows):raise ValueError('Public route filter was not exact')
    target.write_bytes(data)
    return route,data,False


def decorate(row,index):
    item=index[row['표준버스정류장ID']]
    match=re.search(r'\((\d+)\)$',row['역명'])
    return {**row,'stop_sequence':str(int(match.group(1))) if match else '',
        'zone':item['zone'],'latitude':item['lat'],'longitude':item['lon']}


def main():
    index=stop_index()
    # Reuse the original, independently hashed file already in the workspace.
    cached=ANALYSIS/'historical_validation_2026-11-06/sources/boardings_hourly_202610.csv'
    original_receipt=json.loads((cached.parent/'download_receipt.json').read_text(encoding='utf-8'))
    data=cached.read_bytes()
    assert hashlib.sha256(data).hexdigest()==original_receipt['sha256']
    fields,rows,encoding=read_csv(data)
    assert {r['사용년월'] for r in rows}=={'202610'}
    campus=[decorate(r,index) for r in rows if r['표준버스정류장ID'] in index and r['표준버스정류장ID'] not in OUTSIDE]
    nearby=[decorate(r,index) for r in rows if r['표준버스정류장ID'] in OUTSIDE and r['노선번호'] in ROUTES]
    extras=['stop_sequence','zone','latitude','longitude']
    write_csv(OUT/'campus_hourly_monthly_202610.csv',campus,fields+extras)
    write_csv(OUT/'nearby_8_routes_hourly_monthly_202610.csv',nearby,fields+extras)
    long=[]
    for row in campus:
        for hour in range(24):
            prefix='00' if hour==0 else str(hour)
            board=int(row[f'{prefix}시승차총승객수'])
            alight=int(row[f'{prefix}시하차총승객수'])
            assert board>=0 and alight>=0
            long.append({'month':row['사용년월'],'route_no':row['노선번호'],
                'stop_id':row['표준버스정류장ID'],'ars_no':row['버스정류장ARS번호'],
                'stop_name':row['역명'],'stop_sequence':row['stop_sequence'],
                'zone':row['zone'],'hour_kst':hour,'monthly_boardings':board,'monthly_alightings':alight})
    write_csv(OUT/'campus_hourly_monthly_202610_long.csv',long,list(long[0]))
    receipts=[];daily=[];daily_nearby=[];daily_fields=None
    with ThreadPoolExecutor(max_workers=2) as pool:
        for route,raw,reused in pool.map(fetch_daily,ROUTES):
            fields,records,enc=read_csv(raw)
            daily_fields=fields
            dates=Counter(r['사용일자'] for r in records)
            selected=[r for r in records if START<=r['사용일자']<=END]
            chosen=[decorate(r,index) for r in selected if r['표준버스정류장ID'] in index and r['표준버스정류장ID'] not in OUTSIDE]
            context=[decorate(r,index) for r in selected if r['표준버스정류장ID'] in OUTSIDE]
            daily.extend(chosen);daily_nearby.extend(context)
            receipts.append({'route_no':route,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                'reused_download':reused,'source_rows':len(records),'all_dates':sorted(dates),
                'requested_date_rows':len(selected),'campus_rows':len(chosen),'nearby_rows':len(context),'encoding':enc,
                'endpoint':'https://datafile.seoul.go.kr/bigfile/iot/sheet/csv/download.do',
                'public_filter':{'filterCol':'RTE_NO','txtFilter':route},'api_key_used':False})
            print(json.dumps({k:receipts[-1][k] for k in ['route_no','bytes','source_rows','campus_rows','nearby_rows']},ensure_ascii=False),flush=True)
    write_csv(OUT/'campus_daily_20261013_20261109_available.csv',daily,daily_fields+extras)
    write_csv(OUT/'nearby_8_routes_daily_20261013_20261109_available.csv',daily_nearby,daily_fields+extras)
    dates=sorted({r['사용일자'] for r in daily})
    expected=[];day=datetime.strptime(START,'%Y%m%d')
    while day.strftime('%Y%m%d')<=END:
        expected.append(day.strftime('%Y%m%d'));day+=timedelta(days=1)
    keycols=['사용일자','노선번호','표준버스정류장ID','역명']
    keys=[tuple(r[c] for c in keycols) for r in daily]
    duplicate_keys=len(keys)-len(set(keys))
    assert duplicate_keys==0,'Repeated stops in a route must retain stop sequence, not create duplicated joins'
    assert all(int(r[c])>=0 for r in daily for c in ['승차총승객수','하차총승객수'])
    profile={'requested_start':START,'requested_end':END,'available_dates':dates,
        'missing_dates':[d for d in expected if d not in dates],
        'monthly_hourly':{'month':'202610','original_bytes':len(data),'source_sha256':original_receipt['sha256'],
            'source_rows':len(rows),'campus_rows':len(campus),'unique_campus_stops':len({r['표준버스정류장ID'] for r in campus}),
            'campus_routes':dict(Counter(r['노선번호'] for r in campus)),
            'nearby_8_route_rows':len(nearby),'reused_source':str(cached.resolve()),'encoding':encoding},
        'daily':{'campus_rows':len(daily),'nearby_8_route_rows':len(daily_nearby),
            'unique_campus_stops':len({r['표준버스정류장ID'] for r in daily}),
            'routes':dict(Counter(r['노선번호'] for r in daily)),
            'duplicate_composite_keys':duplicate_keys,'source_receipts':receipts},
        'limitations':['Monthly hourly totals cannot be split into exact dates or weekdays.',
            'Daily totals do not contain hourly or individual boarding times.',
            'Neither table includes queue joining time, denied boarding, or SNU student affiliation.',
            'Missing dates are not imputed as zeros; no simulation parameter or deployment changed.'],
        'sources':['https://data.seoul.go.kr/dataList/OA-12913/S/1/datasetView.do',
                   'https://data.seoul.go.kr/dataList/OA-12912/S/1/datasetView.do'],
        'collected_at':datetime.now(timezone.utc).isoformat()}
    dump(ROOT/'collection_quality.json',profile)
    print(json.dumps({k:v for k,v in profile.items() if k not in ['daily','limitations']},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
