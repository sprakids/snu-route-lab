"""Published service and the prior simulation's waiting model, never live vehicles."""
from datetime import datetime,timezone,timedelta
import math
from shuttle_clock import WINDOWS,FIXED

KST=timezone(timedelta(hours=9))
SOURCE='https://cse.snu.ac.kr/ko/community/notice/25464'
EXCLUDED={'2026-09-24','2026-09-25','2026-10-05','2026-10-09','2026-10-15'}

def service_day(at):
    d=datetime.fromtimestamp(at,KST)
    return d.weekday()<5 and '2026-09-01'<=d.date().isoformat()<='2026-12-21' and d.date().isoformat() not in EXCLUDED

class ShuttleTimetable:
    def __init__(self,geometry,use_queue=True):
        self.geometry=geometry
        from simulation_travel import SimulationTravel
        self.simulation=SimulationTravel(geometry)
        from shuttle_waiting import WaitingScenario
        self.queue=WaitingScenario() if use_queue else None
        from travel_time import TravelTime
        self.travel=TravelTime(geometry=geometry);self.offset_cache={}

    def offset(self,route,index):
        key=(route['id'],index)
        if key not in self.offset_cache:
            value=self.travel.estimate(route,0,index,0) if index else {'seconds':0,'available':True}
            self.offset_cache[key]=value['seconds'] if value.get('available') else None
        return self.offset_cache[key]

    def arrival(self,route,index,ready):
        value=self._schedule_arrival(route,index,ready)
        if value:
            wait=max(0,round(value['departure_at']-ready));shift=wait-value['wait_seconds']
            value['wait_seconds']=wait;value['eta_window_seconds']=[max(0,x+shift) for x in value['eta_window_seconds']]
        return self.queue.apply(value,route,index,ready) if self.queue else value

    def _schedule_arrival(self,route,index,ready):
        rid=route['provider_id']
        if rid=='41916':return self._late_arrival(route,index,ready)
        if not service_day(ready):return None
        d=datetime.fromtimestamp(ready,KST);mid=d.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        minute=(ready-mid)/60;rid=route['provider_id'];stop=route['stops'][index]
        wait=None;fixed=False;headway=None;bounds=None;last=None
        if rid=='41841':
            campus=stop['id']=='snu-410'
            if minute>=1260:return None  # night service has its own provider 41915
            last=mid+(1260 if campus else 1080)*60
            if not campus and minute>=1080:return None
            for start,end,lo,hi in ((420,480,15,15),(480,660,3,5),(660,900,10,10),(900,1140,3,5),(1140,1200,15,15),(1200,1260,30,30)):
                if start<=minute<end:
                    headway=(lo+hi)/2;wait=min(headway*30,last-ready);bounds=[0,min(hi*60,last-ready)]
                    if minute+wait/60>=end and end<1260:return self._schedule_arrival(route,index,mid+end*60)
                    break
        elif rid=='41946':
            base=index%(route.get('cycle_length') or len(route['stops']))
            last=mid+1260*60
            if base>6:last+=self.simulation.leg_seconds(route,6,base) or 0
            elif base<6:last=mid+1250*60+(self.simulation.leg_seconds(route,0,base) or 0)
            if 480<=minute<1140:headway=6.;bounds=[0,420]
            elif 1140<=minute and ready<=last:
                # Published last departures: gate 20:50; building 302 21:00.
                headway=20.;bounds=[0,min(1200,last-ready)]
            if headway:wait=min(headway*30,bounds[1])
        elif rid=='41914':
            # 302-terminal clock, with the road travel offset to this stop.
            base=index%(route.get('cycle_length') or len(route['stops']))
            offset=self.simulation.leg_seconds(route,0,base) if base else 0.
            if offset is None:return None
            last=mid+1030*60+offset
            leave=next((mid+m*60+offset for m in range(590,1031,20) if mid+m*60+offset>=ready),None)
            if leave is not None:wait=leave-ready;bounds=[wait,wait];fixed=True;headway=20.
        elif rid=='41843':
            # Both terminals use the official 2026-2 timetable, not the
            # SNU-station shuttle's much shorter afternoon headway.
            if not stop['board_allowed'] or not 420<=minute<=1140:return None
            last=mid+1140*60
            for start,end,lo,hi in ((420,480,15,15),(480,660,6,7),(660,1140,10,10)):
                if start<=minute<end:
                    headway=(lo+hi)/2;wait=min(headway*30,last-ready)
                    bounds=[0,min(hi*60,last-ready)];break
            if minute==1140:wait=0;bounds=[0,0];fixed=True
        elif rid in ('41915','41942'):
            if stop['id']!='snu-410' or not stop['board_allowed']:return None
            last=mid+1390*60
            leave=next((mid+m*60 for m in (1270,1300,1330,1360,1390) if mid+m*60>=ready),None)
            # Keep the next published departure even across the day/night gap.
            # The planner applies its existing 3-hour arrival horizon to the
            # complete journey, so a separate wait cutoff cannot hide a service.
            if leave is None:return None
            wait=leave-ready;bounds=[wait,wait];fixed=True;headway=30.
        elif rid in ('41842','41868','41869'):
            if not stop['board_allowed']:return None
            offset=self.offset(route,index)
            if offset is None:return None
            start,end,headway=WINDOWS[rid][0];first=mid+start*60+offset;last=mid+end*60+offset
            if ready>last:return None
            wait=max(0,first-ready)+headway*30
            wait=min(wait,last-ready);bounds=[max(0,first-ready),min(max(0,first-ready)+headway*60,last-ready)]
        if wait is None:return None
        note=('공식 출발시간표' if fixed else '공식 배차범위·기존 균등 대기 시뮬레이션의 평균')+' 기반 추정 · 실제 출발·대기열 미확인'
        if rid in ('41843','41942'):note+=' · 대학동 v5 유입 코호트와 FIFO 정원 모형으로 대기를 보정합니다.'
        return {'departure_at':ready+round(wait),'earliest_departure_at':ready+round(wait),'provided_at':None,
            'vehicle_id':None,'full':False,'crowd_cost':None,'crowd_label':'정보 부족',
            'arrival_source':'shuttle_timetable_estimate','observed_interval':None,'observed_at_stop':False,
            'eta_window_seconds':[round(x) for x in bounds],'wait_seconds':round(wait),
            'wait_model':{'kind':'fixed_terminal_clock_with_road_offset' if fixed else 'uniform_headway_simulation_mean',
                'headway_minutes':headway,'observed_queue':False,'source_url':SOURCE,
                'travel_clock_model':(route.get('travel_prior') or {}).get('model_id',self.simulation.model_id),
                'simulation_source':'course_demand_2026-11-06/simulate_stop_inflow.py:wait_seconds'},
            'prediction_note':note,'source_url':SOURCE,'fixed_departure':fixed,'last_scheduled_departure_at':last}

    def _late_arrival(self,route,index,ready):
        if not route['stops'][index]['board_allowed']:return None
        offset=self.offset(route,index)
        if offset is None:return None
        d=datetime.fromtimestamp(ready,KST);mid=d.replace(hour=0,minute=0,second=0,microsecond=0).timestamp();rows=[]
        for midnight in (mid-86400,mid):
            if not service_day(midnight):continue
            rows.extend((midnight+m*60+offset,midnight) for m in FIXED['41916'] if midnight+m*60+offset>=ready)
        if not rows:return None
        leave,service_mid=min(rows);wait=leave-ready
        return {'departure_at':leave,'earliest_departure_at':leave,'provided_at':None,'vehicle_id':None,'full':False,
                'crowd_cost':None,'crowd_label':'정보 부족','arrival_source':'shuttle_timetable_estimate',
                'observed_interval':None,'observed_at_stop':False,'eta_window_seconds':[round(wait),round(wait)],'wait_seconds':round(wait),
                'wait_model':{'kind':'fixed_terminal_clock_with_road_offset','headway_minutes':30,'observed_queue':False,'source_url':SOURCE},
                'prediction_note':'공식 302동 24:00·00:30·01:00·01:30·02:00 출발 + v5 주행식의 정류소별 경과시간 · 실측 아님',
                'source_url':SOURCE,'fixed_departure':True,'service_midnight':service_mid,'last_scheduled_departure_at':service_mid+1560*60+offset}

    def info(self,at):
        late=datetime.fromtimestamp(at,KST).hour<3 and service_day(at-86400)
        return {'operating_day':service_day(at) or late,'late_previous_service_day':late,'source_url':SOURCE,'source':'2026학년도 2학기 공식 셔틀 시간표',
            'reason':None if service_day(at) or late else '정규 시간표상 미운행일입니다. 심야는 전날 운행일의 자정 이후 편으로 판단합니다.',
            'waiting_model':'시간표·v5 유입·FIFO 정원/배차위상 모형 · 셔틀 혼잡 실측 미사용 · 실제 줄 길이 미측정'}
