"""Reconcile an observed public-sheet date gap against its official monthly file."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
import re
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parent
target=ROOT/'sources/daily_all_routes_202610.csv'
receipt=ROOT/'sources/daily_all_routes_202610.receipt.json'
page=(ROOT/'daily_source_page.html').read_text(encoding='utf-8')
match=re.search(r'title="BUS_STATION_BOARDING_MONTH_202610\.csv" onclick="javascript:downloadFile\(\'(\d+)\'\)',page)
assert match,'The original file must be listed on the public page'
seq=match.group(1)
url='https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false'
if not target.exists():
    req=urllib.request.Request(url,data=urllib.parse.urlencode({
        'infId':'OA-12912','seqNo':'','seq':seq,'infSeq':'3'}).encode('ascii'),
        headers={'User-Agent':'Mozilla/5.0','Referer':'https://data.seoul.go.kr/dataList/OA-12912/S/1/datasetView.do'})
    temp=target.with_suffix('.csv.partial')
    with urllib.request.urlopen(req,timeout=40) as response,temp.open('xb') as output:
        total=0;digest=hashlib.sha256()
        while data:=response.read(4*1024*1024):
            if not total and data.lstrip().startswith(b'<'):raise ValueError('HTML is not CSV')
            output.write(data);digest.update(data);total+=len(data)
            if total>250_000_000:raise ValueError('Bounded download exceeded')
            if total%(32*1024*1024)==0:print('MONTH_FILE_BYTES',total,flush=True)
    temp.rename(target)
    receipt.write_text(json.dumps({'source_page':'https://data.seoul.go.kr/dataList/OA-12912/S/1/datasetView.do',
        'file_name':'BUS_STATION_BOARDING_MONTH_202610.csv','sequence':seq,'bytes':total,
        'sha256':digest.hexdigest(),'api_key_used':False,'automatic_retries':0,
        'downloaded_at':datetime.now(timezone.utc).isoformat()},ensure_ascii=False,indent=2),encoding='utf-8')

with target.open(encoding='cp949',newline='') as source:
    reader=csv.DictReader(source)
    print('MONTH_FILE_FIELDS',reader.fieldnames,flush=True)
    dates={};selected=[];all_rows=0
    routes={'5511','5513','5516','관악02-1','관악02-2','5515','5528','6515'}
    for row in reader:
        all_rows+=1
        day=row['사용일자']
        dates[day]=dates.get(day,0)+1
        if row['노선번호'] in routes:selected.append(row)
    print('MONTH_DATES',json.dumps(dates,ensure_ascii=False),flush=True)
    print('MONTH_ROWS',all_rows,'SELECTED',len(selected),flush=True)
    out=ROOT/'sources/daily_8_routes_202610_archive.csv'
    with out.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=reader.fieldnames);writer.writeheader();writer.writerows(selected)
    result={'source_rows':all_rows,'source_dates':dates,'selected_8_route_rows':len(selected),
            'october_27_present':'20261027' in dates,'source':'daily_all_routes_202610.csv',
            'selected_file':str(out)}
    (ROOT/'october_gap_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
