"""Extend the existing FIFO adapter using the retained v5 Daehak cohorts.

Morning commuter and after-midnight cohorts do not exist in the source. Those
routes explicitly use phase/headway simulations with unknown queue counts.
Night services share the daytime profile and residual queue, not copied demand.
"""
import copy,gzip,hashlib,json,math
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).parent;DATA=ROOT/'data';SOURCE=ROOT.parent/'simulation_viewer_2026-11-07/city_bus_model_2026-11-08'
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def build(target=None,source=None):
    import server
    from queue_release import stamp_model
    app=server.Application();target=Path(target) if target else DATA/'auto_queue_inputs.json';data=read(target)
    source=Path(source) if source else SOURCE
    routes={k:v for k,v in data['routes'].items() if k in ('shuttle-41841','shuttle-41946','shuttle-41914')}
    extension=read(DATA/'shuttle_model_extension.json');bundle=read(source/'prepared.json.gz');common=bundle['prepared']['common']
    if read(source/'independent_verification.json')['status']!='PASS':raise ValueError('Unverified source simulation')
    for route in app.transit.shuttle.routes:
        rid=route['id']
        if rid in routes:continue
        n=route.get('cycle_length') or len(route['stops']);stops=route['stops'][:n]
        offsets=[0.]
        for segment in extension['routes'][rid]['segments']:offsets.append(offsets[-1]+segment['seconds'])
        nodes=[{**{k:s[k] for k in ('id','name','lat','lon','board_allowed')},'city_links':[]} for s in stops]
        routes[rid]={'id':rid,'stops':nodes,'n':n,'loop':bool(route.get('cycle_length')),'offsets':offsets,
                     'anchor':next((i for i,s in enumerate(stops) if s['id']=='snu-410'),0),'capacity':route['capacity'],
                     'flows':[],'ready_flows':[],'od':{},'inflow_source':'none_commuter_or_midnight_cohort_unavailable'}
    for rid in ('shuttle-41841','shuttle-41946','shuttle-41914'):
        routes[rid]['inflow_source']='latest_audited_v5_regular';routes[rid]['cohort_range_seconds']=[680*60,1390*60]
    town=routes['shuttle-41843'];town['inflow_source']='latest_audited_v5_regular_daehak';town['cohort_range_seconds']=[680*60,1390*60]
    town['source_route_alias']='shuttle-daehak';source_totals=[];flow=defaultdict(float);packets=defaultdict(float)
    for rid in ('shuttle-41841','shuttle-41946','shuttle-41914','shuttle-41843'):routes[rid]['ready_packets']=[]
    for day,did in enumerate(('mon','tue','wed','thu','fri')):
        path=source/f'audit-regular-{did}.json.gz';audit=read(path);entered=0.;source_boarded=0.
        if audit['report']['capacity_violations']!=0:raise ValueError('Source capacity violation')
        for row in audit['wait_audit']:
            node=common['nodes'][row['node']]
            source_id=node['route'];rid='shuttle-41843' if source_id=='shuttle-daehak' else source_id
            if rid not in ('shuttle-41841','shuttle-41946','shuttle-41914','shuttle-41843') or row['ready']>common['end_second']:continue
            model=routes[rid]
            index=next((i for i,s in enumerate(model['stops']) if s['id']==node['stop_id']),None) if rid=='shuttle-41843' else node['board']
            if index is None:raise ValueError('Unmapped town boarding location')
            mass=row['weight'];second=int(row['ready']//15)*15
            exit_second=int(row['end']//15)*15 if row['outcome']!='boarded' else -1
            packets[rid,day,index,second,exit_second]+=mass
            if rid!='shuttle-41843':continue
            flow[day,index,second]+=mass;entered+=mass
            if row['outcome']=='boarded':source_boarded+=mass
        source_totals.append({'weekday':day,'conditional_ready_weight':entered,'source_modeled_boarding_weight':source_boarded})
        data['source_sha256']['town_latest_'+did]=sha(path)
    for (day,index,second),mass in sorted(flow.items()):town['ready_flows'].append([day,index,second,round(mass,9)])
    for (rid,day,index,second,exit_second),mass in sorted(packets.items()):
        routes[rid]['ready_packets'].append([day,index,second,round(mass,9),None if exit_second<0 else exit_second])
    for day in range(5):
        for i in range(town['n']):town['od'][f'{day}:{i}']=[[1,1.]]
    # One joint daily profile retains the daytime residual line for night buses.
    for rid,primary,indexes in [('shuttle-41915','shuttle-41841',[1,2]),('shuttle-41942','shuttle-41843',[1,0])]:
        routes[rid].update(profile_route_id=primary,profile_index_map=indexes,inflow_source='shared_day_night_residual_queue',
                           cohort_range_seconds=[680*60,1390*60])
    data['routes']=routes;data['schema']='all_student_shuttle_queue_v3'
    data['model'].update(algorithm_id='latest-v5-all-shuttle-clock-fifo-v3',model_only=True,historical_beta=0.,live_beta=0.)
    data['all_shuttle_extension']={'source_alias':'shuttle-daehak','source_totals':source_totals,
        'shared_night_profiles':['shuttle-41915','shuttle-41942'],'frozen_source_unchanged':True,
        'unavailable_cohorts':['morning_commuters','after_midnight'],'routing_feedback_replayed':False,
        'source_switch_exits_replayed':True,
        'note':'동일 승차지의 v5 조건부 코호트와 경로 전환 유출 시각 재사용·새 도로 시계/FIFO 재계산. 수단선택 전체 재시뮬레이션 아님.'}
    data['limitations']=[s for s in data['limitations'] if '버스 혼잡→셔틀 수요 가중치' not in s]
    data['limitations']+=['셔틀 대기는 관측 혼잡·시내버스 신호 없이 시간표와 v5 코호트/FIFO 모형으로 계산',
        '원본 모형에서 경로 전환한 가중 인원은 전환시각에 줄에서 제거·새 배차조건에서 전환행동 자체를 다시 최적화한 것은 아님',
        '등교·심야 수요 코호트 부재 노선은 배차위상 모형만 사용·줄 인원과 탑승부담은 미산출',
        '대학동은 동일 행정관/대학동 승차지 코호트 대응·도로/하차 지점 변경 후 전체 수단선택 피드백은 미재실행']
    data['limitations']=list(dict.fromkeys(data['limitations']))
    stamp_model(data)
    target.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print({'routes':len(routes),'town_ready_cells':len(town['ready_flows']),'town_weight':sum(r[3] for r in town['ready_flows']),
           'night_aliases_share_inflow':True,'model_only':True})
    return data

if __name__=='__main__':build()
