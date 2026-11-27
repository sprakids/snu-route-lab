"""City boarding estimates: audited FIFO curves + separate observed full risk.

An ordinal crowd grade never becomes an observed number of seats or people.
Full-flag frequencies are a provisional binary risk, not observed queue waits.
"""
import math
from datetime import datetime
from shuttle_timetable import KST
from calculation_context import memoized

def profile(data,key,at):
    date=datetime.fromtimestamp(at,KST);minute=date.hour*60+date.minute
    if not data or key not in data.get('services',{}):return {'available':False,'reason':'outside_simulated_stops'}
    if date.weekday()>4 or not data['term_start']<=date.date().isoformat()<=data['term_end'] or date.date().isoformat() in ('2026-09-24','2026-09-25','2026-10-05','2026-10-09','2026-10-15'):
        return {'available':False,'reason':'no_class_cohort_for_date'}
    if not data['start_minute']<=minute<data['end_minute']:return {'available':False,'reason':'outside_cohort_clock'}
    rows=data['profiles'].get(f'{date.weekday()}:{key}')
    if rows is None:return {'available':False,'reason':'no_verified_profile'}
    minute=minute//5*5;row=next((r for r in rows if r[0]==minute),None)
    result={'available':not row or row[4]==0,'minute':minute,'reference_headway_seconds':data['services'][key]['reference_headway_seconds'],
        'extra_wait_seconds':row[1] if row else 0.,'expected_skipped_services':row[2] if row else 0.,
        'modeled_compatible_queue_weight':row[3] if row else 0.,'censored_phases':row[4] if row else 0,
        'unit':data['unit'],'algorithm_id':data['algorithm_id'],'external_background_passengers_included':False}
    if not result['available']:result['reason']='censored_capacity_scenario_not_served_only_average'
    return result

def full_risk(history,rid,seq,when,asof,grade=None):
    d=datetime.fromtimestamp(when,KST);cut=datetime.fromtimestamp(min(when,asof),KST).date().isoformat()
    value=history.get('crowd_history',{}).get(rid,{})
    if value.get('hour')!=d.hour or value.get('weekday')!=d.weekday() or not value.get('dates') or any(day>=cut for day in value['dates']):return {'available':False,'reason':'no_prior_binary_labels'}
    section=value.get('sections',{}).get(str(seq),{})
    for name,counts,minimum in [('stop_and_grade',section.get('availability',{}),20),('route_and_grade',value.get('availability',{}),50)]:
        pair=counts.get(str(grade)) if grade is not None else None
        if pair is None:pair=[sum(p[i] for p in counts.values()) for i in range(2)]
        full,n=pair
        if n>=minimum and 0<=full<=n:
            p=min(.95,(full+.5)/(n+1))
            return {'available':True,'probability_full':p,'expected_blocked_services':p/(1-p),'passages':n,
                'full_flag_passages':full,'dates':value['dates'],'cohort':name,'calibrated_wait':False,
                'unit':'binary_provider_full_flag_not_observed_denied_boarding'}
    return {'available':False,'reason':'insufficient_prior_binary_labels'}

def history_snapshot(transit,live):
    return getattr(transit,'plan_snapshot',{}) if live else getattr(transit,'history_snapshot',{})

def project(model,transit,route,index,ready,base,live=True,*,history=None,key=None,headway=None,pool_members=None):
    if base is None or route.get('kind')=='shuttle':return base
    now=transit.now();rid=route['id'];seq=route['stops'][index]['seq'];key=key or f'{rid}:{seq}'
    data=model.data.get('city_wait');history=history if history is not None else history_snapshot(transit,live)
    simulation=memoized('city_fifo',(id(model),key,int(ready)//300),lambda:profile(data,key,ready))
    headway=headway or (base.get('arrival_forecast') or {}).get('headway_seconds') or transit.interval(route,ready)*60
    grade=None
    if live and base.get('provided_at') is not None and -5<=now-base['provided_at']<=90:
        code=base.get('crowd_cost');grade=str(int(code)+3) if code in (0,1,2,3) else None
    empirical=full_risk(history,rid,seq,ready,now,grade)
    if key.startswith('pool:'):
        parts=[(member,full_risk(history,member['route_id'],member['seq'],ready,now)) for member in (pool_members or [])]
        if parts and all(value['available'] for member,value in parts):
            p=sum(member['probability']*value['probability_full'] for member,value in parts)
            empirical={'available':True,'probability_full':p,'expected_blocked_services':p/(1-p),
                'passages':sum(v['passages'] for m,v in parts),'calibrated_wait':False,
                'cohort':'arrival_probability_weighted_full_flags','unit':'binary_full_flags_not_queue_counts'}
        else:empirical={'available':False,'reason':'insufficient_joint_pool_binary_labels'}
    simulated=simulation['extra_wait_seconds']*headway/simulation['reference_headway_seconds'] if simulation['available'] else 0.
    measured=empirical.get('expected_blocked_services',0)*headway if empirical['available'] else 0.
    # The two risks overlap. Taking their maximum avoids adding the same lost
    # capacity twice. This policy remains provisional until held-out wait data.
    extra=round(max(simulated,measured));leave=base['departure_at']+extra
    if extra and not transit.in_service(route,leave):return None
    detail={'model_id':model.config['id'],'algorithm_id':'conditional_fifo_and_binary_full_risk_v1',
        'simulation':simulation,'empirical_full_risk':empirical,'base_departure_at':base['departure_at'],
        'expected_boarding_at':leave,'extra_wait_seconds':extra,'headway_seconds':headway,
        'observed_queue':False,'calibrated':False,'grade_to_seats_conversion':False,
        'base_conditional_after_known_services':base.get('arrival_forecast',{}).get('conditional_after_known_services',False),
        'policy':'maximum_of_overlapping_capacity_delay_estimates','queue_state_is_conditional':True}
    value={**base,'city_wait':detail}
    forecast={**base.get('arrival_forecast',{}),'expected_boarding_at':leave,'base_departure_at':leave,
        'headway_seconds':headway,'city_wait':detail,'model_id':model.config['id'],
        'vehicle_confirmed':bool(live and base.get('vehicle_id') and base.get('provided_at') is not None and -5<=now-base['provided_at']<=150)}
    bounds=forecast.get('range_seconds') or [max(0,base['departure_at']-ready)]*2
    forecast['range_seconds']=[max(0,value+extra) for value in bounds]
    value['arrival_forecast']=forecast
    if extra:
        forecast.update(vehicle_confirmed=False,source='city_conditional_fifo_estimate',conditional_after_known_services=True)
        value.update(departure_at=leave,earliest_departure_at=leave,vehicle_id=None,provided_at=None,
            arrival_source='city_queue_estimate',crowd_cost=None,crowd_label='혼잡위험 추정',full=False,
            based_on_observed_at=base.get('provided_at') or base.get('based_on_observed_at'),
            prediction_note='실험실의 정류장별 호환 FIFO·과거 만차 위험을 반영한 예상 승차시각')
    return value
