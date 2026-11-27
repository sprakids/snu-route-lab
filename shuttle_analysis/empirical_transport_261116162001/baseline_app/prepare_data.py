"""One bounded download of public walking ways and eight Seoul route definitions."""
import json
import shutil
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
KST = timezone(timedelta(hours=9))
ROUTES = [('5511','100100250'), ('5513','100100251'), ('5516','100100253'),
          ('관악02-1','120900011'), ('관악02-2','120900012'),
          ('5515','100100252'),('5528','100100263'),('6515','100100521')]

def fetch_route(pair):
    name, route_id = pair
    request = urllib.request.Request('http://m.bus.go.kr/mBus/bus/getRouteAndPos.bms',
        data=urllib.parse.urlencode({'busRouteId': route_id}).encode(),
        headers={'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'SNU-Route-Lab/0.1'})
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read()
    (DATA / 'raw' / ('route_' + route_id + '.json')).write_bytes(raw)
    payload = json.loads(raw)
    if str(payload.get('error', {}).get('errorCode')) != '0000':
        raise ValueError('Route definition unavailable: ' + name)
    stops = []
    for item in payload['resultList']:
        stops.append({'id': str(item['station']), 'seq': int(item['seq']), 'name': item['stationNm'],
            'lat': float(item['gpsY']), 'lon': float(item['gpsX']), 'ars': item.get('arsId',''),
            'segment_m': float(item.get('fullSectDist') or 0), 'direction': item.get('direction','')})
    stops.sort(key=lambda x:x['seq'])
    return {'id':route_id, 'name':name, 'stops':stops, 'source':'서울시 공식 모바일 버스정보',
            'captured_at':datetime.now(KST).isoformat()}

def main():
    (DATA / 'raw').mkdir(parents=True, exist_ok=True)
    existing=json.loads((DATA/'network.json').read_text(encoding='utf-8')) if (DATA/'network.json').exists() else {'routes':[]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        routes = list(pool.map(fetch_route, ROUTES))
    historical = json.loads((ROOT.parent/'bus_api_2026-11-04/snapshot_20261104_165101_379169/routes.json').read_text(encoding='utf-8'))
    for route in routes:
        meta = next((x for x in historical if x['busRouteId'] == route['id']),None)
        if meta is None:
            prior=next((r for r in existing['routes'] if r['id']==route['id']),None)
            if not prior:raise ValueError('Verified route metadata must be installed first: '+route['name'])
            route.update({k:v for k,v in prior.items() if k not in ('stops','id','name')})
            continue
        route.update(interval_minutes=int(meta['term']), first_time=meta['firstBusTm'][-6:],
                     last_time=meta['lastBusTm'][-6:], interval_text=meta['term_all'],
                     schedule_source_date='2026-11-04', color='#1e716a' if route['name'].startswith('관악') else '#304f90')
    (DATA/'network.json').write_text(json.dumps({'routes':routes,'captured_at':datetime.now(KST).isoformat()},ensure_ascii=False),encoding='utf-8')
    query = '[out:json][timeout:45];way["highway"](37.438,126.936,37.486,126.970);(._;>;);out body;'
    target = DATA/'walking_osm.json'
    if not target.exists():
        request = urllib.request.Request('https://overpass-api.de/api/interpreter',
            data=urllib.parse.urlencode({'data':query}).encode(), headers={'User-Agent':'SNU-Route-Lab/0.1 (local academic prototype)'})
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
        payload = json.loads(raw)
        if not payload.get('elements') or payload.get('remark'):
            raise ValueError('Incomplete OSM extraction')
        target.write_bytes(raw)
    payload = json.loads(target.read_text(encoding='utf-8'))
    (DATA/'walking_source.json').write_text(json.dumps({'retrieved_at':datetime.now(KST).isoformat(),
        'source':'OpenStreetMap contributors via Overpass API','license':'ODbL 1.0',
        'source_url':'https://www.openstreetmap.org/copyright','bbox':[37.438,126.936,37.486,126.970],
        'query':query,'osm_timestamp':payload.get('osm3s',{}).get('timestamp_osm_base'),
        'elements':len(payload['elements']),'field_validation':'교내 통행 가능성·출입구 현장 검증 전'},ensure_ascii=False,indent=2),encoding='utf-8')
    vendor = ROOT/'static/vendor'
    vendor.mkdir(parents=True,exist_ok=True)
    leaflet=ROOT/'node_modules/leaflet/dist'
    if leaflet.exists():
        for filename in ('leaflet.js','leaflet.css'):
            shutil.copy2(leaflet/filename,vendor/filename)
        shutil.copytree(leaflet/'images',vendor/'images',dirs_exist_ok=True)
        shutil.copy2(ROOT/'node_modules/leaflet/LICENSE',vendor/'LEAFLET-LICENSE')
    print(json.dumps({'routes':len(routes),'stop_occurrences':sum(len(r['stops']) for r in routes),
                      'osm_elements':len(payload['elements']),'leaflet_ready':(vendor/'leaflet.js').exists()}))

if __name__=='__main__':
    main()
