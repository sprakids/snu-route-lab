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
    if known:
        original,bus=min(known,key=lambda pair:pair[1]['departure_at'])
        out=deepcopy(original);out['id']='gate-first'
        detail={'kind':'first_observed_boardable_bus','routes_with_eta':len(known),'vehicle_confirmed':True,
                'label':'도보 도착 뒤 탑승 가능한, 도착정보가 확인된 노선 중 첫 차량 · 미확인 노선은 별도'}
    else:
        scenarios=[(c,b) for c,b in direct if b['arrival_source']=='estimate']
        if not scenarios:return candidates
        # Do not pool incompatible access/egress geometries or arrival windows.
        original,bus=scenarios[0]
        scenarios=[(c,b) for c,b in scenarios if c['walk_seconds']==original['walk_seconds'] and c['boarding_seconds']==original['boarding_seconds']]
        h=[planner.transit.interval(planner.by_id[b['route_id']],b['ready_at'])*60 for c,b in scenarios]
        wait,prob=uniform_first(h);wait=round(wait)
        legs=deepcopy(original['legs']);ride=next(l for l in legs if l['type']=='bus')
        seconds=round(sum(p*b['seconds'] for p,(c,b) in zip(prob,scenarios)))
        ready=ride['ready_at'];leave=ready+wait
        if not all(planner.transit.in_service(planner.by_id[b['route_id']],leave) for c,b in scenarios):return candidates
        for l in legs:
            if l['type']=='wait':l.update(seconds=wait,source='pooled_headway_estimate',label='정문 공동노선 첫 차 대기')
        ride.update(seconds=seconds,departure_at=leave,arrival_at=leave+seconds,
            route_name='정문 공동노선 먼저 오는 차',arrival_source='pooled_headway_estimate',vehicle_id=None,arrival_options=[],
            ride_model={'seconds':seconds,'source':'common_line_weighted_prior','label':'각 노선 차내시간의 첫 도착 확률 가중 평균 · 가정',
                        'note':'동일 정류장 순서의 도로 경로를 공유하며 실제 탑승 노선은 미확인입니다.'},
            ride_source='동일 구간의 노선별 차내시간 가중 추정')
        detail={'kind':'independent_uniform_residuals','headway_seconds':h,'route_probabilities':prob,
                'expected_wait_seconds':wait,'vehicle_confirmed':False,
                'label':'등록 배차간격·노선별 독립 균등 잔여대기 가정 · 실제 배차·탑승 차량 미확인'}
        out=finish_candidate('gate-first',legs,departure,[detail['label'],'노선별 상관·군집 도착·실제 여석은 이 시나리오에 반영되지 않았습니다.'])
        out['strategy']='walk_to_gate'
    out['common_gate_service']={**detail,'eligible_route_ids':[b['route_id'] for c,b in (known if known else scenarios)],
        'eligible_route_names':[b['route_name'] for c,b in (known if known else scenarios)]}
    return candidates+[out]
