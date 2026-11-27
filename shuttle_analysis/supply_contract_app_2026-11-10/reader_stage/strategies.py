"""Compare feasible strategies without converting passenger sums into minutes."""
GATE_STOP='120000029'
STATION_STOP='120000150'
GATE_ROUTES={'100100250','100100251','100100252','100100263','100100521'}

def strategy_for(rides,by_id):
    route=by_id[rides[0][0]];index=rides[0][1]
    if route.get('kind')=='shuttle':return 'shuttle_wait'
    if route['id'] in GATE_ROUTES and route['stops'][index]['id']==GATE_STOP:return 'walk_to_gate'
    return 'other_city'

def summarize(candidate):
    rides=[l for l in candidate['legs'] if l['type']=='bus']
    queues=[a['queue_model'] for l in rides for a in l.get('arrival_options',[]) if a.get('queue_model')]
    return {k:candidate[k] for k in ('id','total_seconds','walk_seconds','walk_m','wait_seconds','ride_seconds',
            'boarding_seconds','arrival_at','route_names','crowd_label','crowd_risk','historical_forecast')} | {
        'strategy':candidate.get('strategy'),
        'boarding':[{k:l.get(k) for k in ('route_id','route_name','from_name','to_name','station_ars','ready_at',
            'departure_at','vehicle_id','arrival_source','crowd_source','crowd_label','age_seconds','observed_at',
            'historical_demand','prediction_note')} for l in rides],
        'historical_demand':candidate.get('historical_demand'),
        'queue_scenario':queues[0] if queues else None,
        'common_gate_service':candidate.get('common_gate_service'),
        'queue_projection':next((l['queue_projection'] for l in rides if l.get('queue_projection')),None),
        'automatic_queues':[l['automatic_queue'] for l in rides if l.get('automatic_queue')],
        'time_evidence':[l.get('ride_model',{}) for l in rides],
        'uses_unobserved_departure':any(l.get('arrival_source') not in ('live','live_shuttle') for l in rides)}

def compare_strategies(plan,enabled=True):
    candidates=plan['candidates']
    if not enabled:return None
    summaries={}
    for key in ('shuttle_wait','walk_to_gate','walk_only','other_city'):
        values=[c for c in candidates if c.get('strategy')==key]
        if key=='walk_to_gate' and any(c.get('common_gate_service') for c in values):values=[c for c in values if c.get('common_gate_service')]
        best=min(values,key=lambda c:(c['total_seconds'],c['crowd_risk'],c['walk_m'])) if values else None
        summaries[key]=summarize(best) if best else None
    both=[summaries[k] for k in ('shuttle_wait','walk_to_gate') if summaries[k]]
    pair_winner=min(both,key=lambda c:(c['total_seconds'],c['crowd_risk'])) if both else None
    fastest=min(candidates,key=lambda c:(c['total_seconds'],c['crowd_risk'])) if candidates else None
    gap=abs(both[0]['total_seconds']-both[1]['total_seconds']) if len(both)==2 else None
    shuttle_options=[]
    shuttle_candidates=[c for c in candidates if c.get('strategy')=='shuttle_wait']
    first=lambda c:next(l for l in c['legs'] if l['type']=='bus')['route_id']
    for rid in dict.fromkeys(first(c) for c in shuttle_candidates):
        shuttle_options.append(summarize(min((c for c in shuttle_candidates if first(c)==rid),key=lambda c:c['total_seconds'])))
    return {'strategies':summaries,'compared_at':plan['generated_at'],
        'faster_strategy':pair_winner['strategy'] if len(both)==2 else None,
        'difference_seconds':gap,'small_difference':gap is not None and gap<120,
        'small_difference_threshold_seconds':120,'recommended_candidate_id':fastest['id'] if fastest else None,
        'recommended_strategy':fastest.get('strategy') if fastest else None,
        'recommendation_basis':'도보·대기·승차 여유·차내시간의 합이 가장 짧은 실행 가능한 후보. 실측 만차 차량은 제외.',
        'missing_reasons':{'shuttle_wait':'시간표·관측·보행 조건에서 탑승 가능한 셔틀 후보가 없습니다.' if plan.get('include_shuttle',True) else '셔틀 비교 옵션을 켜면 함께 확인할 수 있습니다.',
                           'walk_to_gate':'서울대학교 21128 정류장 경유로 연결 가능한 후보가 없습니다.',
                           'walk_only':'연결 가능한 전체 보행 경로가 없습니다.','other_city':'다른 유효 시내버스 후보가 없습니다.'},
        'note':'총시간은 추정입니다. 과거 재차합은 상대 수요 근거로 표시하며 차량 혼잡 등급·추가 대기 분으로 환산하지 않습니다.',
        'shuttle_options':shuttle_options,
        'gate_options':[{k:c[k] for k in ('id','route_names','total_seconds','walk_seconds','wait_seconds','ride_seconds','crowd_label')}
                        for c in sorted(candidates,key=lambda c:c['total_seconds']) if c.get('strategy')=='walk_to_gate']}
