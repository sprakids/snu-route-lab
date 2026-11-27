"""Prepare a pinned official building catalog; never called for user searches.

Usage: python prepare_campus_places.py --source <UTF-8 official response> --receipt <download receipt>
Missing entrances use an explicitly estimated nearby public walkway, without drawing
or timing an unverified building-to-walkway connector.
"""
import argparse,hashlib,heapq,json
from collections import Counter
from pathlib import Path
from routing import WalkingGraph,distance

ROOT=Path(__file__).resolve().parent
ALIASES={'38':['글로벌공학관'],'220':['중앙교육연구동'],'62':['중앙도서관','중도'],
         '62-1':['관정도서관','관정관','관정'],'301':['신공학관1','제1공학관'],
         '302':['신공학관2','제2공학관']}

def prepare(source,receipt):
    raw=json.loads(Path(source).read_text(encoding='utf-8'));receipt=json.loads(Path(receipt).read_text(encoding='utf-8'))
    graph=WalkingGraph(json.loads((ROOT/'data/walking_osm.json').read_text(encoding='utf-8')),
                       json.loads((ROOT/'data/building_access.json').read_text(encoding='utf-8')))
    parents={n:n for n in graph.nodes}
    def find(n):
        while n!=parents[n]:parents[n]=parents[parents[n]];n=parents[n]
        return n
    for n,edges in graph.edges.items():
        for m,*_ in edges:
            a,b=find(n),find(m)
            if a!=b:parents[b]=a
    largest=Counter(find(n) for n in graph.nodes).most_common(1)[0][0]
    points=[(n,xy) for n,xy in graph.points if find(n)==largest]
    entries=[]
    for row in raw['rows']:
        lat,lon=float(row['lat_val']),float(row['lon_val']);point=(lat,lon)
        number=str(row['vil_dong_nm']).strip();name=row['inst_kor_nm'].strip();endpoint=graph.endpoint(point)
        routing_point=point
        if endpoint and find(endpoint[0])==largest:
            access_point=endpoint[2];method='mapped_entrance' if endpoint[3] else 'visible_walkway'
        else:
            choices=heapq.nsmallest(80,points,key=lambda x:distance(point,x[1]))
            nearby=next(((n,p) for n,p in choices if distance(point,p)<=100 and not graph.buildings.containing(p)),None)
            if not nearby:raise ValueError('No nearby mapped public walkway: '+number)
            _,routing_point=nearby;access_point=routing_point;method='nearby_walkway_estimate'
        gap=round(distance(point,access_point),1)
        note=(f'출입구 연결 미확인 · 건물에서 약 {round(gap)}m 떨어진 보행로부터 계산 · 실내·출입구 연결 이동 미포함'
              if method=='nearby_walkway_estimate' else
              '지도에 등록된 출입구에서 안내 · 건물 내부 이동시간 미포함' if method=='mapped_entrance' else
              '건물 대표점과 지도 보행망 기준 · 건물 내부 이동시간 미포함')
        entries.append({'id':'campus-'+row['bd_no'],'official_building_id':row['bd_no'],'number':number,
            'name':name,'label':f'{number}동 · {name}','english_name':(row.get('inst_eng_nm') or '').strip(),
            'aliases':ALIASES.get(number,[]),'lat':lat,'lon':lon,'kind':'official_campus_building',
            'routing_point':{'lat':routing_point[0],'lon':routing_point[1]},
            'access':{'method':method,'lat':access_point[0],'lon':access_point[1],
                      'representative_to_access_m':gap,'entrance_field_verified':False,
                      'indoor_time_included':False,'unverified_connector_drawn':False,'note':note}})
    entries.sort(key=lambda x:tuple(int(p) for p in x['number'].split('-')))
    return {'version':'snu-building-catalog-v1','source':{**receipt,'title':'서울대학교 공식 캠퍼스맵',
        'attribution':'건물 번호·이름·대표 좌표: 서울대학교 캠퍼스맵; 보행망·출입구: OpenStreetMap contributors',
        'map_url':'https://map.snu.ac.kr/web/main.action'},'scope':'관악캠퍼스',
        'graph_sha256':{n:hashlib.sha256((ROOT/'data'/n).read_bytes()).hexdigest() for n in ['walking_osm.json','building_access.json']},
        'access_counts':dict(Counter(x['access']['method'] for x in entries)),
        'approximation_policy':'출입구 연결 미확인 시 건물 대표점 100m 이내의 지도상 공용 보행로에서 계산. 미확인 연결선과 실내 이동시간을 생성하지 않음.',
        'alias_sources':['https://snu.ac.kr/campuslife/facilities/amenities',
                         'https://cse.snu.ac.kr/api/v1/file/1712387520810_CSE_Brochure.pdf'],
        'buildings':entries}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--receipt',required=True);a=p.parse_args()
    data=prepare(a.source,a.receipt);(ROOT/'data/campus_places.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print('Prepared',len(data['buildings']),'official buildings:',data['access_counts'])
