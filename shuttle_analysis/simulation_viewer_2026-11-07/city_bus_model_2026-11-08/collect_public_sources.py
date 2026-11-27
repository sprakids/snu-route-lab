"""Collect public Seoul planning metadata and manufacturer references; no keys."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import concurrent.futures
import hashlib
import json
import time
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'sources'
BASE='http://m.bus.go.kr/mBus/bus/'
NAMES=['5511','5513','5515','5516','5528','6515','관악02-1','관악02-2']
IDS=dict(zip(NAMES,['100100250','100100251','100100252','100100253','100100263','100100521','120900011','120900012']))
HEADERS={'User-Agent':'Mozilla/5.0','Referer':'http://m.bus.go.kr/',
         'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8'}

def request(path,params):
    req=urllib.request.Request(BASE+path,data=urllib.parse.urlencode(params).encode(),headers=HEADERS)
    with urllib.request.urlopen(req,timeout=35) as response:raw=response.read()
    value=json.loads(raw)
    if value.get('error',{}).get('errorCode')!='0000' or 'resultList' not in value:
        failure=OUT/('failed_'+path.replace('.bms','')+'_'+str(params.get('strSrch',params.get('busRouteId')))+'.json')
        failure.write_bytes(raw)
        raise RuntimeError({'params':params,'keys':list(value),'error':value.get('error')})
    return raw,value

def route(name):
    rid=IDS[name];search_file=OUT/f'route_search_{rid}.json';route_file=OUT/f'route_{rid}.json'
    query=name if name[0].isdigit() else '02'
    if search_file.exists():raw=search_file.read_bytes();data=json.loads(raw)
    elif query=='02' and (OUT/'route_search_02_all.json').exists():
        raw=(OUT/'route_search_02_all.json').read_bytes();data=json.loads(raw)
    else:raw,data=request('getBusRouteList.bms',{'strSrch':query})
    found=[r for r in data['resultList'] if r['busRouteNm']==name]
    assert len(found)==1,(name,[r['busRouteNm'] for r in data['resultList']])
    meta=found[0];rid=str(meta['busRouteId'])
    (OUT/f'route_search_{rid}.json').write_bytes(raw)
    if route_file.exists():raw=route_file.read_bytes();data=json.loads(raw)
    else:raw,data=request('getRouteAndPos.bms',{'busRouteId':rid})
    (OUT/f'route_{rid}.json').write_bytes(raw)
    return {'name':name,'rid':rid,'metadata':meta,'stop_count':len(data['resultList']),
            'route_sha256':hashlib.sha256(raw).hexdigest()}

def main():
    OUT.mkdir(exist_ok=True)
    assert not (OUT/'route_metadata.json').exists(),'Preserve the completed snapshot.'
    rows=[]
    for name in NAMES:
        rows.append(route(name));time.sleep(.2)
    result={'captured_at':datetime.now(timezone(timedelta(hours=9))).isoformat(),
            'source':BASE,'route_plans_are_observed_departures':False,
            'transport_note':'Official HTTP endpoint, without TLS verification bypass; public AJAX request headers required.',
            'routes':rows}
    (OUT/'route_metadata.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    for row in rows:
        meta=row['metadata']
        print(json.dumps({'name':row['name'],'route_id':row['rid'],'headway':meta.get('term_all'),
                          'service':meta.get('tm_all'),'first':meta.get('firstBusTm'),
                          'last':meta.get('lastBusTm'),'stops':row['stop_count']},ensure_ascii=True))

if __name__=='__main__':main()
