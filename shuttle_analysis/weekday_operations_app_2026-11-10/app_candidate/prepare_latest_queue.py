"""Use latest audited v5 regular cohorts as a conditional queue-inflow prior.

Personal route walks use 4.8 km/h. The v5 population walk distribution is kept;
this is not a counterfactual replay in which all students walk at that speed.
No source simulation, private records, or API collectors are modified.
"""
import gzip,hashlib,json,math
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).parent;SOURCE=ROOT.parent/'simulation_viewer_2026-11-07'
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def build(target=None,source=None,*,write_features=True):
    target=Path(target) if target else ROOT/'data/auto_queue_inputs.json';result=read(target)
    source=Path(source) if source else SOURCE/'city_bus_model_2026-11-08'
    prepared_path=source/'prepared.json.gz';bundle=read(prepared_path)
    prepared=bundle['prepared'];common=prepared['common']
    operations_path=source/'city_operations.json'
    operations=read(operations_path) if operations_path.exists() else None
    if common['city_speed_revision']!='campus_stop_corridors_20261108' and not operations:
        raise ValueError('missing_city_operations')
    if operations:
        from city_operations import validate_operations
        network_path=ROOT/'data/network.json'
        validate_operations(operations,read(network_path),sha(network_path))
        if operations['revision']!=common['city_speed_revision']:raise ValueError('operations_revision')
    verification=source/'independent_verification.json'
    assert read(verification)['status']=='PASS'
    from prepare_city_queue import CityQueueBuilder
    city=CityQueueBuilder(common)
    paths={};stage_rows=[]
    for options in bundle['alternatives'].values():
        for option in options:stage_rows.extend(option['stages'])
    for plans in prepared['plans'].values():
        for p in plans:stage_rows.extend(p[6])
    for row in stage_rows:
        for s in row.get('pool',[row]):
            value=(s['rid'],s['board'],s['alight']);pid=s['ride_path']
            assert pid not in paths or paths[pid]==value,('ambiguous path',pid)
            paths[pid]=value
    flow=defaultdict(float);city_features=defaultdict(float);od=defaultdict(lambda:defaultdict(float));sources={'latest_prepared':sha(prepared_path),'latest_independent_verification':sha(verification)}
    totals=[]
    for day,did in enumerate(('mon','tue','wed','thu','fri')):
        file=source/f'audit-regular-{did}.json.gz';audit=read(file);sources['latest_regular_'+did]=sha(file)
        assert audit['report']['capacity_violations']==0
        city.add_day(day,audit)
        entered=defaultdict(float);boarded=defaultdict(float);actual_od=defaultdict(float)
        for row in audit['wait_audit']:
            choices=row['eligibility']
            if choices and row['ready']<=common['end_second']:
                for choice in choices:city_features[day,int(row['ready']//300)*5,choice[0]]+=row['weight']/len(choices)
            node=common['nodes'][row['node']];rid=node['route']
            if rid not in result['routes']:continue
            index=node['board'];r=result['routes'][rid]
            assert node['stop_id']==r['stops'][index]['id'];assert 0<=index<r['n']
            if row['ready']>common['end_second']:continue
            # Split boarding/abandonment records partition an entry's mass.
            # They are summed as weights, never counted as extra persons.
            second=int(row['ready']//15)*15;weight=row['weight']
            assert weight>=0 and math.isfinite(weight)
            flow[rid,day,index,second]+=weight;entered[rid]+=weight
            if row['outcome']=='boarded':boarded[rid]+=weight
        for packet in audit['legs']:
            for leg in packet['legs']:
                if leg[0]!=3:continue
                rid,i,j=paths[leg[3]]
                if rid not in result['routes']:continue
                n=result['routes'][rid]['n'];delta=j-i
                assert 0<delta<=n
                od[rid,day,i%n][delta]+=packet['weight'];actual_od[rid]+=packet['weight']
        for rid in result['routes']:assert abs(boarded[rid]-actual_od[rid])<1e-5,(did,rid,boarded[rid],actual_od[rid])
        totals.append({'weekday':day,'ready_entry_weight':dict(entered),'modeled_boarding_weight':dict(boarded)})
        print({'weekday':day,'status':'source mass reconciled'},flush=True)
    for rid,r in result['routes'].items():
        r['flows']=[];r['ready_flows']=[];r['od']={}
    for (rid,day,index,second),weight in sorted(flow.items()):
        result['routes'][rid]['ready_flows'].append([day,index,second,round(weight,9)])
    for (rid,day,index),counts in od.items():
        total=math.fsum(counts.values());result['routes'][rid]['od'][f'{day}:{index}']=[[k,v/total] for k,v in sorted(counts.items())]
    result['model']['id']='latest-v5-ready-inflow-v1';result['model']['step_seconds']=15
    result.update(schema='auto_queue_inputs_v2',source_sha256={**result['source_sha256'],**sources},
        provenance='검증 완료한 v5 regular 월~금 전체 가중 흐름의 승차준비시각 유입·실제 모형 승하차OD를15초 집계. 실측 줄·고유 학생 수 아님.',
        latest_simulation={'revision':common['city_speed_revision'],'scenario':'regular','independent_status':'PASS',
            'personal_walking_kmh':4.8,'population_walking_replayed_at_4p8':False,
            'population_note':'v5 기준집단 보행 분포 유지 · 개인4.8km/h 도착시각에서 줄을 조회',
            'ready_flows_include_boarding_prep':True,'preparation_added_again':False,
            'source_totals':totals,'sensitivity_feedback_replayed':False})
    result['limitations']=[s for s in result['limitations'] if '5분 유입' not in s and '정류장별 차량 시계만' not in s]
    result['limitations']+=['최신v5기준집단의조건부유입·OD · 전체집단4.8km/h 재실행아님',
        '원본v5의시내정원50/24·배경승객미포함은시나리오가정 · 실제정원아님',
        '15초유입집계오차최대7.5초 · 준비20초재가산없음',
        '24가지수요/여석민감도에서유입·OD고정 · 전체경로재선택피드백미재실행']
    result['limitations']=list(dict.fromkeys(result['limitations']))
    result['city_wait']=city.result()
    if operations:
        result['city_operations']=operations
        result['source_sha256']['city_operations']=sha(operations_path)
        result['city_wait'].update(delay_scale_policy='absolute_audited_clock',operation_revision=operations['revision'])
        result['latest_simulation']['city_operations']={k:operations[k] for k in ('schema','revision','source_dates','transfer_estimate')}
        result['provenance']='검증 완료한 평일 운행 보정 regular 월~금 가중 흐름의 승차준비시각 유입·모형 승하차OD 집계. 실측 줄·고유 학생 수 아님.'
        result['latest_simulation']['population_note']='기준집단 보행 분포 유지 · 개인4.8km/h 도착시각에서 줄을 조회'
        result['limitations'].append('월요일 관측 기반 운행을 월~금에 전이한 추정이며 다른 날짜의 예측 정확도는 미검증')
    else:result.pop('city_operations',None)
    target.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    feature_path=ROOT/'data/demand_features.json';maximum=max(city_features.values(),default=1) or 1
    historical=defaultdict(list)
    for name in ('weekday_history.json','weekday_history_extension.json'):
        h=read(ROOT/'data'/name)
        for row in h['profiles']:
            rid=h['segments'][row[0]][0]
            for day in range(5):historical[day,row[1],rid].append(row[3][day])
    means={k:math.fsum(v)/len(v) for k,v in historical.items()};hmax=max(means.values(),default=1) or 1
    routeids=[r['id'] for r in read(ROOT/'data/network.json')['routes']]
    features={str(day):{str(minute):{rid:{'history':means.get((day,minute//60,rid),0)/hmax,
        'history_available':(day,minute//60,rid) in means,'classes':city_features.get((day,minute,rid),0)/maximum} for rid in routeids}
        for minute in range(680,1390,5)} for day in range(7)}
    if write_features:feature_path.write_text(json.dumps(features,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    if write_features:(ROOT/'data/demand_features_source.json').write_text(json.dumps({'revision':common['city_speed_revision'],'scenario':'regular',
        'source_sha256':sources,'unit':'normalized modeled ready-entry weight; shared service pools divided equally',
        'observed_passengers':False,'population_walking_replayed_at_4p8':False},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print({'model':result['model']['id'],'ready_flow_cells':len(flow),'bytes':target.stat().st_size})
    if (ROOT/'data/shuttle_model_extension.json').exists():
        from prepare_shuttle_queue import build as extend_shuttles
        result=extend_shuttles(target=target,source=source)
    return result

if __name__=='__main__':build()
