"""Preserve v3 inputs; add offline stop-to-destination alternatives and gate bus pool."""
from pathlib import Path
from types import SimpleNamespace
import ast,copy,gzip,hashlib,json,math,heapq
import capacity_model as base
import speed_capacity_model as speed

ROOT=Path(__file__).resolve().parent
WORK=ROOT/'adaptive_model'
SOURCE=WORK/'route_sources'
POOL_NAMES=['5511','5513','5515','5528','6515']

def load_prepared():
    p,_=base.prepare();speed.apply_speed(p);return p

def prepare():
    WORK.mkdir(exist_ok=True)
    inputs=[ROOT/'capacity_model/prepared.json.gz',ROOT/'capacity_model/speed_40_65/motion_profiles.json.gz',Path(__file__)]
    inputs+=sorted(SOURCE.glob('*.json'))
    hashes={str(p.relative_to(ROOT)):base.sha(p) for p in inputs}
    cache=WORK/'prepared.json.gz'
    if cache.exists():
        stored=json.loads(gzip.decompress(cache.read_bytes()))
        if stored['input_hashes']==hashes:return stored
    prepared=load_prepared();common=prepared['common'];routes=prepared['routes']
    road=base.read(base.OLD/'road_geometry.json')['routes'];road=copy.deepcopy(road)
    evidence=[];pool=[]
    reference=routes['100100251']
    reference_gate=next(i for i,s in enumerate(reference['stops']) if s['id']=='120000029')
    reference_end=next(i for i,s in enumerate(reference['stops']) if i>reference_gate and s['id']=='120000150')
    corridor=reference['stops'][reference_gate:reference_end+1]
    for name in POOL_NAMES:
        meta=base.read(SOURCE/f'route_search_{name}.json')['resultList'][0]
        rid=meta['busRouteId'];raw=base.read(SOURCE/f'route_{rid}.json')
        assert raw['error']['errorCode']=='0000'
        allstops=sorted(raw['resultList'],key=lambda x:int(x['seq']))
        gate=next(i for i,x in enumerate(allstops) if x['station']=='120000029')
        end=next(i for i,x in enumerate(allstops) if i>gate and x['station']=='120000150')
        relevant=allstops[gate:end+1]
        assert [x['station'] for x in relevant]==[s['id'] for s in corridor],name
        if rid not in routes:
            stops=[{'id':x['station'],'seq':int(x['seq']),'name':x['stationNm'],
                    'lat':float(x['gpsY']),'lon':float(x['gpsX']),'ars':x.get('arsId',''),
                    'segment_m':float(x.get('fullSectDist') or 0),'direction':x.get('direction','')}
                   for x in relevant]
            routes[rid]={'id':rid,'name':name,'stops':stops,'interval_minutes':float(meta['term']),
                'source':'서울시 공식 모바일 버스정보; 서울대학교→서울대입구역 부분 노선',
                'partial_route':True,'color':'#304f90'}
            road[rid]={'source':'동일한 공식 정류장 순서·도로 구간의 기존 5513 도형 재사용',
                'segments':copy.deepcopy(road['100100251']['segments'][reference_gate:reference_end])}
        r=routes[rid];i=next(i for i,s in enumerate(r['stops']) if s['id']=='120000029')
        j=next(j for j,s in enumerate(r['stops']) if j>i and s['id']=='120000150')
        pool.append((rid,i,j))
        evidence.append({'route':name,'route_id':rid,'board_stop_id':'120000029','board_ars':'21128',
            'alight_stop_id':'120000150','alight_ars':'21252','official_board_sequence':int(allstops[gate]['seq']),
            'official_alight_sequence':int(allstops[end]['seq']),'direction':allstops[gate].get('direction'),
            'weekday_headway_min':float(meta['term']),'schedule_is_observed':False})
    engine=base.module('adaptive_saved_engine',base.OLD/'engine/simulate_stop_inflow.py')
    endpoints=[p for path in common['paths'] for p in (path[0],path[-1])]
    points=endpoints+list(common['destinations'].values())+[base.point(s) for r in routes.values() for s in r['stops']]
    walker=engine.MatrixWalker(engine.WalkingGraph(base.read(base.OLD/'app/data/walking_osm.json')),points)
    planner=engine.Planner({'routes':list(routes.values())},walker,SimpleNamespace(shuttle=SimpleNamespace(available=lambda r:True)))
    campus=speed.Campus();path_keys={};walk_trees={};drive=None;profile_count=0
    def pid(kind,a=None,b=None,rid=None,i=None,j=None):
        nonlocal drive,profile_count
        key=(kind,tuple(a) if a is not None else None,tuple(b) if b is not None else None,rid,i,j)
        if key in path_keys:return path_keys[key]
        cuts=[]
        if kind=='point':pts=[list(a)]
        elif kind=='walk':
            na,_=walker.snaps[tuple(a)];nb,_=walker.snaps[tuple(b)]
            if na not in walk_trees:walk_trees[na]=walker.graph.tree(na)[1]
            parents=walk_trees[na];assert nb==na or nb in parents
            chain=[nb]
            while chain[-1]!=na:chain.append(parents[chain[-1]][0])
            pts=[list(a)]+[walker.graph.nodes[n] for n in reversed(chain)]+[list(b)]
        else:
            pts=[];st=routes[rid]['stops'];segments=road.get(rid,{}).get('segments',[])
            for k in range(i,j):
                if k<len(segments) and segments[k] and segments[k].get('geometry'):part=segments[k]['geometry']
                else:
                    if drive is None:
                        src=(base.BASE/'app/prepare_geometry.py').read_text(encoding='utf-8')
                        node=next(n for n in ast.parse(src).body if isinstance(n,ast.ClassDef) and n.name=='DriveGraph')
                        ns={'math':math,'heapq':heapq,'meters':base.distance}
                        exec(compile(ast.Module(body=[node],type_ignores=[]),'saved_drive_graph','exec'),ns)
                        drive=ns['DriveGraph'](base.read(base.BASE/'app/data/roads_osm.json'))
                    part=drive.path(base.point(st[k]),base.point(st[k+1]));assert part,(rid,k)
                if pts:assert base.distance(pts[-1],part[0])<3,(rid,k)
                pts.extend(part if not pts else part[1:]);cuts.append(len(pts)-1)
        # Keep identical consecutive vertices: stop cuts index this exact geometry.
        pts=[[round(float(x),6),round(float(y),6)] for x,y in pts]
        out=len(common['paths']);common['paths'].append(pts);path_keys[key]=out
        if kind=='bus':
            pr=speed.profile(pts,cuts,campus);common['motion_profiles'][str(out)]=pr;profile_count+=1
        return out
    def walk(a,b):
        w=walker.walk(a,b)
        return [pid('walk',a,b),float(w['seconds'])] if w else None
    def stage(rid,i,j,nextwalk):
        route=routes[rid];p=pid('bus',rid=rid,i=i,j=j)
        return {'rid':rid,'board':i,'alight':j,'ride_path':p,
                'ride_seconds':common['motion_profiles'][str(p)]['duration'],
                'wait_path':pid('point',base.point(route['stops'][i])),
                'dynamic_city':not rid.startswith('shuttle'),'city_wait':0.,'next_walk':nextwalk}
    alternatives={};gatepoint=base.point(corridor[0]);destinations=common['destinations']
    gatepaths={}
    for node,n in enumerate(common['nodes']):
        origin=[n['lat'],n['lon']]
        for dest,target in destinations.items():
            options=[];direct=walk(origin,target)
            if direct:options.append({'name':'목적지까지 도보','kind':'walk','walk':direct,'stages':[]})
            patterns=planner.patterns(origin,target,include_shuttle=True)
            # A diverse bounded set; selection ETAs below use new 40/65 profiles.
            picked=[];seen=set()
            for pat in patterns:
                first=pat['rides'][0][0]
                if first in seen:continue
                seen.add(first);picked.append(pat)
                if len(picked)>=8:break
            for pat in picked:
                rides=pat['rides'];first=routes[rides[0][0]]['stops'][rides[0][1]]
                access=walk(origin,base.point(first))
                if access is None:continue
                stages=[];valid=True
                for ri,(rid,i,j) in enumerate(rides):
                    alight=base.point(routes[rid]['stops'][j])
                    nextpoint=base.point(routes[rides[ri+1][0]]['stops'][rides[ri+1][1]]) if ri+1<len(rides) else target
                    w=walk(alight,nextpoint)
                    if w is None:valid=False;break
                    stages.append(stage(rid,i,j,w))
                if valid:options.append({'name':' / '.join(routes[r]['name'] for r,_,_ in rides),'kind':'transit','walk':access,'stages':stages})
            if dest=='snu':
                access=walk(origin,gatepoint);last=walk(base.point(corridor[-1]),target)
                if access and last:
                    poolstages=[stage(rid,i,j,last) for rid,i,j in pool]
                    options.append({'name':'서울대학교 21128 · 먼저 오는 5개 노선','kind':'gate_pool','walk':access,
                        'stages':[{**poolstages[0],'pool':poolstages}], 'gate_route_names':POOL_NAMES})
                    gatepaths[str(node)]=access[0]
            alternatives[f'{node}|{dest}']=options
        if node%10==0:print('adaptive alternatives',node,'/',len(common['nodes']),flush=True)
    # Recover each particle's existing walking-speed multiplier without a new draw.
    scales={};destination_keys={}
    for day,plans in prepared['plans'].items():
        for p in plans:
            path=common['paths'][p[5][0]];w=walker.walk(path[0],path[-1])
            scales[str(p[0])]=p[5][1]/w['seconds'] if w and w['seconds'] else 1.
            lastpid=p[6][-1]['next_walk'][0] if p[6] else p[5][0]
            endpoint=common['paths'][lastpid][-1]
            dest=min(destinations,key=lambda k:base.distance(endpoint,destinations[k]))
            assert base.distance(endpoint,destinations[dest])<5
            destination_keys[str(p[0])]=dest
    common.update(schema_version=4,adaptive_behavior=True,
        source_note='수강인원 기반 가중 모형. 대기줄 관찰 후 경로 변경 가정 포함. 실제 이동·GPS가 아닙니다.',
        queue_note='정류장 도착·60초 간격·만차 후 재판단. 예상 도착 2분 이상 개선·최대2회 변경.',
        gate_pool={'board_ars':'21128','alight_ars':'21252','routes':POOL_NAMES,'point':gatepoint},
        adaptive_settings={'recheck_seconds':60,'minimum_gain_seconds':120,'cooldown_seconds':180,'max_switches':2,
            'observed_preferences':False,'forecast':'current queue ahead + scheduled vehicles + current modeled onboard occupancy; future arrivals unknown'})
    result={'input_hashes':hashes,'prepared':prepared,'alternatives':alternatives,'walk_scales':scales,
        'destination_keys':destination_keys,'gate_routes':evidence,'gate_walk_paths':gatepaths,
        'added_motion_profiles':profile_count}
    base.packed(cache,result);base.save(WORK/'route_verification.json',{'status':'PASS','routes':evidence,
        'source':'http://m.bus.go.kr/mBus/bus/getRouteAndPos.bms','source_hashes':hashes,
        'new_city_routes_partial':True,'corridor_stop_ids':[x['id'] for x in corridor],
        'alternatives':sum(map(len,alternatives.values())),'new_speed_profiles':profile_count})
    return result

if __name__=='__main__':
    d=prepare();print('PREPARED',len(d['prepared']['common']['paths']),sum(map(len,d['alternatives'].values())),flush=True)
