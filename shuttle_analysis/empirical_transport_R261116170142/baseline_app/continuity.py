"""Continuous, explicitly provisional service/crowd estimates between observations.

Empirical ordinal labels and simulation demand are distinct inputs. Neither
hourly passenger sums nor assumed capacities become observed crowd grades.
"""
import json,math,statistics,time
from collections import defaultdict
from datetime import datetime,timezone,timedelta
from pathlib import Path
from prediction import crowd_evidence,LABELS
from crowd_model import FEATURES

ROOT=Path(__file__).parent;KST=timezone(timedelta(hours=9))

def clip(value,lo=0.,hi=3.):return max(lo,min(hi,value))

class Continuity:
    def __init__(self,path=None):
        p=Path(path) if path else ROOT/'data/empirical_profiles.json'
        self.data=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'grades':[],'headways':[],'transitions':[],'dates':[]}
        self.rows=defaultdict(list);self.headways=defaultdict(list);self.transitions=defaultdict(list);self.cache={}
        for row in self.data['grades']:self.rows[row[1]].append(row)
        for row in self.data['headways']:self.headways[row[1]].append(row)
        for row in self.data['transitions']:self.transitions[row[1]].append(row)

    def info(self):
        return {'model_id':'continuity-v1-'+self.data.get('model_id','scenario'),
                'empirical_dates':self.data['dates'],'calibrated':False,
                'source':'완료된 날짜의 차량·회차·구간별 혼잡등급 + 마지막 관측 + 수업/과거 수요 시뮬레이션',
                'limitations':self.data.get('limitations',[]),
                'policy':'잠정 추정으로 연속 안내 · 신선한 실측 우선 · 현재 관측을 미래 지정 검색에 섞지 않음'}

    @staticmethod
    def cutoff(at,asof):return datetime.fromtimestamp(min(at,asof),KST).date().isoformat()

    def counts(self,rid,seq,at,asof,shared=None):
        d=datetime.fromtimestamp(at,KST);cut=self.cutoff(at,asof);key=(rid,str(seq),d.weekday(),d.hour,cut)
        value=(shared or {}).get(rid,{})
        if value.get('hour')==d.hour and value.get('weekday')==d.weekday() and value.get('dates') and all(day<cut for day in value['dates']):
            section=value.get('sections',{}).get(str(seq),{})
            for name,counts,minimum in [('shared_stop_hour',section.get('counts'),5),('shared_route_hour',value.get('counts'),20)]:
                if isinstance(counts,list) and len(counts)==4 and all(type(n) is int and n>=0 for n in counts) and sum(counts)>=minimum:
                    return counts,name+('_pooled_dates' if value.get('cohort')=='pooled_hour' else ''),section.get('dates',value['dates']) if name=='shared_stop_hour' else value['dates']
        if key in self.cache:return self.cache[key]
        rows=[r for r in self.rows[rid] if r[0]<cut]
        same=lambda r:datetime.fromisoformat(r[0]).weekday()==d.weekday()
        cohorts=[('same_stop_weekday_hour',[r for r in rows if str(r[2])==str(seq) and r[3]==d.hour and same(r)],5),
                 ('same_route_weekday_hour',[r for r in rows if r[3]==d.hour and same(r)],10),
                 ('same_route_hour',[r for r in rows if r[3]==d.hour],20),('other_day_route',rows,20)]
        result=([0]*4,'no_grade_observations',[])
        for name,group,minimum in cohorts:
            values=[sum(r[4+k] for r in group) for k in range(4)]
            if sum(values)>=minimum:result=(values,name,sorted({r[0] for r in group}));break
        if len(self.cache)>4000:self.cache.clear()
        self.cache[key]=result;return result

    def headway(self,rid,seq,at,asof,nominal,shared=None):
        d=datetime.fromtimestamp(at,KST);cut=self.cutoff(at,asof)
        value=(shared or {}).get(rid,{}).get(str(seq),{})
        if value.get('hour')==d.hour and value.get('weekday')==d.weekday() and value.get('n',0)>=3 and value.get('dates') and all(day<cut for day in value['dates']):
            return clip(value['median_seconds'],nominal*.5,nominal*2),'shared_saved_stop_passage_intervals',value['dates']
        rows=[r for r in self.headways[rid] if r[0]<cut and str(r[2])==str(seq) and r[3]==d.hour]
        same=[r for r in rows if datetime.fromisoformat(r[0]).weekday()==d.weekday()]
        rows=same or rows
        if rows:return clip(statistics.median(r[5] for r in rows),nominal*.5,nominal*2),'saved_section_passage_intervals',sorted({r[0] for r in rows})
        return nominal,'registered_headway',[]

    def predict_crowd(self,route,index,at,asof,evidence=None,last_section=None,live=True,shared=None):
        evidence=evidence or {};rid=route['id'];seq=route['stops'][index]['seq'];last_at=evidence.get('provided_at') if live else None
        last_grade=evidence.get('crowd_cost')
        if last_grade is None and str(evidence.get('crowd_code')) in ('3','4','5','6'):last_grade=int(evidence['crowd_code'])-3
        if evidence.get('full'):last_grade=3.
        if last_at is None or last_grade is None or not -5<=asof-last_at<=21600 or at<last_at-5:last_at=None;last_grade=None
        try:hops=int(seq)-int(last_section) if last_section is not None else 0
        except (ValueError,TypeError):hops=0
        if hops<0 or hops>16:last_at=None;last_grade=None
        if last_at and max(asof,at)-last_at<=90 and hops==0 and not evidence.get('is_proxy'):
            return crowd_evidence({**evidence,'provided_at':last_at,'crowd_cost':last_grade},asof)
        counts,cohort,dates=self.counts(rid,seq,at,asof,shared);n=sum(counts)
        # Smoothing prevents a short quiet weekend sample from claiming certainty.
        strength=min(n,20) if cohort=='other_day_route' or cohort.endswith('_pooled_dates') else n
        probability=[(v*strength/n+2)/(strength+8) if n else .25 for v in counts]
        d=datetime.fromtimestamp(at,KST);minute=(d.hour*60+d.minute)//5*5
        f=FEATURES.get(str(d.weekday()),{}).get(str(minute),{}).get(rid,{})
        term='2026-09-01'<=d.date().isoformat()<='2026-12-21' and d.weekday()<5 and d.date().isoformat() not in ('2026-09-24','2026-09-25','2026-10-05','2026-10-09','2026-10-15')
        classes=f.get('classes',0) if term else 0.;history=f.get('history') if d.weekday()<5 and 12<=d.hour<=22 and f.get('history_available',True) else None
        signals=[clip(classes,0,1)] if term else []
        if history is not None:signals.append(clip(history,0,1))
        signal=statistics.mean(signals) if signals else .5
        # Bounded ordinal likelihood tilt, a declared operating assumption, not a
        # conversion from passenger totals or manufacturer reference capacity.
        probability=[p*math.exp(.5*(signal-.5)*(k-1.5)) for k,p in enumerate(probability)]
        total=sum(probability);probability=[p/total for p in probability]
        age=max(0,at-last_at) if last_at else None
        if last_grade is not None:
            bucket=0 if hops<=3 else 1 if hops<=8 else 2
            trans=[r for r in self.transitions[rid] if r[0]<self.cutoff(at,asof) and r[2]==int(last_grade) and r[3]==bucket]
            c=[sum(r[4+k] for r in trans) for k in range(4)];nt=sum(c)
            transitioned=[(v+2)/(nt+8) for v in c] if nt>=5 and hops else [float(k==int(last_grade)) for k in range(4)]
            weight=math.exp(-age/600)*math.exp(-hops/8)
            if evidence.get('is_proxy'):weight*=.35
            probability=[(1-weight)*p+weight*q for p,q in zip(probability,transitioned)]
        mean=sum(k*p for k,p in enumerate(probability));sd=math.sqrt(sum((k-mean)**2*p for k,p in enumerate(probability)))
        uncertainty=min(1.5,.5*sd+(.35 if cohort in ('other_day_route','no_grade_observations') or cohort.endswith('_pooled_dates') else .15))
        source='observation_simulation_estimate' if last_grade is not None else 'historical_simulation_estimate' if n else 'simulation_scenario_estimate'
        return {'crowd_cost':None,'crowd_estimate':round(mean,3),'crowd_risk':max(2.5 if not n and last_grade is None else 0,clip(mean+uncertainty)),
                'crowd_uncertainty':round(uncertainty,3),'crowd_source':source,
                'crowd_label':LABELS[int(clip(round(mean)))]+' 추정' if n or last_grade is not None else '기준 혼잡위험 추정',
                'model_version':self.info()['model_id'],'calibrated':False,'observed_at':last_at,
                'age_seconds':round(asof-last_at) if last_at else None,'target_at':at,'prediction_horizon_seconds':max(0,round(at-asof)),
                'empirical_passages':n,'empirical_dates':dates,'empirical_cohort':cohort,
                'simulation_signal':{'classes':classes,'relative_history':history,'ordinal_tilt_coefficient':.5},
                'category_range':[round(clip(mean-sd),2),round(clip(mean+sd),2)],
                'prediction_note':'이전 관측·과거 혼잡등급 분포·수업/수요 신호의 잠정 결합. 등급 실측과 구분하며 평일 오차 개선은 미검증입니다.'}

    def service(self,transit,route,index,ready,observed=(),live=True,history=None):
        """A service opportunity, never a fabricated identified vehicle."""
        now=transit.now();rid=route['id'];seq=route['stops'][index]['seq'];operation=None
        if route.get('kind')=='shuttle':
            base=transit.shuttle.timetable._schedule_arrival(route,index,ready)
            if base is None:return None
            base=transit.shuttle.with_supply(route,index,base)
            nominal=(base['wait_model'].get('headway_minutes') or 20)*60
            value={**base};leave=value['departure_at'];source='shuttle_timetable_simulation'
            if getattr(transit,'automatic_queue',None):
                # The planner already evaluated this exact boarding opportunity.
                # Preserve its verified position conditioning instead of running
                # FIFO a second time on its own synthetic output.
                values=[a for a in observed if a.get('automatic_queue',{}).get('arrival_time')==ready and
                    a['automatic_queue'].get('model_id')==transit.automatic_queue.config['id']]
                if not values:
                    values=transit.automatic_queue.arrival(route,index,ready,list(observed),transit.shuttle.timetable,now,
                        getattr(transit,'plan_snapshot',transit.snapshot) if live else {},live)
                if values: value={**values[0]};leave=value['departure_at']
                elif values==[]:return None
            bounds=value.get('automatic_queue',{}).get('wait_scenario_range_seconds') or value.get('eta_window_seconds') or [0,nominal]
            bounds=[bounds[0] or 0,bounds[1] if bounds[1] is not None else nominal*3]
            closing=base.get('last_scheduled_departure_at')
            if closing is None:
                d=datetime.fromtimestamp(ready,KST)
                end=(1390 if route['stops'][index]['id']=='snu-410' else 1080) if route['provider_id']=='41841' else (1250 if route['stops'][index]['id']=='snu-101' else 1260)
                closing=d.replace(hour=end//60,minute=end%60,second=0,microsecond=0).timestamp()
        else:
            if not transit.in_service(route,ready):return None
            nominal=transit.interval(route,ready)*60
            from city_wait import history_snapshot
            history=history if history is not None else history_snapshot(transit,live)
            headway,source,dates=self.headway(rid,seq,ready,now,nominal,history.get('headway_history'));nominal=headway
            entry=transit.cache.get((rid,seq),{}) if live else {}
            prior=[a for a in entry.get('last_values',[])+entry.get('values',[]) if a.get('provided_at') and -5<=now-a['provided_at']<=21600 and datetime.fromtimestamp(a['provided_at'],KST).date()==datetime.fromtimestamp(ready,KST).date()]
            last=max(prior,key=lambda a:a['provided_at'],default=None)
            blocked=[a['departure_at'] for a in observed if a.get('full') or a['departure_at']<ready]
            queue=getattr(transit,'automatic_queue',None)
            if queue:
                operation=queue.operations.service(route,index,ready,anchor=last['departure_at'] if last else None,blocked=blocked)
            if operation:
                leave=operation['departure_at'];nominal=operation['headway_seconds'];source=operation['source']
                dates=operation['operations']['source_dates']
            elif last:
                anchor=last['departure_at'];leave=anchor+max(0,math.ceil((ready-anchor)/nominal))*nominal
                source='last_arrival_plus_'+source
            else:leave=ready+nominal/2
            if blocked and not operation:leave=max(leave,max(blocked)+nominal)
            if not transit.in_service(route,leave):return None
            bounds=[max(0,leave-ready-nominal*.5),leave-ready+nominal*.5]
            d=datetime.fromtimestamp(ready,KST);clock=route.get('last_time','235900');closing=d.replace(hour=int(clock[:2]),minute=int(clock[2:4]),second=0,microsecond=0).timestamp()
            if closing<ready:closing+=86400
            value={'departure_at':leave,'earliest_departure_at':leave,'provided_at':None,'vehicle_id':None,'full':False,
                   'arrival_source':'city_operations_estimate' if operation else 'service_history_estimate','crowd_cost':None,'crowd_label':'혼잡도 모형 추정',
                   'conditional_after_known_services':bool(last or blocked),
                   'based_on_observed_at':last['provided_at'] if last else None,'history_dates':dates,
                   'prediction_note':'이전 도착·저장 구간 통과간격·등록 배차간격 기반 예상 운행기회 · 실제 차량·출발 미확인'}
        forecast={'source':source,'generated_at':now,'ready_at':ready,'base_departure_at':leave,
                  'headway_seconds':nominal,'range_seconds':[round(max(0,bounds[0])),round(max(0,bounds[1]))],
                  'last_service_at':closing,'based_on_observed_at':value.get('based_on_observed_at'),
                  'vehicle_confirmed':False,'label':'시간표·이전 운행·시뮬레이션 추정',
                  'conditional_after_known_services':value.get('conditional_after_known_services',False),
                  'rolling':not (base.get('fixed_departure',False) if route.get('kind')=='shuttle' else False),'model_id':self.info()['model_id']}
        if route.get('kind')=='shuttle':
            forecast.update(time_basis='shuttle_schedule_model',expected_boarding_at=leave,
                next_scheduled_departure_at=base['departure_at'] if base.get('fixed_departure') else None,
                fixed_terminal_clock=base.get('fixed_departure',False),position_used_as_departure=False,
                position_clock_conditioned=value.get('automatic_queue',{}).get('live_arrival_conditioned',False),
                label='시간표·v5/FIFO 대기 모형 추정 · 셔틀 혼잡 실측 미사용')
        if route.get('kind')=='shuttle' and base.get('fixed_departure'):
            departures=[base['departure_at']];probe=departures[0]+1
            for _ in range(11):
                following=transit.shuttle.timetable._schedule_arrival(route,index,probe)
                if not following or following['departure_at']<=departures[-1]:break
                departures.append(following['departure_at']);probe=departures[-1]+1
            forecast['future_departures_at']=departures
        value['arrival_forecast']=forecast
        if operation:
            forecast.update(operations=operation['operations'],phase_conditioned=operation['phase_conditioned'],
                future_departures_at=operation['future_departures_at'],rolling=False,
                model_id=operation['operations']['model_id'],label='월요일 관측 기반 평일 운행 추정')
            value['prediction_note']='월요일 관측에서 만든 평일별 불규칙 운행시계 추정입니다. 최신 도착정보가 있으면 우선하며 실제 차량 식별값을 생성하지 않습니다.'
        return value

def shuttle_crowd(value,when):
    q=(value or {}).get('automatic_queue',{});ratio=q.get('expected_load_ratio')
    if ratio is None:
        return {'crowd_cost':None,'crowd_estimate':None,'crowd_risk':3.,'crowd_uncertainty':1.5,
                'crowd_source':'shuttle_unmeasured_prior','crowd_label':'탑승부담 미확인',
                'observed_at':None,'age_seconds':None,'target_at':when,'calibrated':False,
                'prediction_note':'이 노선·시각에 적용할 전용 대기줄·탑승부담 자료가 없어 비교에 보수적인 불확실성 비용을 적용합니다. 실측 혼잡이 아닙니다.'}
    mean=clip((ratio if ratio is not None else .5)*3)
    return {'crowd_cost':None,'crowd_estimate':round(mean,3),'crowd_risk':clip(mean+.75),
            'crowd_uncertainty':.75,'crowd_source':'shuttle_simulation_estimate','crowd_label':'탑승부담 '+('높음' if mean>=2 else '보통' if mean>=1 else '낮음')+' 추정',
            'observed_at':None,'age_seconds':None,'target_at':when,'model_version':q.get('model_id','shuttle-capacity-scenario'),
            'calibrated':False,'expected_load_ratio':ratio,'prediction_note':'수업·보행·배차·정원 시나리오의 탑승부담 추정 · 차량 혼잡등급 실측 아님'}
