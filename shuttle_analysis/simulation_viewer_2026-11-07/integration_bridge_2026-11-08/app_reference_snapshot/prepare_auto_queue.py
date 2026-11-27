"""Compile preserved class-end + pedestrian stop-inflow data, without new API calls."""
import csv,gzip,hashlib,json,math
from collections import defaultdict
from pathlib import Path
from routing import distance

ROOT=Path(__file__).resolve().parent
MODEL={'id':'class-walk-bus-pressure-v1','step_seconds':15,'phases':[(i+.5)/8 for i in range(8)],
       'sensitivity':[{'demand':.75,'reserve':0},{'demand':1.,'reserve':.1},{'demand':1.25,'reserve':.2}],
       'historical_beta':.25,'live_beta':.25,'factor_bounds':[.75,1.25],
       'live_fresh_seconds':90,'live_max_age_seconds':600,'live_decay_seconds':180,
       'calibrated':False,'capacity_large':60,'capacity_reverse':25}

def build():
    import server
    app=server.Application();base=ROOT.parent/'scenario_comparison_2026-11-07/simulation_outputs'
    assert json.loads((base/'runner_validation.json').read_text(encoding='utf-8'))['status']=='PASS'
    assert json.loads((base/'execution_provenance.json').read_text(encoding='utf-8'))['status']=='complete'
    spec=json.loads((base/'input_snapshot/scenario_specs.json').read_text(encoding='utf-8'))
    reference=next(s for s in spec['scenarios'] if s['name']=='historical_reference')
    rho=reference['dorm_share'];q=reference['immediate_trip_share']
    shares={'dorm':rho*q,**{g:(1-rho)*q*p for g,p in zip(('snu','nak','daehak'),reference['external_mix'])}}
    prepared_path=ROOT.parent/'simulation_viewer_2026-11-07/capacity_model/prepared.json.gz'
    prepared=json.loads(gzip.decompress(prepared_path.read_bytes()))
    data={};days='월화수목금'
    for route in app.transit.shuttle.routes:
        rid=route['id'];n=route.get('cycle_length') or len(route['stops']);stops=route['stops'][:n]
        old=prepared['routes'][rid]['stops'][:n]
        assert [s['id'] for s in stops]==[s['id'] for s in old],rid
        offsets=[0.]
        for i in range(1,len(route['stops'])):
            road=app.transit.geometry.leg(route,i-1,i)
            if not road:raise ValueError('Missing road geometry: '+rid)
            offsets.append(offsets[-1]+road['meters']/5+15)
        anchor=next(i for i,s in enumerate(stops) if s['id']==('snu-410' if rid=='shuttle-41841' else 'snu-901'))
        nodes=[]
        for s in stops:
            links=[]
            for city in app.network['routes']:
                choices=[]
                for a,b in zip(city['stops'],city['stops'][1:]):
                    d=min(distance((s['lat'],s['lon']),(a['lat'],a['lon'])),distance((s['lat'],s['lon']),(b['lat'],b['lon'])))
                    if d<=450:choices.append((d,{'route_id':city['id'],'section_order':str(b['seq']),
                        'from_seq':a['seq'],'from_stop':a['id'],'to_stop':b['id']}))
                links.extend(v for d,v in sorted(choices,key=lambda pair:pair[0])[:3])
            nodes.append({**{k:s[k] for k in ('id','name','lat','lon','board_allowed')},'city_links':links})
        data[rid]={'stops':nodes,'n':n,'loop':bool(route.get('cycle_length')),'offsets':offsets,'anchor':anchor,
                   'capacity':25 if rid=='shuttle-41914' else 60,'flows':[],'od':{}}
    flows=defaultdict(float)
    with (base/'conditional_mean_bins.csv').open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            rid=row['route_id']
            if rid not in data or row['weekday'] not in days:continue
            index=next((i for i,s in enumerate(data[rid]['stops']) if s['id']==row['stop_id']),None)
            if index is None:raise ValueError('Unmapped class inflow stop')
            mass=float(row['conditional_trip_events'])*shares[row['destination_group']]
            flows[(rid,days.index(row['weekday']),index,int(row['bin_minute']))]+=mass
    for (rid,day,index,minute),mass in sorted(flows.items()):
        if mass>1e-9:data[rid]['flows'].append([day,index,minute,round(mass,9)])
    od=defaultdict(lambda:defaultdict(float))
    for day,plans in prepared['plans'].items():
        for plan in plans:
            for leg in plan[-1]:
                rid=leg['rid']
                if rid not in data:continue
                n=data[rid]['n'];i=leg['board']%n;delta=leg['alight']-leg['board']
                if delta<=0 or delta>n:raise ValueError('Invalid modeled boarding order')
                od[(rid,days.index(day),i)][delta]+=plan[3]
    for (rid,day,i),counts in od.items():
        total=math.fsum(counts.values());data[rid]['od'][f'{day}:{i}']=[[k,round(v/total,10)] for k,v in sorted(counts.items())]
    paths={'conditional_stop_inflow':base/'conditional_mean_bins.csv','class_endings':base/'input_snapshot/course_endings_current.json',
           'walk_graph':base/'input_snapshot/app/data/walking_osm.json','scenario_specs':base/'input_snapshot/scenario_specs.json',
           'representative_od':prepared_path,'validation':base/'runner_validation.json'}
    out={'schema':'auto_queue_inputs_v1','model':MODEL,'routes':data,'reference_scenario':reference,
         'course_end_events':len([e for e in json.loads(paths['class_endings'].read_text(encoding='utf-8'))
                                 if e['included_main'] and e['weekday'] in days and e['end_minute']<=1390]),
         'source_sha256':{k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in paths.items()},
         'unit':'weighted_expected_trip_events','observed_queue':False,
         'provenance':'수업 종료·건물 위치·보행망·출발 지연을 반영한 보존 10회 평균 정류장 유입. 하차 비중은 대표 반복의 경로 구성.',
         'limitations':['고유 학생·실제 줄 인원이 아님','즉시 이동50%·기숙사5772/29613·과거 목적지 비중은 참고 가정',
          '배경 탑승자는 여석 유보0~20% 가정','휴강·실제 이탈·혼잡에 따른 집단 재선택·환승 지연 전파 미관측',
          '버스 혼잡→셔틀 수요 가중치 미보정','5분 유입을15초 균등 분배·배차 위상·수요 범위는 신뢰구간 아님']}
    target=ROOT/'data/auto_queue_inputs.json';target.write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print({'model':MODEL['id'],'routes':len(data),'stops':sum(v['n'] for v in data.values()),'flow_cells':sum(len(v['flows']) for v in data.values()),'bytes':target.stat().st_size})
    return out

if __name__=='__main__':build()
