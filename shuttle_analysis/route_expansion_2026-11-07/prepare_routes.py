"""Bounded official metadata download. Never print keys or signed URLs."""
from pathlib import Path
from datetime import datetime, timezone
import json, sys, urllib.request, urllib.parse, hashlib, shutil

ROOT=Path(__file__).resolve().parent
APP=ROOT.parent/'app'
sys.path.insert(0,str(APP))
import server
from prepare_geometry import stop_offsets
from road_geometry import slice_path,length

def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def main():
    key=urllib.parse.unquote(server.secret('SEOUL_BUS_SERVICE_KEY') or server.saved_bus_key() or '')
    assert key,'Backend key unavailable'
    ledger_path=ROOT/'metadata_request_ledger.json'
    ledger=json.loads(ledger_path.read_text(encoding='utf-8')) if ledger_path.exists() else []
    def request(operation,params,filename):
        target=ROOT/'sources'/filename
        if target.exists():return json.loads(target.read_text(encoding='utf-8'))
        ledger.append({'operation':operation,'parameters':params,'reserved_before_request':True})
        dump(ROOT/'metadata_request_ledger.json',ledger)
        url='http://ws.bus.go.kr/api/rest/busRouteInfo/'+operation+'?'+urllib.parse.urlencode({'serviceKey':key,'resultType':'json',**params})
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'SNU-Route-Lab/0.7 academic prototype'}),timeout=20) as response:raw=response.read(8_000_001)
        except Exception as e:raise RuntimeError('Metadata request failed: '+type(e).__name__) from None
        assert len(raw)<=8_000_000 and key.encode() not in raw
        doc=json.loads(raw)
        assert str(doc.get('msgHeader',{}).get('headerCd'))=='0','Provider metadata rejected'
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        return doc
    def rows(doc):
        value=(doc.get('msgBody') or {}).get('itemList') or []
        return [value] if isinstance(value,dict) else value
    additions=[];paths={};evidence=[]
    for name in ('5515','5528','6515'):
        candidates=rows(request('getBusRouteList',{'strSrch':name},name+'-search.json'))
        match=[r for r in candidates if r.get('busRouteNm')==name]
        assert len(match)==1,'Route name is ambiguous: '+name
        rid=str(match[0]['busRouteId'])
        stops=[]
        for item in rows(request('getStaionByRoute',{'busRouteId':rid},name+'-stops.json')):
            stops.append({'id':str(item['station']),'seq':int(item['seq']),'name':item['stationNm'],
                'lat':float(item['gpsY']),'lon':float(item['gpsX']),'ars':item.get('arsId',''),
                'segment_m':float(item.get('fullSectDist') or 0),'direction':item.get('direction','')})
        stops.sort(key=lambda s:s['seq'])
        metadata=rows(request('getRouteInfo',{'busRouteId':rid},name+'-info.json'))[0]
        route={'id':rid,'name':name,'stops':stops,'source':'서울시 공식 노선정보조회 getStaionByRoute',
               'captured_at':datetime.now(timezone.utc).isoformat(),'interval_minutes':int(metadata.get('term') or 15),
               'first_time':str(metadata.get('firstBusTm',''))[-6:],'last_time':str(metadata.get('lastBusTm',''))[-6:],
               'interval_text':str(metadata.get('term') or ''),'schedule_source_date':'2026-11-07','color':'#304f90'}
        rawpath=rows(request('getRoutePath',{'busRouteId':rid},name+'-path.json'))
        rawpath.sort(key=lambda r:int(r.get('no',0)))
        poly=[[float(r['gpsY']),float(r['gpsX'])] for r in rawpath]
        offsets=stop_offsets(poly,stops)
        segments=[]
        for start,end in zip(offsets,offsets[1:]):
            part=slice_path(poly,start,end)
            segments.append({'geometry':part,'meters':round(length(part),1)})
        paths[rid]={'source':'서울시 공식 노선정보조회 getRoutePath','segments':segments}
        gates=[(i,s) for i,s in enumerate(stops) if s['name']=='서울대학교']
        alternatives=[]
        for i,s in gates:
            destinations=[v for v in stops[i+1:] if '서울대입구역' in v['name']]
            if destinations and destinations[0].get('direction')==s.get('direction') and destinations[0]['seq']-s['seq']<=12:
                alternatives.append({'boarding_stop':s,'alighting_stop':destinations[0]})
        evidence.append({'route':name,'route_id':rid,'stops':len(stops),'verified_gate_to_station':alternatives})
        additions.append(route)
    assert len({r['id'] for r in additions})==3
    dump(ROOT/'prepared_routes.json',{'routes':additions})
    dump(ROOT/'prepared_paths.json',paths)
    dump(ROOT/'route_verification.json',{'source':'Seoul official route API','routes':evidence,'metadata_requests':len(ledger)})
    for item in evidence:print(json.dumps(item,ensure_ascii=False))

if __name__=='__main__':main()
