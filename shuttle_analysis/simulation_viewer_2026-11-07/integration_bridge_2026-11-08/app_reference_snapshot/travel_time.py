"""Travel seconds have their own evidence; passenger sums are not travel times."""
import json,math,statistics,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
from road_geometry import RoadGeometry
KST=timezone(timedelta(hours=9))

class TravelTime:
    def __init__(self,path=None,geometry=None):
        self.geometry=geometry or RoadGeometry();p=Path(path) if path else Path(__file__).parent/'data/travel_history.json'
        self.data=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'speed_profiles':{}}

    def estimate(self,route,i,j,when,snapshot=None,live=False):
        snapshot=snapshot or {};road=self.geometry.leg(route,i,j)
        if not road:return {'seconds':0,'source':'geometry_unavailable','label':'도로 경로 미확인','available':False}
        pair=f"{route['id']}:{route['stops'][i]['seq']}:{route['stops'][j]['seq']}"
        measured=snapshot.get('travel_history',{}).get(pair)
        if measured and measured.get('n',0)>=5 and measured.get('days',0)>=2:
            return {'seconds':round(measured['median_seconds']),'source':'measured_history','label':'같은 방향·구간의 과거 통과 관측',
                'range_seconds':[round(measured['p10_seconds']),round(measured['p90_seconds'])],
                'range_kind':'historical_observation_spread','n':measured['n'],'days':measured['days'],'available':True}
        if route.get('kind')=='shuttle':
            seconds=road['meters']/5+max(0,j-i-1)*15
            return {'seconds':max(1,round(seconds)),'source':'shuttle_simulation_road_prior','available':True,
                'label':'실제 도로거리·기존 셔틀 시뮬레이션의 속도·정차 가정',
                'range_seconds':[round(seconds*.7),round(seconds*1.5)],'range_kind':'scenario_not_validated_interval',
                'note':'도로거리/18km/h와 중간 정류소당 15초 가정입니다. 실제 주행 완료시간을 측정한 값은 아닙니다.'}
        date=datetime.fromtimestamp(when,KST);traffic=snapshot.get('traffic',{}).get(route['id'],{})
        fresh=live and traffic.get('fetched_at') and -5<=time.time()-traffic['fetched_at']<=900 and abs(when-time.time())<=900
        seconds=0;sources=[];sample_dates=set();current=0
        parts=self.geometry.routes.get(route['id'],{}).get('segments',[])
        for k in range(i,j):
            # Seoul's section speed/distance on row k+1 describe the incoming link.
            seq=str(route['stops'][k+1]['seq']);speed=None
            if fresh:
                speed=traffic.get('sections',{}).get(seq,{}).get('speed_kmh')
                if speed is not None and not .5<=speed<=100:speed=None
            if speed is not None:sources.append('current_speed');current+=1
            else:
                learned=snapshot.get('historical_traffic',{}).get(route['id'],{})
                cell=learned.get('sections',{}).get(seq,{}) if learned.get('weekday')==date.weekday() and learned.get('hour')==date.hour else {}
                if cell.get('days',0)>=1 and .5<=cell.get('speed_kmh',0)<=100:
                    speed=cell['speed_kmh'];sources.append('historical_speed');sample_dates.update(learned.get('dates',[]))
                    seconds+=parts[k]['meters']/(speed/3.6);continue
                history=self.data.get('speed_profiles',{}).get(route['id']+':'+seq,{})
                candidates=history if isinstance(history,list) else history.get('samples',[])
                matching=[x for x in candidates if x['weekday']==date.weekday() and x['hour']==date.hour]
                chosen=matching if len({x['date'] for x in matching})>=3 else candidates
                speeds=[x['speed_kmh'] for x in chosen if .5<=x['speed_kmh']<=100]
                if speeds:
                    speed=statistics.median(speeds);sources.append('historical_speed');sample_dates.update(x['date'] for x in chosen)
                else:speed=18.;sources.append('distance_assumption')
            seconds+=parts[k]['meters']/(speed/3.6)
        source='current_section_speed' if all(x=='current_speed' for x in sources) else 'historical_section_speed' if all(x=='historical_speed' for x in sources) else 'distance_assumption' if all(x=='distance_assumption' for x in sources) else 'mixed_section_speed'
        return {'seconds':max(1,round(seconds)),'source':source,'available':True,
            'label':{'current_section_speed':'서울시 최신 구간 소통속도','historical_section_speed':'과거에 기록한 서울시 구간속도','distance_assumption':'도로거리·18km/h 가정','mixed_section_speed':'서울시 구간속도·과거 자료·미확인 구간 가정'}[source],
            'range_seconds':[max(1,round(seconds*.7)),max(1,round(seconds*1.5))],
            'range_kind':'traffic_change_scenario_not_validated_interval','current_segments':current,'total_segments':j-i,
            'history_dates':sorted(sample_dates),'observed_at':traffic.get('fetched_at') if current else None,
            'note':'구간 소통속도는 차내시간의 추정 입력입니다. 고정 정차 15초를 중복해서 더하지 않습니다.'}

def paired_arrival_time(selected,other,road_m,now):
    if not selected or not other or not selected.get('vehicle_id') or selected.get('vehicle_id')!=other.get('vehicle_id'):return None
    a,b=selected.get('provided_at'),other.get('provided_at')
    if not a or not b or abs(a-b)>60 or not all(-5<=now-t<=150 for t in (a,b)):return None
    seconds=other['departure_at']-selected['departure_at']
    if not max(1,road_m/(100/3.6))<=seconds<=max(900,road_m+600):return None
    return {'seconds':round(seconds),'source':'same_vehicle_arrival_difference','label':'같은 차량의 서울시 정류소별 도착예정 차이',
        'observed_at':min(a,b),'available':True,'note':'제공기관의 실시간 예측값 차이이며 실제 주행 완료시간 관측은 아닙니다.'}
