"""Remaining-time decisions and FIFO capacity scenarios; never subtract cohort means."""
import math
from simulation_travel import fifo_opportunity

POLICY={'recheck_seconds':60,'minimum_gain_seconds':120,'cooldown_seconds':180,'max_switches':2,
        'assumption':True,'label':'경로 변경 시뮬레이션의 운영 가정 · 실측 적합 계수 아님'}

def boarding_key(candidate):
    if candidate.get('common_gate_service'):return 'gate-first:120000029'
    bus=next((l for l in candidate['legs'] if l['type']=='bus'),None)
    return bus['route_id']+':'+bus['station_id'] if bus else 'walk-only'

def validate_context(value,now):
    if value is None:return None
    if not isinstance(value,dict):raise ValueError('대기 비교 상태를 확인해 주세요.')
    key=value.get('current_key');count=value.get('switch_count',0);last=value.get('last_switch_at')
    abandoned=value.get('abandoned_keys',[])
    if not isinstance(key,str) or len(key)>100 or not key:raise ValueError('대기 경로를 확인해 주세요.')
    if type(count)!=int or not 0<=count<=2:raise ValueError('경로 변경 횟수를 확인해 주세요.')
    if last is not None and (not isinstance(last,(int,float)) or not math.isfinite(last) or not now-86400<=last<=now+5):raise ValueError('경로 변경 시각을 확인해 주세요.')
    if not isinstance(abandoned,list) or len(abandoned)>2 or any(not isinstance(k,str) or len(k)>100 for k in abandoned):raise ValueError('이전 대기 경로를 확인해 주세요.')
    waiting=value.get('waiting_since')
    if waiting is not None and (not isinstance(waiting,(int,float)) or not math.isfinite(waiting) or not now-86400<=waiting<=now+5):raise ValueError('정류장 도착 시각을 확인해 주세요.')
    return {'current_key':key,'switch_count':count,'last_switch_at':last,'abandoned_keys':abandoned,'waiting_since':waiting}

def decision(candidates,context,now):
    if context is None:return None
    current=min((c for c in candidates if boarding_key(c)==context['current_key']),key=lambda c:c['total_seconds'],default=None)
    allowed=[c for c in candidates if boarding_key(c) not in context['abandoned_keys'] or boarding_key(c)==context['current_key']]
    best=min(allowed,key=lambda c:(c['total_seconds'],c['crowd_risk']),default=None)
    gain=current['total_seconds']-best['total_seconds'] if current and best else None
    cooldown=max(0,math.ceil(POLICY['cooldown_seconds']-(now-context['last_switch_at']))) if context['last_switch_at'] is not None else 0
    if not best:reason='no_alternative'
    elif context['switch_count']>=POLICY['max_switches']:reason='switch_limit'
    elif cooldown:reason='cooldown'
    elif current and boarding_key(best)==context['current_key']:reason='current_fastest'
    elif current and gain<POLICY['minimum_gain_seconds']:reason='small_gain'
    else:reason='current_unavailable' if current is None else 'worth_switching'
    switch=reason in ('worth_switching','current_unavailable')
    return {'action':'suggest_switch' if switch else 'keep','reason':reason,
            'current_candidate_id':current['id'] if current else None,'recommended_candidate_id':best['id'] if best else None,
            'remaining_seconds_current':current['total_seconds'] if current else None,
            'remaining_seconds_alternative':best['total_seconds'] if best else None,'gain_seconds':gain,
            'cooldown_remaining_seconds':cooldown,'switch_count':context['switch_count'],'policy':POLICY,
            'note':'현재 위치부터 남은 시간만 비교하며 이미 기다린 시간은 다시 더하지 않습니다.'}

def queue_input(value,now):
    if value is None:return None
    if not isinstance(value,dict):raise ValueError('대기줄 입력을 확인해 주세요.')
    def number(key,lo,hi,default=None):
        n=value.get(key,default)
        if not isinstance(n,(int,float)) or isinstance(n,bool) or not math.isfinite(n) or not lo<=n<=hi:raise ValueError('대기줄·여석 입력 범위를 확인해 주세요.')
        return float(n)
    observed=number('reported_at',now-86400,now+5)
    if now-observed>90:return None
    opportunity=number('opportunity_departure_at',now-86400,now+7200)
    if opportunity<=now:return None
    vehicle=value.get('opportunity_vehicle_id')
    if vehicle is not None and (not isinstance(vehicle,str) or len(vehicle)>100):raise ValueError('다음 차량 정보를 다시 확인해 주세요.')
    rid=value.get('route_id');sid=value.get('station_id')
    if not isinstance(rid,str) or not rid.startswith('shuttle-') or len(rid)>50 or not isinstance(sid,str) or len(sid)>50:raise ValueError('셔틀 정류소를 확인해 주세요.')
    terminal=number('opportunity_terminal_dispatch_at',now-86400,now+21600) if value.get('opportunity_terminal_dispatch_at') is not None else None
    return {'route_id':rid,'station_id':sid,'reported_at':observed,'queue_ahead':number('queue_ahead',0,10000),
            'next_seats':number('next_seats',0,60) if value.get('next_seats') is not None else None,
            'next_full':value.get('next_full') is True,'source':'user_report','party_weight':1.,
            'opportunity_departure_at':opportunity,'opportunity_vehicle_id':vehicle,
            'opportunity_terminal_dispatch_at':terminal}

def fifo_departure(rows,ready,ahead,weight=1.):
    """Known current queue only; don't peek at future inflows or recycle a full vehicle."""
    return fifo_opportunity(rows,ready,ahead,weight)

def queue_arrivals(route,index,ready,observed,report,timetable,now,*,capacity_model=None):
    """Replace the hourly queue mean only for a fresh report at this waiting stop."""
    default_cap=route.get('capacity',25 if route['provider_id'] in ('41914','41869','41916') else 60)
    first=timetable._schedule_arrival(route,index,ready)
    raw=[dict(a) for a in observed if a.get('arrival_source')=='live_shuttle' and a.get('earliest_departure_at',a['departure_at'])>=ready]
    raw.sort(key=lambda a:a['departure_at'])
    frozen=report.get('opportunity_departure_at');vehicle=report.get('opportunity_vehicle_id')
    if frozen is not None:
        if frozen<=now or frozen<ready:return None
        if vehicle and (not raw or raw[0].get('vehicle_id')!=vehicle):return None
        if not vehicle and raw:return None
    if not raw and first:raw=[first]
    if raw and frozen is not None and not vehicle:
        raw[0].update(departure_at=frozen,earliest_departure_at=frozen)
        # The first opportunity is frozen by the report, not a new mean ETA.
        raw[0].pop('vehicle_supply',None)
    # Future seats are unknown. Full nominal capacity is an explicit optimistic scenario.
    while raw and len(raw)<12:
        previous=raw[-1];after=previous['departure_at']+.01
        following=timetable._schedule_arrival(route,index,after)
        if not following:break
        headway=following.get('wait_model',{}).get('headway_minutes')
        if headway and not following.get('fixed_departure'):
            after=previous['departure_at']+headway*30+.01
            following=timetable._schedule_arrival(route,index,after)
        if not following or following['departure_at']<=previous['departure_at']:break
        following['departure_at']=round(following['departure_at']);following['earliest_departure_at']=following['departure_at']
        raw.append(following)
    supplied=[]
    for n,row in enumerate(raw):
        if capacity_model:
            terminal=report.get('opportunity_terminal_dispatch_at') if n==0 else None
            clock_row={**row,'departure_at':frozen} if terminal is not None and frozen is not None else row
            supplied_row=capacity_model.with_vehicle_supply(route,index,clock_row,terminal_dispatch_at=terminal)
            row={**row,'vehicle_supply':supplied_row['vehicle_supply']} if supplied_row.get('vehicle_supply') else row
        count=(row.get('vehicle_supply') or {}).get('batch_vehicles',1)
        # Actual observed vehicles are already individual opportunities.
        count=count if row.get('arrival_source')!='live_shuttle' and not row.get('vehicle_id') else 1
        supplied.extend({**row,'batch_member':member} for member in range(count))
    raw=supplied
    for n,row in enumerate(raw):
        cap=(row.get('vehicle_supply') or {}).get('capacity',default_cap)
        seats=row.get('seats_available');at=row.get('provided_at')
        observed_seats=bool(row.get('arrival_source')=='live_shuttle' and isinstance(seats,(int,float)) and
            not isinstance(seats,bool) and math.isfinite(seats) and 0<=seats<=cap and
            isinstance(at,(int,float)) and -5<=now-at<=90)
        if n==0 and report['next_seats'] is not None:
            row['seats_available']=min(cap,report['next_seats']);row['seat_source']='user_report'
        elif observed_seats:row['seat_source']='fresh_available_seats_observation'
        else:row['seats_available']=cap;row['seat_source']='nominal_capacity_assumption'
        if n==0 and report['next_full']:row['full']=True;row['seat_source']='user_report_full'
    chosen,passed,full=fifo_departure(raw,ready,report['queue_ahead'],report['party_weight'])
    if chosen is None:return []
    cap=(chosen.get('vehicle_supply') or {}).get('capacity',default_cap)
    projection={'queue_ahead':report['queue_ahead'],'capacity_assumption':cap,'skipped_departures':passed,
        'full_departures':full,'report_age_seconds':round(now-report['reported_at']),
        'report_opportunity_departure_at':frozen,'report_opportunity_vehicle_id':vehicle,
        'unobserved_future_inflow':True,'seat_sources':[r['seat_source'] for r in raw[:passed+1]],
        'observed_queue':False,'source':'user_report_plus_capacity_scenario',
        'label':'입력한 내 앞 인원·여석과 정원 가정에 따른 FIFO 추정 · 미래 유입·후속 여석 미확인'}
    return [{**chosen,'departure_at':chosen['departure_at'],'earliest_departure_at':chosen['departure_at'],
        'arrival_source':'shuttle_queue_estimate','vehicle_id':None,'provided_at':None,'full':False,
        'crowd_cost':None,'crowd_label':'정보 부족','observed_interval':chosen.get('observed_interval'),
        'observed_at_stop':False,'eta_window_seconds':chosen.get('eta_window_seconds',[0,0]),
        'prediction_note':projection['label'],'queue_projection':projection}]
