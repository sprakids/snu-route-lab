"""Bridge all 10 published student shuttles to directed roads and v5 clocks.

The 2026-2 PDF takes precedence over older BUSIN/map route descriptions.
Frozen simulation files are never edited. New geometry gets its own kernel
replay and provenance; conditional cohorts are not observed passengers.
"""
import copy,gzip,hashlib,json,math,re,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from prepare_geometry import DriveGraph,map_extract
from road_geometry import length,meters
from simulation_kernel import kinematic_profile

ROOT=Path(__file__).parent;DATA=ROOT/'data'
SOURCE='https://cse.snu.ac.kr/ko/community/notice/25464'
MAPPING={'41841':10,'41842':70,'41843':40,'41868':120,'41869':130,'41914':81,'41946':61,'41915':92,'41942':112,'41916':140}

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def build():
    catalog=read(DATA/'shuttle_network.json');geometry=read(DATA/'road_geometry.json');frozen=read(DATA/'simulation_time_inputs.json')
    by_id={r['id']:r for r in catalog['routes']};official={}
    for rid in MAPPING.values():
        for s in read(DATA/f'shuttle_live/snu_route_{rid}.json')['suttle_route_path_list']:official[str(s['bus_station_code'])]=s
    def stop(code,name=None,board=True,alight=True):
        row=official[str(code)]
        return dict(id='snu-'+str(code),name=name or row['bus_station_name'],lat=float(row['bus_station_latitude']),lon=float(row['bus_station_longitude']),
                    board_allowed=board,alight_allowed=alight,coordinate_source='서울대 공식 캠퍼스맵 정류소')
    existing={str(a.get('stop_id','')).replace('snu-',''):a for r in catalog['routes'] for a in r['anchors'] if a.get('stop_id')}
    # The map route 70 lists an older natural-science stop; the current PDF and
    # BUSIN explicitly stop at agricultural sciences and engineering (38).
    def known(code,name=None,board=True,alight=True):
        if str(code) in official:return stop(code,name,board,alight)
        a=existing[str(code)];return dict(id='snu-'+str(code),name=name or a['name'],lat=a['lat'],lon=a['lon'],board_allowed=board,alight_allowed=alight,
                                         coordinate_source=a.get('coordinate_source','서울대 공식 캠퍼스맵 정류소'))
    new=[dict(id='41842',name='설입→제2공학관 셔틀',short_name='설입·302',color='#4f7192',
              routing_stops=[known(2401,'서울대입구역(승차)',alight=False),known(501,'농생대'),known(601,'공대(38동)'),known(901,'302동 공학관',board=False)],
              anchor_codes=[2401,None,501,601,901,None,None]),
         dict(id='41868',name='사당→행정관 셔틀',short_name='사당·행정관',color='#766247',
              routing_stops=[known(3101,'사당역(홈플러스)',alight=False),known(410,'행정관',board=False)],
              anchor_codes=[3101,None,101,410,101,1501,3301,None]),
         dict(id='41869',name='낙성대→제1공학관 셔틀',short_name='낙성대·301',color='#537b70',capacity=25,
              routing_stops=[known(3201,'낙성대 송원숯불갈비',alight=False),known(1501,'기숙사삼거리'),known(1301,'교수회관입구'),
                             known(1200,'기초과학공동기기원'),known(1101,'유전공학연구소'),known(701,'신소재공동연구소'),known(901,'302동 공학관'),known(1001,'301동 공학관',board=False)],
              anchor_codes=[3201,None,None,1501,1301,1101,701,901,1001,1101,1301,1501,None,None]),
         dict(id='41915',name='설입 야간도서관 셔틀',short_name='설입 야간',color='#7c6485',
              routing_stops=[known(410,'행정관',alight=False),known(2400,'서울대입구역(하차)',board=False)],
              anchor_codes=[410,101,None,None,2400,None,None,None,None,101]),
         dict(id='41916',name='심야 셔틀',short_name='심야',color='#595d8a',capacity=25,routing_live_compatible=False,
              routing_stops=[known(901,'302동 공학관',alight=False),known(1001,'301동 공학관'),known(711,'에너지자원신기술연구소'),
                             known(601,'공대(38동)'),known(501,'농생대'),known(401,'자연대500동'),known(101,'정문'),known(1801,'경영대'),
                             known(1700,'수의대입구'),known(1601,'국제대학원'),known(1910,'기숙사'),known(2011,'BK국제관'),
                             known(3301,'낙성대(인헌초)'),known(2401,'서울대입구역(3번출구)',board=False)],
              anchor_codes=[711,1001,901,601,501,401,101,1801,1700,1601,1910,2011,3301,2401])]
    # A narrow public OSM addition covers Sadang; no secret/API key is used.
    east=DATA/'east_map_osm.json'
    if not east.exists():
        raw=map_extract([126.965,37.467,126.986,37.486]);east.write_bytes(raw)
        east.with_suffix('.json.source.json').write_text(json.dumps({'bbox':[126.965,37.467,126.986,37.486],'sha256':sha(east),
            'received_utc':datetime.now(timezone.utc).isoformat(),'source':'OpenStreetMap API','license':'ODbL 1.0'}),encoding='utf-8')
    merged={(e['type'],e['id']):e for p in [DATA/'roads_osm.json',east] for e in read(p)['elements']}
    roads=DriveGraph({'elements':list(merged.values())})
    for spec in new:
        rid=spec['id'];html=(DATA/f'shuttle_live/page_{rid}_current.html').read_text(encoding='utf-8')
        matches=list(re.finditer(r'<span class="(route_point[^\"]*)" style="[^"]*top:\s*(\d+)px;\s*left:\s*(\d+)px;">\s*<em>(.*?)</em>',html,re.S))
        if len(matches)!=len(spec['anchor_codes']):raise ValueError('Unexpected provider schematic '+rid)
        anchors=[]
        for i,(m,code) in enumerate(zip(matches,spec.pop('anchor_codes'))):
            a=dict(index=i,x=int(m[3]),y=int(m[2]),name=re.sub('<[^>]+>','',m[4]),stop_id=None,board_allowed=False,alight_allowed=False)
            if code:
                s=known(code);a.update(lat=s['lat'],lon=s['lon'],coordinate_source=s['coordinate_source'],stop_id=s['id'],
                                     board_allowed='unstop' not in m[1],alight_allowed='unstop' not in m[1])
            anchors.append(a)
        spec.update(anchors=anchors,loop=False,official_route_id=str(MAPPING[rid]),capacity=spec.get('capacity',60),
                    direction_label=spec['name'].replace(' 셔틀',''),source_url=f'https://web.busin.co.kr/BuslineCircleS.aspx?cd=snu_1&di={rid}&tab=F',
                    timetable_source=SOURCE,coordinate_note='현재 시간표의 정차 순서를 우선합니다. 운영사 노선도는 GPS가 아니며 일부 구 노선 표기와 다릅니다.',
                    routing_live_compatible=spec.get('routing_live_compatible',True))
        if rid=='41916':spec['coordinate_note']='2026-2 시간표는 302동 출발이며 운영사 구 노선도는 에너지연구소 출발로 순서가 다릅니다. 도식 관측을 현재 경로의 GPS·출발시각으로 사용하지 않습니다.'
        stops=spec['routing_stops'];segments=[]
        for a,b in zip(stops,stops[1:]):
            if rid=='41915':poly=geometry['routes']['shuttle-41841']['segments'][1]['geometry']
            else:poly=roads.path([a['lat'],a['lon']],[b['lat'],b['lon']])
            if not poly:raise ValueError(f'Missing directed road: {rid} {a["name"]}->{b["name"]}')
            segments.append(dict(geometry=poly,meters=round(length(poly),1)))
        parts=[]
        for a,b in zip(anchors,anchors[1:]+anchors[:1]):
            poly=roads.path([a['lat'],a['lon']],[b['lat'],b['lon']]) if all('lat' in s for s in (a,b)) else None
            parts.append(dict(geometry=poly,meters=round(length(poly),1)) if poly else None)
        geometry['routes']['shuttle-'+rid]={'source':'2026-2 공식 시간표 정차 순서·공식 서울시 공유 구간/OSM 차량 도로 · 현장 확인 전',
                                          'segments':segments,'anchor_segments':parts}
        by_id[rid]=spec
        print('route',rid,'stops',len(stops),'road metres',round(sum(x['meters'] for x in segments)),flush=True)
    for spec in by_id.values():
        spec['capacity']=25 if spec['id'] in ('41914','41869','41916') else 60
        spec['arrival_policy']='timetable_and_simulation'
        spec.pop('travel_prior',None)
    catalog['routes']=[by_id[rid] for rid in ['41841','41946','41914','41843','41942','41842','41869','41868','41915','41916']]
    catalog['coverage']={'student_routes':10,'official_route_ids':[str(x) for x in MAPPING.values()],
                         'staff_only_in_student_recommendations':False,'source':SOURCE,'verified_utc':datetime.now(timezone.utc).isoformat()}
    geometry['version']='road-v1-'+hashlib.sha256(json.dumps(geometry['routes'],sort_keys=True,separators=(',',':')).encode()).hexdigest()[:12]
    extension={'schema':1,'model_id':'v5-kernel-shuttle-extension-v1','observed_operations':False,'routes':{},
               'frozen_input_sha256':sha(DATA/'simulation_time_inputs.json'),'kernel_sha256':sha(ROOT/'simulation_kernel.py'),
               'road_version':geometry['version'],'official_source':SOURCE,'note':'새 도로에서 v5 가감속·정차식 재계산. 원본 전체 수단선택 재실행·실측 검증 아님.'}
    for spec in catalog['routes']:
        rid='shuttle-'+spec['id']
        if rid in ('shuttle-41841','shuttle-41946','shuttle-41914'):continue
        parts=geometry['routes'][rid]['segments'];rows=[]
        for k,part in enumerate(parts):
            value=kinematic_profile(part['geometry'],[len(part['geometry'])-1],frozen['campus_polygon'])
            seconds=value['duration']
            if spec['id']=='41915':seconds=frozen['routes']['shuttle-41841']['segments'][1]['model_seconds']
            rows.append(dict(meters=part['meters'],seconds=seconds,geometry_sha256=hashlib.sha256(json.dumps(part['geometry'],separators=(',',':')).encode()).hexdigest()))
        base=spec.get('routing_stops') or [a for a in spec['anchors'] if a.get('lat') and (a['board_allowed'] or a['alight_allowed'])]
        sequence=[s.get('id',s.get('stop_id')) for s in (base+base if spec['loop'] else base)]
        extension['routes'][rid]={'segments':rows,'capacity':spec['capacity'],'stops':sequence}
    for file,value in [('shuttle_network.json',catalog),('road_geometry.json',geometry),('shuttle_model_extension.json',extension)]:
        (DATA/file).write_text(json.dumps(value,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    return catalog,extension

if __name__=='__main__':build()
