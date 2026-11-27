"""Use a conditional queue scenario as a scenario, never as an observed line."""
import json,math
from pathlib import Path
from datetime import datetime,timezone,timedelta

KST=timezone(timedelta(hours=9))
class WaitingScenario:
    def __init__(self,path=None):
        p=Path(path) if path else Path(__file__).parent/'data/shuttle_waiting_scenario.json'
        self.data=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'cells':[]}
        self.cells={(r['weekday'],r['node'],r['hour']):r for r in self.data['cells']}

    def point(self,route,stop,at):
        rid=route['provider_id'];sid=stop['id'];node=None
        if rid=='41841' and sid=='snu-410':node='admin_snu'
        elif rid in ('41946','41914') and sid in ('snu-901','snu-1001'):
            node=('circle' if rid=='41946' else 'reverse')+('_302' if sid=='snu-901' else '_301')
        date=datetime.fromtimestamp(at,KST);r=self.cells.get((date.weekday(),node,date.hour))
        if not r or not r['arrival_weight'] or not r['served_weight'] or r['unserved_weight']>1e-8:return None
        extra=r['mean_capacity_extra_min']
        if extra is None or not math.isfinite(extra) or extra<0:return None
        return {'model_id':self.data['model_id'],'node':node,'weekday':date.weekday(),'hour':date.hour,
            'capacity_extra_seconds':round(extra*60),'reference_mean_seconds':round(r['mean_wait_min']*60),
            'reference_p90_seconds':round(r['p90_wait_min']*60),'reference_includes_boarding_prep_seconds':20,
            'large_capacity_assumption':60,'reverse_capacity_assumption':25,'observed_queue':False,
            'label':'정원 가정에 따른 조건부 대기 시뮬레이션 · 실측 아님',
            'scope':'해당 요일·정류소 도착시간대의 모형. 시간대 P90은 특정 출발시각의 예측구간이 아닙니다.'}

    def apply(self,arrival,route,index,ready):
        if arrival is None:return None
        # Arrival at the stop is BEFORE the separately modelled 20-second prep.
        point=self.point(route,route['stops'][index],ready-20)
        if point is None:return arrival
        extra=point['capacity_extra_seconds'];out={**arrival,'queue_model':point}
        out['next_scheduled_departure_at']=arrival['departure_at'] if arrival.get('fixed_departure') else None
        # Do not push a scenario beyond a published last departure.
        limit=23*60+10 if route['provider_id']=='41841' else 21*60 if route['provider_id']=='41946' else None
        d=datetime.fromtimestamp(arrival['departure_at']+extra,KST)
        if limit is not None and d.hour*60+d.minute>limit or arrival.get('last_scheduled_departure_at') and arrival['departure_at']+extra>arrival['last_scheduled_departure_at']:
            out['prediction_note']+=' · 막차 이후 추가 대기는 적용하지 않았으며 실제 탑승 가능 여부는 미확인'
            point['extra_applied']=False;return out
        out.update(departure_at=arrival['departure_at']+extra,earliest_departure_at=arrival['departure_at']+extra,
            wait_seconds=arrival['wait_seconds']+extra,fixed_departure=arrival.get('fixed_departure',False) and extra==0)
        out['wait_model']={**arrival['wait_model'],'kind':'timetable_plus_conditional_queue_scenario','queue_model_id':point['model_id']}
        out['prediction_note']+=' · 정원 부족 추가 대기는 기존 조건부 시뮬레이션의 시간대 평균이며 실제 줄 길이가 아닙니다.'
        point['extra_applied']=True
        return out
