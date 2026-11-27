"""Prepare finite-capacity city buses from preserved v4 particles and public plans.

Manufacturer capacities are explicit reference scenarios, not verified assignments
of a particular vehicle model to a Seoul route. No observed sum is turned into seats.
"""
from pathlib import Path
from datetime import datetime
from collections import defaultdict,Counter
import copy,gzip,hashlib,json,math,re,statistics
import capacity_model as base
import speed_capacity_model as speed

ROOT=Path(__file__).resolve().parent
WORK=ROOT/'city_bus_model_2026-11-08'
SOURCE=WORK/'sources'
OUT=ROOT/'public/data/capacity_v5'


def weekday_plan(meta):
    match=re.search(r'(\d{1,2}:\d{2})\s*~\s*(\d{1,2}:\d{2})\s*\(평일\)',meta['tm_all'])
    headway=re.search(r'(\d+(?:\.\d+)?)분\(평일\)',meta['term_all'])
    assert match and headway,meta
    def seconds(value):
        h,m=map(int,value.split(':'));return h*3600+m*60
    first,last=map(seconds,match.groups())
    if last<first:last+=86400
    return {'first_seconds':first,'last_seconds':last,'headway_seconds':float(headway.group(1))*60,
            'weekday_hours':match.group(1)+' ~ '+match.group(2),'headway_minutes':float(headway.group(1))}


def planned_departures(plan):
    first,last,h=plan['first_seconds'],plan['last_seconds'],plan['headway_seconds']
    values=[first+i*h for i in range(int((last-first)//h)+1)]
    if values[-1]<last-1e-6:values.append(float(last))
    return values


def historical_profiles():
    """Empirical weekday/hour section sums; retain nulls as missing, never seats."""
    analysis=ROOT.parent
    dates=base.read(analysis/'app/data/weekday_history.json')['history_dates']
    extra=base.read(analysis/'route_expansion_2026-11-07/cached_history_new_routes.json')
    rows=defaultdict(list);sources=[];availability=Counter();all_dates=[]
    for date in dates:
        p=analysis/f'tdata_calibration_2026-11-07/collected/{date}/target_routes.json'
        sources.append({'path':p.relative_to(analysis).as_posix(),'sha256':base.sha(p)})
        records=base.read(p)+extra[date];weekday=datetime.strptime(date,'%Y%m%d').weekday()
        assert weekday<5
        all_dates.append(date)
        for record in records:
            assert record['stdrDe']==date
            key=(str(record['routeId']),int(record['staSn']),str(record['fromStaId']),str(record['toStaId']))
            for hour in range(24):
                for label,prefix in [('sum_load','a18SumLoadPsngNum'),('average','a18Num'),('maximum','maxA18Num'),('runs','a18FcntNum')]:
                    value=record.get(f'{prefix}{hour:02d}h');availability[label+('_missing' if value is None else '_present')]+=1
                value=record.get(f'a18SumLoadPsngNum{hour:02d}h')
                if value is not None:
                    value=float(value);assert math.isfinite(value) and value>=0
                    rows[(*key,weekday,hour)].append(value)
    profiles={'|'.join(map(str,k)):{'mean_sum_load':math.fsum(v)/len(v),'sample_dates':len(v)} for k,v in rows.items()}
    p=analysis/'route_expansion_2026-11-07/cached_history_new_routes.json'
    sources.append({'path':p.relative_to(analysis).as_posix(),'sha256':base.sha(p)})
    return {'profiles':profiles,'dates':all_dates,'availability':dict(availability),'sources':sources,
            'unit':'hourly directional section sum of onboard passengers across services',
            'is_individual_vehicle_load':False,'used_as_capacity_or_queue_input':False,
            'source_url':'https://t-data.seoul.go.kr/dataprovide/trafficdataviewopenapi.do?data_id=1025'}


def prepare():
    WORK.mkdir(exist_ok=True)
    dependencies=[ROOT/'adaptive_model/prepared.json.gz',ROOT/'model_snapshot/road_geometry.json',
                  ROOT/'model_snapshot/app/data/walking_osm.json',ROOT/'model_snapshot/engine/simulate_stop_inflow.py',
                  ROOT.parent/'app/data/travel_history.json',ROOT.parent/'app/data/weekday_history.json',
                  ROOT.parent/'route_expansion_2026-11-07/cached_history_new_routes.json',Path(__file__)]
    dependencies+=sorted(SOURCE.glob('route_*.json'))+[SOURCE/'manufacturer_sources.json']
    dates=base.read(ROOT.parent/'app/data/weekday_history.json')['history_dates']
    dependencies+=[ROOT.parent/f'tdata_calibration_2026-11-07/collected/{d}/target_routes.json' for d in dates]
    hashes={str(p.relative_to(ROOT.parent)):base.sha(p) for p in dependencies}
    cache=WORK/'prepared.json.gz'
    if cache.exists():
        saved=json.loads(gzip.decompress(cache.read_bytes()))
        if saved['city_input_hashes']==hashes:return saved
        raise AssertionError('City preparation inputs changed; preserve the existing cache before rebuilding.')
    bundle=json.loads(gzip.decompress((ROOT/'adaptive_model/prepared.json.gz').read_bytes()))
    prepared=bundle['prepared'];common=prepared['common'];routes=prepared['routes']
    plans_meta=base.read(SOURCE/'route_metadata.json');meta={r['rid']:r for r in plans_meta['routes']}
    reference_caps=base.read(SOURCE/'manufacturer_sources.json')['reference_capacities']
    speed_prior=base.read(ROOT.parent/'app/data/travel_history.json')
    road=base.read(ROOT/'model_snapshot/road_geometry.json')['routes']
    reference=routes['100100251'];gate=next(i for i,s in enumerate(reference['stops']) if s['id']=='120000029')
    for rid in ('100100252','100100263','100100521'):
        road[rid]={'segments':copy.deepcopy(road['100100251']['segments'][gate:gate+4])}
    # Exactly match the frozen route indexes to newly fetched official sequences.
    full={};speed_values={};speed_sources=[]
    for rid in meta:
        full[rid]=sorted(base.read(SOURCE/f'route_{rid}.json')['resultList'],key=lambda r:int(r['seq']))
        mapping={int(r['seq']):r for r in full[rid]}
        assert all(mapping[int(s['seq'])]['station']==s['id'] for s in routes[rid]['stops'])
        historical=ROOT/f'adaptive_model/route_sources/route_{rid}.json'
        if historical.exists():
            snapshot=base.read(historical)['resultList'];speed_sources.append({'path':historical.relative_to(ROOT).as_posix(),'sha256':base.sha(historical),'documented_snapshot_date':'2026-11-07'})
            for row in snapshot:
                try:value=float(row['sectSpd'])
                except (KeyError,TypeError,ValueError):continue
                if .5<=value<=100:speed_values[rid,int(row['seq'])]=value
    for key,observations in speed_prior['speed_profiles'].items():
        rid,seq=key.split(':');values=[float(o['speed_kmh']) for o in observations if .5<=float(o['speed_kmh'])<=100]
        if values:speed_values[rid,int(seq)]=statistics.median(values)
    speed_sources.extend(speed_prior['sources'])
    used=defaultdict(set);stage_catalog={}
    def remember(stages,dest,factor=1.):
        for j,st in enumerate(stages):
            for choice in st.get('pool',[st]):
                if choice['rid'].startswith('shuttle'):continue
                rid=choice['rid'];used[rid].add(choice['board'])
                ident=(rid,choice['board'],dest,tuple((s['rid'],s['board'],s['alight'],s['next_walk'][0]) for s in stages[j:]))
                if ident not in stage_catalog:
                    suffix=copy.deepcopy(stages[j:])
                    for leg in suffix:
                        leg['next_walk'][1]/=factor
                        if 'pool' in leg:
                            for candidate in leg['pool']:candidate['next_walk'][1]/=factor
                    stage_catalog[ident]=suffix
    for plans in prepared['plans'].values():
        for p in plans:remember(p[6],bundle['destination_keys'][str(p[0])],bundle['walk_scales'][str(p[0])])
    for key,options in bundle['alternatives'].items():
        dest=key.split('|',1)[1]
        for option in options:remember(option['stages'],dest)
    node_lookup={n['id']:i for i,n in enumerate(common['nodes'])}
    physical={};city_nodes=[]
    for rid in sorted(meta):
        for i in sorted(used[rid]):
            stop=routes[rid]['stops'][i];sid=stop['id']
            if sid not in physical:
                node=len(common['nodes']);physical[sid]=node
                n={'id':'city|'+sid,'route':'city','board':-1,'stop_id':sid,'ars':stop.get('ars',''),
                   'name':stop['name'],'label':stop['name']+' · 시내버스','lat':stop['lat'],'lon':stop['lon'],
                   'city':True,'services':[]}
                common['nodes'].append(n);node_lookup[n['id']]=node;city_nodes.append(node)
            common['nodes'][physical[sid]]['services'].append({'rid':rid,'board':i,'route_name':routes[rid]['name'],'seq':int(stop['seq'])})
    campus=speed.Campus();profile_fallbacks=0;city_services=[]
    def append_path(points,profile=None):
        pid=len(common['paths']);common['paths'].append([[round(float(a),6),round(float(b),6)] for a,b in points])
        if profile is not None:common['motion_profiles'][str(pid)]=profile
        return pid
    for rid in sorted(meta):
        route=routes[rid];stops=route['stops'];segments=[];offsets=[0.];segment_sources=[]
        for i,(a,b) in enumerate(zip(stops,stops[1:])):
            segment=road.get(rid,{}).get('segments',[])
            assert i<len(segment) and segment[i] and segment[i].get('geometry'),(rid,i,'missing preserved road geometry')
            points=segment[i]['geometry'];profile=speed.profile(points,[len(points)-1],campus)
            pid=append_path(points,profile);segments.append(pid)
            observed=speed_values.get((rid,int(b['seq'])))
            seconds=max(profile['duration'],profile['d'][-1]/(observed/3.6)) if observed else profile['duration']
            segment_sources.append({'speed_kmh':observed,'source':'saved_provider_section_speed' if observed else '40_65_kinematic_scenario',
                                    'applied_seconds':seconds,'kinematic_min_seconds':profile['duration']})
            offsets.append(offsets[-1]+seconds)
            if observed is None:profile_fallbacks+=1
        first_seq=int(stops[0]['seq']);prefix=0.
        for a,b in zip(full[rid],full[rid][1:]):
            if int(b['seq'])>first_seq:break
            straight=base.distance([float(a['gpsY']),float(a['gpsX'])],[float(b['gpsY']),float(b['gpsX'])])
            reported=float(b.get('fullSectDist') or 0)
            metres=reported if straight*.7<=reported<=max(300,straight*3) else straight*1.2
            kmh=speed_values.get((rid,int(b['seq'])),18.)
            prefix+=max(15.,metres/(kmh/3.6))
        vehicle_class='village' if rid.startswith('1209') else 'large'
        capacity=reference_caps[vehicle_class]['passenger_capacity'];plan=weekday_plan(meta[rid]['metadata'])
        info={'n':len(stops),'offsets':offsets,'segments':segments,'anchor':0,'city':True,
              'capacity':capacity,'origin_to_modeled_first_stop_seconds':prefix,'plan':plan,
              'segment_time_sources':segment_sources}
        common['route_info'][rid]=info
        city_services.append({'route_id':rid,'name':route['name'],**plan,'passenger_capacity':capacity,
            'capacity_reference_model':reference_caps[vehicle_class]['model'],'actual_fleet_verified':False,
            'modeled_stops':len(stops),'partial_route':bool(route.get('partial_route')),
            'first_stop':stops[0]['name'],'last_stop':stops[-1]['name'],'prefix_clock_estimate_seconds':prefix,
            'plan_source':plans_meta['source'],'plan_captured_at':plans_meta['captured_at']})
    city_lines=[];max_join_gap=0.
    for rid in sorted(meta):
        points=[]
        for pid in common['route_info'][rid]['segments']:
            part=common['paths'][pid]
            if points:
                gap=base.distance(points[-1],part[0]);max_join_gap=max(max_join_gap,gap)
                assert gap<3,(rid,gap,'preserved road segment discontinuity')
            points.extend(part if not points else part[1:])
        city_lines.append({'id':rid,'name':routes[rid]['name'],'geometry':points,
                           'color':'#536eaa' if not rid.startswith('1209') else '#33828d'})
    common['city_route_lines']=city_lines
    # Retain original walking network, 110m connector limit, and particle speed factors.
    engine=base.module('city_saved_engine',ROOT/'model_snapshot/engine/simulate_stop_inflow.py')
    graph=engine.WalkingGraph(base.read(ROOT/'model_snapshot/app/data/walking_osm.json'))
    points=[base.point(common['nodes'][n]) for n in city_nodes]+list(common['destinations'].values())
    walker=engine.MatrixWalker(graph,points);trees={};walk_count=0
    alternatives=bundle['alternatives'];alternatives=dict(alternatives)
    by_node_dest=defaultdict(list)
    for (rid,i,dest,_),stages in stage_catalog.items():
        node=physical[routes[rid]['stops'][i]['id']]
        by_node_dest[node,dest].append({'name':' / '.join(routes[s['rid']]['name'] for s in stages),
                                      'kind':'transit','walk':[None,0.],'stages':stages})
    for node in city_nodes:
        n=common['nodes'][node];origin=base.point(n);point_pid=append_path([origin])
        for dest,target in common['destinations'].items():
            options=[];walk=walker.walk(origin,target)
            if walk:
                na,_=walker.snaps[tuple(origin)];nb,_=walker.snaps[tuple(target)]
                if na not in trees:trees[na]=graph.tree(na)[1]
                parents=trees[na];chain=[nb]
                while chain[-1]!=na:chain.append(parents[chain[-1]][0])
                pts=[origin]+[graph.nodes[k] for k in reversed(chain)]+[target]
                options.append({'name':'목적지까지 도보','kind':'walk','walk':[append_path(pts),float(walk['seconds'])],'stages':[]});walk_count+=1
            seen=set()
            for option in by_node_dest[node,dest]:
                key=tuple((s['rid'],s['board'],s['alight']) for s in option['stages'])
                if key in seen:continue
                seen.add(key);option['walk'][0]=point_pid;options.append(option)
                if len(seen)>=12:break
            alternatives[f'{node}|{dest}']=options
    # Same-stop first-boardable pool is preserved as a distinct eligibility pattern.
    gate_node=physical['120000029']
    for options in bundle['alternatives'].values():
        pool=next((o for o in options if o['kind']=='gate_pool'),None)
        if pool:
            option=copy.deepcopy(pool);option['walk']=[append_path([base.point(common['nodes'][gate_node])]),0.]
            alternatives[f'{gate_node}|snu'].append(option);break
    common['hot_nodes'].update(city_gate=gate_node)
    for label,needle in [('city_302','제2공학관'),('city_301','제1공학관'),('city_admin','행정관')]:
        found=[n for n in city_nodes if needle in common['nodes'][n]['name']]
        if found:common['hot_nodes'][label]=found[0]
    for node in city_nodes:
        n=common['nodes'][node];common['hot_nodes']['city_'+n['stop_id']]=node
    history=historical_profiles()
    common.update(schema_version=5,city_capacity_applied=True,city_services=city_services,
        city_history=history,city_nodes=city_nodes,city_capacities=reference_caps,
        city_clock_note='공식 평일 첫차·막차·간격으로 재구성한 예시 시계. 실제 회차별 출발표·실차 GPS가 아닙니다.',
        city_capacity_note='제조사 제원 참고 승객정원: 일반50·마을24. 해당 노선의 실제 차종·등록정원 미확인. 외부 배경 승객은 미포함.',
        city_speed_note='저장된 제공기관 구간속도로 이동시간 보정. 사용자 최고40/65 곡선보다 빠르게 만들지 않음. 현재 실측 운행시간 아님.')
    bundle.update(city_input_hashes=hashes,prepared=prepared,alternatives=alternatives,
        city_node_lookup={f'{rid}|{i}':physical[routes[rid]['stops'][i]['id']] for rid in meta for i in used[rid]},
        city_sources={'plans':plans_meta,'manufacturer':base.read(SOURCE/'manufacturer_sources.json'),
                      'speed':speed_sources,'historical_source_files':history['sources']})
    base.packed(cache,bundle)
    report={'status':'PASS','city_routes':len(meta),'city_queue_nodes':len(city_nodes),
        'city_segments':sum(len(common['route_info'][r]['segments']) for r in meta),
        'speed_fallback_segments':profile_fallbacks,'new_walking_alternatives':walk_count,
        'road_geometry_verified':True,'official_sequence_ids_match_frozen_routes':True,
        'max_road_segment_join_gap_m':max_join_gap,
        'actual_vehicle_fleet_verified':False,'background_passengers_modeled':False,
        'history_dates':history['dates'],'history_field_availability':history['availability'],
        'observed_hourly_sum_used_as_vehicle_load':False,'input_hashes':hashes}
    base.save(WORK/'preparation_verification.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('input_hashes','history_field_availability')},ensure_ascii=True),flush=True)
    return bundle


if __name__=='__main__':prepare()
