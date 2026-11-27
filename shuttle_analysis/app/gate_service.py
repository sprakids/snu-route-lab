"""A common-line service at 21128. Observed first bus, or explicit uniform residuals."""
from copy import deepcopy
from strategies import GATE_STOP,STATION_STOP,GATE_ROUTES

def uniform_first(headways):
    # Integrate P(min residual > t); independent uniform residuals are an assumption.
    end=min(headways)
    def integral(exclude=None):
        coefficients=[1.]
        for i,h in enumerate(headways):
            if i==exclude:continue
            out=[0.]*(len(coefficients)+1)
            for k,v in enumerate(coefficients):out[k]+=v;out[k+1]-=v/h
            coefficients=out
        return sum(v*end**(k+1)/(k+1) for k,v in enumerate(coefficients))
    return integral(),[integral(i)/h for i,h in enumerate(headways)]

def add_common_gate(candidates,planner,departure,live):
    from routing import finish_candidate
    direct=[]
    for c in candidates:
        bus=[l for l in c['legs'] if l['type']=='bus']
        if len(bus)==1 and bus[0]['route_id'] in GATE_ROUTES and bus[0]['station_id']==GATE_STOP:
            r=planner.by_id[bus[0]['route_id']]
            if any(s['id']==STATION_STOP and s['seq']==bus[0]['to_seq'] for s in r['stops']):direct.append((c,bus[0]))
    if not direct:return candidates
    known=[(c,b) for c,b in direct if b['arrival_source']=='live' and b.get('vehicle_id')]
    modeled=[(c,b) for c,b in direct if (b.get('arrival_forecast') or {}).get('operations',{}).get('available')
             or b.get('city_wait',{}).get('simulation',{}).get('model_id')]
    if known:
        original,bus=min(known,key=lambda pair:pair[1]['departure_at'])
        out=deepcopy(original);out['id']='gate-first'
        detail={'kind':'first_observed_boardable_bus','routes_with_eta':len(known),'vehicle_confirmed':True,
                'label':'도보 도착 뒤 탑승 가능한, 도착정보가 확인된 노선 중 첫 차량 · 미확인 노선은 별도'}
    elif modeled:
        # These routes already share the new irregular clock and FIFO delay.
        # Replacing them by uniform residuals would discard the observed pattern.
        original,bus=min(modeled,key=lambda pair:pair[1]['departure_at'])
        out=deepcopy(original);out['id']='gate-first'
        detail={'kind':'first_modeled_boardable_bus','vehicle_confirmed':False,
            'operations_model_id':(bus.get('arrival_forecast') or {}).get('operations',{}).get('model_id') or bus['city_wait']['model_id'],
            'expected_wait_seconds':round(bus['departure_at']-bus['ready_at']),
            'label':'운행·승차 예측에서 먼저 탈 수 있는 노선'}
        scenarios=modeled
    else:
        scenarios=[(c,b) for c,b in direct if b['arrival_source'] in ('estimate','service_history_estimate','city_queue_estimate') and
                   not b.get('city_wait',{}).get('base_conditional_after_known_services',(b.get('arrival_forecast') or {}).get('conditional_after_known_services'))]
        if not scenarios:return candidates
        # Do not pool incompatible access/egress geometries or arrival windows.
        original,bus=scenarios[0]
        scenarios=[(c,b) for c,b in scenarios if c['walk_seconds']==original['walk_seconds'] and c['boarding_seconds']==original['boarding_seconds']]
        h=[b.get('city_wait',{}).get('headway_seconds') or planner.transit.interval(planner.by_id[b['route_id']],b['ready_at'])*60 for c,b in scenarios]
        wait,prob=uniform_first(h);wait=round(wait)
        legs=deepcopy(original['legs']);ride=next(l for l in legs if l['type']=='bus')
        seconds=round(sum(p*b['seconds'] for p,(c,b) in zip(prob,scenarios)))
        ready=ride['ready_at'];leave=ready+wait
        pool=None
        if hasattr(planner.transit,'city_boarding'):
            route=planner.by_id[ride['route_id']];i=next(i for i,s in enumerate(route['stops']) if s['seq']==ride['from_seq'])
            baseline={'departure_at':leave,'earliest_departure_at':leave,'vehicle_id':None,'provided_at':None,
                'full':False,'arrival_source':'pooled_headway_estimate','arrival_forecast':{'headway_seconds':1/sum(1/x for x in h)}}
            pool=planner.transit.city_boarding(route,i,ready,baseline,live,key='pool:'+GATE_STOP,headway=1/sum(1/x for x in h),
                pool_members=[{'route_id':b['route_id'],'seq':b['from_seq'],'probability':p} for p,(c,b) in zip(prob,scenarios)])
            if pool is None:return candidates
            leave=pool['departure_at'];wait=round(leave-ready)
        if not all(planner.transit.in_service(planner.by_id[b['route_id']],leave) for c,b in scenarios):return candidates
        for l in legs:
            if l['type']=='wait':l.update(seconds=wait,source='pooled_headway_estimate',label='정문 공동노선 첫 차 대기')
        ride.update(seconds=seconds,departure_at=leave,arrival_at=leave+seconds,
            route_name='정문 공동노선 먼저 오는 차',arrival_source='pooled_headway_estimate',vehicle_id=None,arrival_options=[],
            ride_model={'seconds':seconds,'source':'common_line_weighted_prior','label':'각 노선 차내시간의 첫 도착 확률 가중 평균 · 가정',
                        'note':'동일 정류장 순서의 도로 경로를 공유하며 실제 탑승 노선은 미확인입니다.'},
            ride_source='동일 구간의 노선별 차내시간 가중 추정')
        if pool and pool.get('city_wait'):
            ride['city_wait']=pool['city_wait'];ride['arrival_forecast']=pool['arrival_forecast']
        mean=sum(p*(b.get('crowd_estimate') if b.get('crowd_estimate') is not None else 1.5) for p,(c,b) in zip(prob,scenarios))
        risk=sum(p*b.get('crowd_risk',3) for p,(c,b) in zip(prob,scenarios))
        ride.update(crowd_cost=None,crowd_estimate=round(mean,3),crowd_risk=risk,
                    crowd_source='pooled_service_estimate',crowd_label='공동노선 혼잡위험 추정',observed_at=None,age_seconds=None,
                    crowd_components=[{'route_id':b['route_id'],'probability':p,'estimate':b.get('crowd_estimate'),'source':b.get('crowd_source')} for p,(c,b) in zip(prob,scenarios)])
        if ride.get('arrival_forecast'):
            ride['arrival_forecast']={**ride['arrival_forecast'],'base_departure_at':leave,'headway_seconds':max(60,wait*2),
                                      'range_seconds':[0,max(60,wait*2)],'source':'pooled_headway_simulation'}
        detail={'kind':'independent_uniform_residuals','headway_seconds':h,'route_probabilities':prob,
                'expected_wait_seconds':wait,'vehicle_confirmed':False,
                'label':'등록 배차간격·노선별 독립 균등 잔여대기 가정 · 실제 배차·탑승 차량 미확인'}
        if pool and pool.get('city_wait'):
            detail['city_wait']=pool['city_wait']
        out=finish_candidate('gate-first',legs,departure,[detail['label'],'노선별 상관·군집 도착·실제 여석은 이 시나리오에 반영되지 않았습니다.'])
        out['strategy']='walk_to_gate'
    out['common_gate_service']={**detail,'eligible_route_ids':[b['route_id'] for c,b in (known if known else scenarios)],
        'eligible_route_names':[b['route_name'] for c,b in (known if known else scenarios)]}
    return candidates+[out]
