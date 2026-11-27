"""Add official Daehak-dong day/night stops without changing frozen v5 inputs.

Stop coordinates come from the preserved SNU map routes 40/112. BUSIN's
schematic landmarks are road references, never extra passenger stops or GPS.
Only these two routes' geometry is rebuilt; other reviewed paths are retained.
"""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from prepare_geometry import DriveGraph
from road_geometry import length,meters,project,slice_path

ROOT=Path(__file__).parent;DATA=ROOT/'data'

def build():
    catalog=json.loads((DATA/'shuttle_network.json').read_text(encoding='utf-8'))
    roads=DriveGraph(json.loads((DATA/'roads_osm.json').read_text(encoding='utf-8')))
    geometry=json.loads((DATA/'road_geometry.json').read_text(encoding='utf-8'))
    city=json.loads((DATA/'network.json').read_text(encoding='utf-8'))
    city_stops={s['id']:s for r in city['routes'] for s in r['stops']}
    official={rid:json.loads((DATA/f'shuttle_live/snu_route_{rid}.json').read_text(encoding='utf-8')) for rid in (40,112)}
    # The car graph's gate exit follows a long detour. The Seoul official 5516
    # path establishes the bus corridor from campus through the gate to
    # Seoul Industrial Information School. Reuse those directed road points;
    # do not remove one-way restrictions or draw a shortcut across the gate.
    shared=next(r for r in city['routes'] if r['name']=='5516');corridor=[]
    if '서울시 공식' not in geometry['routes'][shared['id']]['source']:
        raise ValueError('The verified official shared bus corridor is required')
    for k,a in enumerate(shared['stops'][:-1]):
        if 16<=a['seq']<=19:
            part=geometry['routes'][shared['id']]['segments'][k]['geometry']
            corridor.extend(part if not corridor else part[1:])
    approach=roads.path([37.46086,126.950347],[37.465375,126.948633])
    joins=[(i,project(p,corridor)) for i,p in enumerate(approach)]
    joins=[(i,p) for i,p in joins if p['offset_m']<=3]
    if not joins:raise ValueError('No matched road join to official bus corridor')
    join,hit=joins[-1]
    def outbound(target):
        candidates=[];offset=0.
        for i,p in enumerate(corridor):
            if i:offset+=meters(corridor[i-1],p)
            if offset<hit['meters']+700 or meters(p,roads.nearest(p)[1])>3:continue
            end=roads.path(p,target)
            if end:candidates.append((offset+length(end),offset,end))
        if not candidates:raise ValueError('Unmatched official corridor endpoint')
        _,offset,end=min(candidates,key=lambda x:x[0])
        return approach[:join+1]+slice_path(corridor,hit['meters'],offset)[1:]+end[1:]
    def stop(rid,code,name,x,y,board,alight):
        row=next(s for s in official[rid]['suttle_route_path_list'] if s['bus_station_code']==code)
        return dict(name=name,x=x,y=y,stop_id=f'snu-{code}',lat=float(row['bus_station_latitude']),
                    lon=float(row['bus_station_longitude']),board_allowed=board,alight_allowed=alight,
                    coordinate_source=f'https://map.snu.ac.kr/api/bus/suttle/{rid}.action',
                    official_name=row['bus_station_name'])
    def road(name,x,y,code=None):
        point=city_stops[code] if code else {'lat':37.465375,'lon':126.948633}
        return dict(name=name,x=x,y=y,stop_id=None,lat=point['lat'],lon=point['lon'],
                    board_allowed=False,alight_allowed=False,coordinate_kind='road_reference_not_verified_stop',
                    coordinate_source='서울시 인근 정류소 좌표·기존 정문 도로 기준점',
                    coordinate_note='통과 랜드마크의 도로 기준점이며 셔틀 정차·차량 GPS 위치가 아닙니다.')
    def g(x,y):return road('관악산역',x,y,'120000058')
    def s(x,y):return road('신림중',x,y,'120000041')
    specs=[dict(id='41843',name='대학동 셔틀',short_name='대학동',color='#9a643e',loop=True,
                direction_label='행정관 ↔ 대학동',official_route_id='40',
                anchors=[stop(40,2501,'대학동 셔틀정류소',157,35,True,True),s(195,135),g(195,275),
                         stop(40,410,'행정관',157,393,True,True),g(116,275),s(116,135)]),
           dict(id='41942',name='대학동 야간 셔틀',short_name='대학동 야간',color='#775782',loop=False,
                direction_label='행정관 → 대학동 · 야간도서관',official_route_id='112',
                anchors=[stop(112,410,'행정관',157,35,True,False),road('정문',195,115),g(195,203),s(195,291),
                         stop(112,2500,'대학동 셔틀하차장',157,393,False,True),s(116,291),g(116,203),road('정문',116,115)])]
    for spec in specs:
        rid=spec['id'];spec['source_url']=f'https://web.busin.co.kr/BuslineCircleS.aspx?cd=snu_1&di={rid}&tab=F'
        spec['coordinate_note']='공식 캠퍼스맵 노선별 정류소 좌표와 BUSIN 정류소 순서입니다. 낮과 밤의 대학동 지점이 다릅니다. 도로상 승하차 위치는 현장 확인 전입니다.'
        spec['travel_prior']={'speed_kmh':18,'range_kmh':[12,25],'validated':False,'model_id':'town-road-speed-prior-v1'}
        for i,a in enumerate(spec['anchors']):a['index']=i
        outward=outbound([spec['anchors'][0 if rid=='41843' else 4]['lat'],spec['anchors'][0 if rid=='41843' else 4]['lon']])
        indices=[3,4,5,0] if rid=='41843' else [0,1,2,3,4]
        offsets=[0.]
        for i in indices[1:-1]:
            a=spec['anchors'][i];h=project([a['lat'],a['lon']],outward,minimum=offsets[-1])
            a.update(lat=h['point'][0],lon=h['point'][1],coordinate_source='서울시 5516 공식 공유 도로 구간의 랜드마크 투영점')
            offsets.append(h['meters'])
        offsets.append(length(outward))
        directed={a:slice_path(outward,lo,hi) for a,lo,hi in zip(indices,offsets,offsets[1:])}
        parts=[]
        for a,b in zip(spec['anchors'],spec['anchors'][1:]+spec['anchors'][:1]):
            poly=directed.get(a['index']) or roads.path([a['lat'],a['lon']],[b['lat'],b['lon']])
            if not poly:raise ValueError(f'Missing directed road path: {rid} {a["index"]}')
            parts.append({'geometry':poly,'meters':round(length(poly),1)})
        stops=[a for a in spec['anchors'] if a['board_allowed'] or a['alight_allowed']]
        pairs=list(zip(stops,stops[1:]+stops[:1])) if spec['loop'] else list(zip(stops,stops[1:]))
        segments=[]
        for a,b in pairs:
            poly=[];i=a['index']
            while i!=b['index']:
                part=parts[i]['geometry']
                if poly and meters(poly[-1],part[0])>3:raise ValueError('Disconnected road path')
                poly.extend(part if not poly else part[1:]);i=(i+1)%len(parts)
            segments.append({'geometry':poly,'meters':round(length(poly),1)})
        if spec['loop']:segments=(segments+segments)[:len(stops)*2-1]
        geometry['routes']['shuttle-'+rid]={'source':'서울시 5516 공식 공유 도로 구간 + OSM 접근 도로·SNU 정류소·BUSIN 순서 · 현장 검증 전',
                                          'segments':segments,'anchor_segments':parts}
        print(rid,'directed segment metres',[r['meters'] for r in segments])
    catalog['routes']=[r for r in catalog['routes'] if r['id'] not in {s['id'] for s in specs}]+specs
    catalog['town_timetable_source']='https://cse.snu.ac.kr/ko/community/notice/25464'
    catalog['town_verified_at']=datetime.now(timezone.utc).isoformat()
    geometry['version']='road-v1-'+hashlib.sha256(json.dumps(geometry['routes'],sort_keys=True,separators=(',',':')).encode()).hexdigest()[:12]
    geometry['generated_at']=datetime.now(timezone.utc).isoformat()
    for name,data in [('shuttle_network.json',catalog),('road_geometry.json',geometry)]:
        (DATA/name).write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')

if __name__=='__main__':build()
