"""Published service and the prior simulation's waiting model, never live vehicles."""
from datetime import datetime,timezone,timedelta
import math

KST=timezone(timedelta(hours=9))
SOURCE='https://cse.snu.ac.kr/ko/community/notice/25464'
EXCLUDED={'2026-09-24','2026-09-25','2026-10-05','2026-10-09','2026-10-15'}

def service_day(at):
    d=datetime.fromtimestamp(at,KST)
    return d.weekday()<5 and '2026-09-01'<=d.date().isoformat()<='2026-12-21' and d.date().isoformat() not in EXCLUDED

class ShuttleTimetable:
    def __init__(self,geometry,use_queue=True):
        self.geometry=geometry
        from shuttle_waiting import WaitingScenario
        self.queue=WaitingScenario() if use_queue else None

    def arrival(self,route,index,ready):
        value=self._schedule_arrival(route,index,ready)
        if value:
            wait=max(0,round(value['departure_at']-ready));shift=wait-value['wait_seconds']
            value['wait_seconds']=wait;value['eta_window_seconds']=[max(0,x+shift) for x in value['eta_window_seconds']]
        return self.queue.apply(value,route,index,ready) if self.queue else value

    def _schedule_arrival(self,route,index,ready):
        if not service_day(ready):return None
        d=datetime.fromtimestamp(ready,KST);mid=d.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        minute=(ready-mid)/60;rid=route['provider_id'];stop=route['stops'][index]
        wait=None;fixed=False;headway=None;bounds=None;last=None
        if rid=='41841':
            campus=stop['id']=='snu-410'
            if not campus and minute>=1080:return None
            if campus and minute>=1260:
                leave=next((mid+m*60 for m in (1270,1300,1330,1360,1390) if mid+m*60>=ready),None)
                if leave is None:return None
                wait=leave-ready;bounds=[wait,wait];fixed=True
            else:
                for start,end,lo,hi in ((420,480,15,15),(480,660,3,5),(660,900,10,10),(900,1140,3,5),(1140,1200,15,15),(1200,1260,30,30)):
                    if start<=minute<end:
                        # E[H]/2, matching the prior uniform-headway simulation.
                        headway=(lo+hi)/2;wait=headway*30;bounds=[0,hi*60]
                        if minute+wait/60>=end:return self._schedule_arrival(route,index,mid+end*60)
                        break
        elif rid=='41946':
            if 480<=minute<1140:headway=6.;bounds=[0,420]
            elif 1140<=minute<1260:
                # Published last departures: gate 20:50; building 302 21:00.
                cut=1250 if stop['id']=='snu-101' else 1260
                if minute>=cut:return None
                headway=20.;bounds=[0,min(1200,(cut-minute)*60)]
            if headway:wait=min(headway*30,bounds[1])
        elif rid=='41914':
            # 302-terminal clock, with the road travel offset to this stop.
            base=index%(route.get('cycle_length') or len(route['stops']))
            road=self.geometry.leg(route,0,base) if base else None
            offset=(road['meters']/5+base*15) if road else 0
            last=mid+1030*60+offset
            leave=next((mid+m*60+offset for m in range(590,1031,20) if mid+m*60+offset>=ready),None)
            if leave is not None:wait=leave-ready;bounds=[wait,wait];fixed=True;headway=20.
        if wait is None:return None
        note=('공식 출발시간표' if fixed else '공식 배차범위·기존 균등 대기 시뮬레이션의 평균')+' 기반 추정 · 실제 출발·대기열 미확인'
        return {'departure_at':ready+round(wait),'earliest_departure_at':ready+round(wait),'provided_at':None,
            'vehicle_id':None,'full':False,'crowd_cost':None,'crowd_label':'정보 부족',
            'arrival_source':'shuttle_timetable_estimate','observed_interval':None,'observed_at_stop':False,
            'eta_window_seconds':[round(x) for x in bounds],'wait_seconds':round(wait),
            'wait_model':{'kind':'fixed_terminal_clock_with_road_offset' if fixed else 'uniform_headway_simulation_mean',
                'headway_minutes':headway,'observed_queue':False,'source_url':SOURCE,
                'simulation_source':'course_demand_2026-11-06/simulate_stop_inflow.py:wait_seconds'},
            'prediction_note':note,'source_url':SOURCE,'fixed_departure':fixed,'last_scheduled_departure_at':last}

    def info(self,at):
        return {'operating_day':service_day(at),'source_url':SOURCE,'source':'2026학년도 2학기 공식 셔틀 시간표',
            'reason':None if service_day(at) else '정규 시간표상 미운행일입니다. 주말·공휴일·학기 밖에는 시간표 차량을 만들지 않습니다.',
            'waiting_model':'공식 배차·출발시각과 기존 조건부 정원 대기모형 · 실제 줄 길이 미측정'}
