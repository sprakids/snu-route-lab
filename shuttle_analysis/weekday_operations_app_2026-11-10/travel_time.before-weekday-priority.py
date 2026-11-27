"""Travel seconds have their own evidence; passenger sums are not travel times."""
import json,math,statistics,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
from road_geometry import RoadGeometry
from simulation_travel import SimulationTravel,modeled_speed_seconds
from calculation_context import memoized
KST=timezone(timedelta(hours=9))

class TravelTime:
    def __init__(self,path=None,geometry=None):
        self.geometry=geometry or RoadGeometry();p=Path(path) if path else Path(__file__).parent/'data/travel_history.json'
        self.data=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'speed_profiles':{}}
        self.simulation=SimulationTravel(self.geometry)
        self.operations=None
        extension=Path(__file__).parent/'data/shuttle_model_extension.json'
        self.extension=json.loads(extension.read_text(encoding='utf-8')) if extension.exists() else {'routes':{}}

    def estimate(self,route,i,j,when,snapshot=None,live=False):
        return memoized('travel',(route['id'],i,j,when,id(snapshot),live),
            lambda:self._estimate(route,i,j,when,snapshot,live))

    def _estimate(self,route,i,j,when,snapshot=None,live=False):
        snapshot=snapshot or {};road=self.geometry.leg(route,i,j)
        if not road:return {'seconds':0,'source':'geometry_unavailable','label':'도로 경로 미확인','available':False}
        pair=f"{route['id']}:{route['stops'][i]['seq']}:{route['stops'][j]['seq']}"
        measured=snapshot.get('travel_history',{}).get(pair)
        if measured and measured.get('n',0)>=5 and measured.get('days',0)>=2:
            return {'seconds':round(measured['median_seconds']),'source':'measured_history','label':'같은 방향·구간의 과거 통과 관측',
                'range_seconds':[round(measured['p10_seconds']),round(measured['p90_seconds'])],
                'range_kind':'historical_observation_spread','n':measured['n'],'days':measured['days'],'available':True}
        if route.get('kind')=='shuttle':
            seconds=self.simulation.leg_seconds(route,i,j)
            ext=self.extension['routes'].get(route['id'])
            if seconds is None and ext:
                parts=self.geometry.routes[route['id']]['segments'];model=ext['segments']
                if self.extension.get('road_version')==self.geometry.version and all(k<len(model) and parts[k] and abs(parts[k]['meters']-model[k]['meters'])<.2 and
                       route['stops'][k]['id']==ext.get('stops',[])[k] and route['stops'][k+1]['id']==ext['stops'][k+1] for k in range(i,j)):
                    seconds=sum(model[k]['seconds'] for k in range(i,j))
                    return {'seconds':max(1,round(seconds)),'source':'shuttle_extended_simulation','available':True,
                        'label':'v5 주행식·확장 도로 시뮬레이션','model_id':self.extension['model_id'],
                        'range_seconds':[round(seconds*.7),round(seconds*1.5)],'range_kind':'scenario_not_validated_interval',
                        'validated':False,'note':self.extension['note']+' 도착지 정차15초 포함·중복 가산 없음.'}
            prior=route.get('travel_prior') or {}
            if seconds is None and prior.get('model_id')=='town-road-speed-prior-v1':
                seconds=road['meters']/(prior['speed_kmh']/3.6)
                low,high=prior['range_kmh']
                return {'seconds':max(1,round(seconds)),'source':'shuttle_road_speed_assumption','available':True,
                    'label':'대학동 노선 도로거리·속도 가정','model_id':prior['model_id'],
                    'range_seconds':[round(road['meters']/(high/3.6)),round(road['meters']/(low/3.6))],
                    'range_kind':'speed_scenario_not_validated_interval','validated':False,
                    'note':'대학동 신규 노선은 도로거리·평균18km/h(범위12~25km/h) 가정입니다. 기존 v5의 검증 구간과 구분하며 이 노선의 실측 운행시간 보정은 아직 없습니다.'}
            if seconds is None:return {'seconds':0,'source':'simulation_route_unmatched','label':'셔틀 주행모형과 도로 경로 불일치','available':False}
            return {'seconds':max(1,round(seconds)),'source':'shuttle_simulation_road_prior','available':True,
                'label':'v5 도로·가감속·정차 시뮬레이션',
                'model_id':self.simulation.model_id,'input_sha256':self.simulation.sha256,
                'range_seconds':[round(seconds*.7),round(seconds*1.5)],'range_kind':'scenario_not_validated_interval',
                'note':'시뮬레이션의 정류장별 서비스 시각 차이입니다. 도착지 정차15초를 포함하며 다시 더하지 않습니다. 실측 운행시간은 아닙니다.'}
        date=datetime.fromtimestamp(when,KST);traffic=snapshot.get('traffic',{}).get(route['id'],{})
        fresh=live and traffic.get('fetched_at') and -5<=time.time()-traffic['fetched_at']<=900 and abs(when-time.time())<=900
        seconds=0;sources=[];sample_dates=set();current=0;modeled=0;guarded=0
        parts=self.geometry.routes.get(route['id'],{}).get('segments',[])
        simulation_mapping=self.simulation.mapping(route)
        operations=self.operations() if self.operations else None
        operation_segments=0
        for k in range(i,j):
            # Seoul's section speed/distance on row k+1 describe the incoming link.
            seq=str(route['stops'][k+1]['seq']);speed=None;source=None
            if fresh:
                speed=traffic.get('sections',{}).get(seq,{}).get('speed_kmh')
                if speed is not None and not .5<=speed<=100:speed=None
            if speed is not None:source='current_speed';current+=1
            else:
                learned=snapshot.get('historical_traffic',{}).get(route['id'],{})
                cell=learned.get('sections',{}).get(seq,{}) if learned.get('weekday')==date.weekday() and learned.get('hour')==date.hour else {}
                if cell.get('days',0)>=1 and .5<=cell.get('speed_kmh',0)<=100:
                    speed=cell['speed_kmh'];source='historical_speed';sample_dates.update(learned.get('dates',[]))
                else:
                    history=self.data.get('speed_profiles',{}).get(route['id']+':'+seq,{})
                    candidates=history if isinstance(history,list) else history.get('samples',[])
                    matching=[x for x in candidates if x['weekday']==date.weekday() and x['hour']==date.hour]
                    chosen=matching if len({x['date'] for x in matching})>=3 else candidates
                    speeds=[x['speed_kmh'] for x in chosen if .5<=x['speed_kmh']<=100]
                    if speeds:speed=statistics.median(speeds);source='historical_speed';sample_dates.update(x['date'] for x in chosen)
            segment=simulation_mapping.get(k,(None,None))[1]
            operation=operations.segment_seconds(route,k,when+seconds) if operations else None
            learned=snapshot.get('historical_traffic',{}).get(route['id'],{})
            multiday=source=='historical_speed' and learned.get('weekday')==date.weekday() and learned.get('hour')==date.hour and learned.get('sections',{}).get(seq,{}).get('days',0)>=2
            if source=='current_speed':value=parts[k]['meters']/(speed/3.6)
            elif operation is not None and not multiday:
                value=operation;source='weekday_transfer_operations';operation_segments+=1
            elif segment:
                modeled+=1
                if speed is None:value=segment['model_seconds'];source='v5_simulation'
                else:
                    value=modeled_speed_seconds(segment,speed)
                    guarded+=int(value>parts[k]['meters']/(speed/3.6)+1e-6)
            else:
                speed=speed if speed is not None else 18.;source=source or 'distance_assumption'
                value=parts[k]['meters']/(speed/3.6)
            sources.append(source);seconds+=value
        source='current_section_speed' if all(x=='current_speed' for x in sources) else 'weekday_transfer_operations' if all(x=='weekday_transfer_operations' for x in sources) else 'historical_section_speed' if all(x=='historical_speed' for x in sources) else 'distance_assumption' if all(x=='distance_assumption' for x in sources) else 'v5_simulation' if all(x=='v5_simulation' for x in sources) else 'mixed_section_speed'
        return {'seconds':max(1,round(seconds)),'source':source,'available':True,
            'label':{'current_section_speed':'서울시 최신 구간 소통속도','weekday_transfer_operations':'월요일 관측 기반 평일 구간시간 추정','historical_section_speed':'과거 구간속도'+('·v5 주행 제약' if modeled else ''),'distance_assumption':'미연결 구간 도로거리·18km/h 가정','v5_simulation':'v5 도로·구간속도 시뮬레이션','mixed_section_speed':'구간속도·평일 운행·기본 모형 결합'}[source],
            'range_seconds':[max(1,round(seconds*.7)),max(1,round(seconds*1.5))],
            'range_kind':'traffic_change_scenario_not_validated_interval','current_segments':current,'total_segments':j-i,
            'simulation_segments':modeled,'simulation_guarded_segments':guarded,
            'city_operations_segments':operation_segments,'city_operations':operations.info() if operation_segments else None,
            'model_id':operations.model_id if operation_segments else self.simulation.model_id if modeled else None,'input_sha256':self.simulation.sha256 if modeled else None,
            'history_dates':sorted(sample_dates),'observed_at':traffic.get('fetched_at') if current else None,
            'note':'최신 구간속도와 충분한 과거 완료시간은 우선합니다. 평일 운행 추정은 구간 진입시각의 정차 포함 총시간을 사용하며 정차를 다시 더하지 않습니다. 다른 평일로의 전이 정확도는 아직 검증하지 않았습니다.' if operation_segments else '최신 구간속도는 우선 사용합니다. 과거·미관측 입력의 일치 구간은 v5 모형을 사용하며 최종 정차가 포함된 모형에15초를 다시 더하지 않습니다. 실측 완료시간과 구분합니다.'}

def paired_arrival_time(selected,other,road_m,now):
    if not selected or not other or not selected.get('vehicle_id') or selected.get('vehicle_id')!=other.get('vehicle_id'):return None
    a,b=selected.get('provided_at'),other.get('provided_at')
    if not a or not b or abs(a-b)>60 or not all(-5<=now-t<=150 for t in (a,b)):return None
    seconds=other['departure_at']-selected['departure_at']
    if not max(1,road_m/(100/3.6))<=seconds<=max(900,road_m+600):return None
    return {'seconds':round(seconds),'source':'same_vehicle_arrival_difference','label':'같은 차량의 서울시 정류소별 도착예정 차이',
        'observed_at':min(a,b),'available':True,'note':'제공기관의 실시간 예측값 차이이며 실제 주행 완료시간 관측은 아닙니다.'}
