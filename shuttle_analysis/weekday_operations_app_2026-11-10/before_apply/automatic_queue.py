"""Automatic class/walk-informed fluid queues. All outputs are estimates, not counts."""
import bisect,copy,hashlib,json,math,statistics
from collections import OrderedDict,defaultdict,deque
from datetime import datetime
from pathlib import Path
from shuttle_timetable import KST,service_day
from simulation_travel import fifo_opportunity
from shuttle_clock import dispatches as terminal_dispatches
from calculation_context import memoized

def grade_signals(node,vehicles,asof):
    links={(p['route_id'],str(p['section_order'])) for p in node['city_links']};latest={}
    for v in vehicles:
        at=v.get('provided_at');code=str(v.get('crowd_code'));key=(v.get('route_id'),v.get('id'))
        if not key[1] or (key[0],str(v.get('section_order'))) not in links:continue
        if not isinstance(at,(int,float)) or not math.isfinite(at) or not -5<=asof-at<=600:continue
        if code not in ('3','4','5','6') and not v.get('full'):continue
        value=1. if v.get('full') else (int(code)-3)/3
        if key not in latest or at>latest[key]['at']:latest[key]={'route_id':key[0],'at':at,'value':value}
    return list(latest.values())

def pressure(signals,when,config):
    groups=defaultdict(list)
    for value in signals:
        age=when-value['at']
        if age<0 or age>config['live_max_age_seconds']:continue
        weight=math.exp(-max(0,age-config['live_fresh_seconds'])/config['live_decay_seconds'])
        groups[value['route_id']].append(.5+(value['value']-.5)*weight)
    return statistics.mean(statistics.mean(v) for v in groups.values()) if groups else .5

def multiplier(historical,live_pressure,config):
    value=1+config['historical_beta']*((historical if historical is not None else .5)-.5)+config['live_beta']*(live_pressure-.5)
    return max(config['factor_bounds'][0],min(config['factor_bounds'][1],value))

def dispatches(rid,phase):
    return terminal_dispatches(rid,phase)

def simulate(route,day,phase,scale,reserve,factor,step=30):
    """One shared vehicle serves upstream stops before downstream queues."""
    n=route['n'];events=[];serial=0;input_mass=0.;boarded=0.;exited=0.;max_load=0.
    packet_rows=route.get('ready_packets')
    for entry in packet_rows if packet_rows is not None else route.get('ready_flows',[]):
        d,node,second,mass=entry[:4];exit_second=entry[4] if len(entry)>4 else None
        if d!=day:continue
        at=second+step/2;w=mass*scale*factor(node,at)
        if w<=0:continue
        input_mass+=w;serial+=1;token=serial;events.append((at,0,serial,node,(token,w)))
        if exit_second is not None:
            serial+=1;events.append((max(at,exit_second+step/2),1,serial,node,token))
    for d,node,minute,mass in (() if packet_rows is not None else route.get('flows',[])):
        if d!=day:continue
        pieces=300//step
        for part in range(pieces):
            at=minute*60+(part+.5)*step+20
            w=mass/pieces*scale*factor(node,at)
            if w<=0:continue
            input_mass+=w;serial+=1;events.append((at,0,serial,node,(serial,w)))
    for vid,leave in enumerate(dispatches(route['id'],phase)):
        origin=leave-route['offsets'][route['anchor']]
        for k,offset in enumerate(route['offsets']):
            serial+=1;events.append((origin+offset,2,serial,vid,k))
    events.sort();queues=[deque() for _ in range(n)];mass=[0.]*n
    keys=[[] for _ in range(n)];values=[[] for _ in range(n)];supply=[[] for _ in range(n)];loads={}
    cap=route['capacity']*(1-reserve);packets={}
    for at,kind,_,a,b in events:
        if kind==0:
            token,w=b;packet=[w,token];packets[token]=packet
            queues[a].append(packet);mass[a]+=w;keys[a].append((at,0));values[a].append(mass[a]);continue
        if kind==1:
            packet=packets.get(b)
            if packet:
                exited+=packet[0];mass[a]=max(0.,mass[a]-packet[0]);packet[0]=0.
                keys[a].append((at,0));values[a].append(mass[a])
            continue
        vid,k=a,b;onboard=loads.setdefault(vid,{})
        for target in [target for target in onboard if target<=k]:onboard.pop(target)
        occupied=math.fsum(onboard.values())
        if k>=n or not route['stops'][k]['board_allowed']:continue
        free=max(0.,cap-occupied);supply[k].append({'at':at,'free':free,'vehicle':vid})
        remaining=free;counts=route['od'].get(f'{day}:{k}')
        if not counts:counts=[[n if route['loop'] else max(1,n-1-k),1.]]
        normalizer=math.fsum(p for _,p in counts)
        while queues[k] and remaining>1e-9:
            if queues[k][0][0]<=1e-9:queues[k].popleft();continue
            w=min(queues[k][0][0],remaining);queues[k][0][0]-=w;mass[k]-=w;remaining-=w;boarded+=w
            for delta,p in counts:onboard[k+int(delta)]=onboard.get(k+int(delta),0)+w*p/normalizer
            if queues[k][0][0]<=1e-9:queues[k].popleft()
        mass[k]=max(0.,mass[k]);keys[k].append((at,1));values[k].append(mass[k])
        max_load=max(max_load,math.fsum(onboard.values()))
    return {'keys':keys,'values':values,'supply':supply,'input_mass':input_mass,'boarded_mass':boarded,
            'remaining_mass':math.fsum(mass),'exited_mass':exited,'max_load':max_load,'capacity':cap}

def queue_at(profile,index,at):
    k=bisect.bisect_right(profile['keys'][index],(at,0))-1
    return profile['values'][index][k] if k>=0 else 0.

class AutomaticQueue:
    def __init__(self,historical,path=None,*,data=None):
        p=Path(path) if path else Path(__file__).parent/'data/auto_queue_inputs.json'
        self.data=copy.deepcopy(data) if data is not None else json.loads(p.read_text(encoding='utf-8'));self.config=self.data['model'];self.historical=historical
        self.cache=OrderedDict();self.hist_cache={}
        for rid,route in self.data['routes'].items():route['id']=rid

    def info(self):
        return {'model_id':self.config['id'],'automatic':True,'calibrated':False,'observed_queue':False,
                'algorithm_id':self.config.get('algorithm_id',self.config['id']),'release':self.data.get('release'),
                'travel_clock_model':self.data.get('travel_clock_model'),
                'boarding_algorithm':'frozen_v5_first_boardable_fifo',
                'latest_simulation':self.data.get('latest_simulation'),
                'city_wait':{'available':bool(self.data.get('city_wait')),'route_count':len({s['route_id'] for s in self.data.get('city_wait',{}).get('services',{}).values() if s.get('route_id')}),
                    'algorithm_id':self.data.get('city_wait',{}).get('algorithm_id'),'calibrated':False},
                'unit':self.data['unit'],'course_end_events':self.data['course_end_events'],
                'signal_coefficients':{k:self.config[k] for k in ('historical_beta','live_beta','factor_bounds')},
                'scope':'정규 학생 셔틀 10개 · 주간/야간 잔여 줄 공유 · 심야는 전날 운행일 기준',
                'model_only':self.config.get('model_only',False),'all_shuttle_extension':self.data.get('all_shuttle_extension'),
                'note':'시간표·v5 수업/보행 유입·FIFO 정원 모형. 등교/심야 코호트가 없으면 배차위상 대기만 산출합니다. 범위는 가정 민감도이며 신뢰구간이 아닙니다.',
                'limitations':self.data['limitations']}

    def city_arrival(self,transit,route,index,ready,base,live=True,**kwargs):
        from city_wait import project
        return project(self,transit,route,index,ready,base,live,**kwargs)

    def historical_signal(self,rid,index,at):
        if self.config.get('model_only'):return {'available':False,'percentile':None,'route_count':0,'source':'model_only_no_city_pressure','unit':'not_used'}
        date=datetime.fromtimestamp(at,KST);key=(rid,index,date.weekday(),date.hour)
        if key in self.hist_cache:return self.hist_cache[key]
        route=self.data['routes'][rid];groups=defaultdict(list)
        for p in route['stops'][index]['city_links']:
            value=self.historical.point(p['route_id'],p['from_seq'],p['from_stop'],p['to_stop'],at)
            if value.get('available'):groups[p['route_id']].append(value['relative_demand_percentile'])
        result={'available':bool(groups),'percentile':statistics.mean(statistics.mean(v) for v in groups.values()) if groups else None,
                'route_count':len(groups),'unit':'relative_hourly_demand_pattern_not_vehicle_crowding'}
        self.hist_cache[key]=result;return result

    def profiles(self,rid,at,snapshot,live,asof):
        date=datetime.fromtimestamp(at,KST);mid=date.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        route=self.data['routes'][rid];signals=[grade_signals(node,snapshot.get('vehicles',[]),asof) if live and not self.config.get('model_only') else [] for node in route['stops']]
        signature=hashlib.sha256(json.dumps(signals,sort_keys=True).encode()).hexdigest()[:16]
        # Profile inputs are date + retained observation values/times; query time is
        # used only below to read the profile. Reuse it across visitors and ticks.
        key=(rid,date.date().isoformat(),signature)
        if key in self.cache:self.cache.move_to_end(key);return self.cache[key],signals,mid
        def factor(index,seconds):
            if self.config.get('model_only'):return 1.
            h=self.historical_signal(rid,index,mid+seconds)['percentile']
            return multiplier(h,pressure(signals[index],mid+seconds,self.config),self.config)
        values=[]
        for scenario in self.config['sensitivity']:
            for phase in self.config['phases']:
                values.append({'scenario':scenario,**simulate(route,date.weekday(),phase,scenario['demand'],scenario['reserve'],factor,self.config['step_seconds'])})
        self.cache[key]=values
        while len(self.cache)>12:self.cache.popitem(last=False)
        return values,signals,mid

    def arrival(self,route,index,ready,observed,timetable,asof,snapshot=None,live=True):
        # A single search uses one observation snapshot and one as-of clock.
        key=(id(self),id(timetable),route['id'],index,ready,asof,live,json.dumps(observed,sort_keys=True))
        return memoized('automatic_queue',key,
            lambda:self._arrival(route,index,ready,observed,timetable,asof,snapshot,live))

    def _arrival(self,route,index,ready,observed,timetable,asof,snapshot=None,live=True):
        target_id=route['id']
        if target_id not in self.data['routes']:return None
        base=timetable._schedule_arrival(route,index,ready)
        if not base:return None
        midnight=base.get('service_midnight')
        profile_at=midnight+12*3600 if midnight is not None else ready
        if not service_day(profile_at):return None
        target=self.data['routes'][target_id];rid=target.get('profile_route_id',target_id)
        index=target.get('profile_index_map',[*range(target['n'])])[index%target['n']]
        index=index%self.data['routes'][rid]['n']
        if not self.data['routes'][rid]['stops'][index]['board_allowed']:return None
        original_index=next((i for i,s in enumerate(route['stops']) if s['id']==self.data['routes'][rid]['stops'][index]['id'] and s['board_allowed']),0)
        profiles,signals,mid=self.profiles(rid,profile_at,snapshot or {},live,asof)
        now=(asof if live else ready)-mid;target=ready-mid;out=[];all_waits=[];q_now=[];q_arrival=[];central_now=[];central_arrival=[];central=[];passed=[];loads=[];no_board=False
        real=sorted([a for a in observed if live and (not self.config.get('model_only') or a.get('clock_conditioning_verified')) and a.get('arrival_source')=='live_shuttle' and
            a.get('provided_at') is not None and -5<=asof-a['provided_at']<=60 and a.get('earliest_departure_at',a['departure_at'])>=ready],key=lambda a:a['departure_at'])
        for profile in profiles:
            ahead=queue_at(profile,index,target);chosen=None;opportunities=[]
            rows=[r for r in profile['supply'][index] if r['at']>=target-1e-8]
            shift=real[0]['departure_at']-mid-rows[0]['at'] if real and rows else 0.
            for k,row in enumerate(rows):
                at=real[k]['departure_at'] if k<len(real) else mid+row['at']+shift
                if at<ready:continue
                if k>=len(real) and (at>base['last_scheduled_departure_at'] if base.get('last_scheduled_departure_at') else not timetable._schedule_arrival(route,original_index,at-1)):continue
                if target_id in ('shuttle-41915','shuttle-41942') and at<mid+1270*60:continue
                free=row['free']
                if k<len(real) and not self.config.get('model_only'):
                    a=real[k];seats=a.get('seats_available')
                    if isinstance(seats,(int,float)) and math.isfinite(seats) and 0<=seats<=route.get('capacity',self.data['routes'][rid]['capacity']):free=seats
                    if a.get('full'):free=0
                opportunities.append({'departure_at':at,'seats_available':free})
            selected,skip,_=fifo_opportunity(opportunities,ready,ahead)
            if selected:chosen=selected['departure_at']
            is_central=profile['scenario']['demand']==1.
            if selected and is_central:
                before=sum(o['seats_available'] for o in opportunities[:skip]);remaining=max(0,ahead+1-before)
                occupied=self.data['routes'][rid]['capacity']-max(0,selected['seats_available']-remaining)
                loads.append(max(0,min(1,occupied/self.data['routes'][rid]['capacity'])))
            if is_central:central.append(chosen)
            if is_central:central_now.append(queue_at(profile,index,now));central_arrival.append(ahead)
            if chosen is None:no_board=True
            else:all_waits.append(chosen-ready)
            if is_central and chosen is not None:out.append(chosen-ready);passed.append(skip)
            q_now.append(queue_at(profile,index,now));q_arrival.append(ahead)
        # Never report a mean over only the served subset of the central scenarios.
        if not central or any(v is None for v in central):return []
        wait=round(statistics.mean(out));hist=self.historical_signal(rid,index,ready)
        signal=signals[index];current=pressure(signal,asof,self.config)
        coverage=self.data['routes'][rid].get('cohort_range_seconds')
        has_cohort=bool(coverage and coverage[0]<=target<=coverage[1])
        forecast={'model_id':self.config['id'],'source':'timetable_v5_fifo_only' if self.config.get('model_only') else 'automatic_class_walk_bus_pressure','observed_queue':False,'calibrated':False,
            'algorithm_id':self.config.get('algorithm_id',self.config['id']),
            'latest_simulation':{k:v for k,v in self.data.get('latest_simulation',{}).items() if k!='source_totals'},
            'expected_load_ratio':round(statistics.mean(loads),4) if loads and has_cohort else None,
            'model_only':self.config.get('model_only',False),'cohort_available':has_cohort,'profile_route_id':rid,
            'inflow_source':self.data['routes'][rid].get('inflow_source','legacy'),
            'estimated_at':asof,'queue_reference_at':asof if live else ready,'future_query':not live,
            'arrival_time':ready,'queue_now':round(statistics.mean(central_now),2),
            'queue_at_arrival':round(statistics.mean(central_arrival),2),'queue_range':[round(min(q_arrival),2),round(max(q_arrival),2)],
            'queue_now_range':[round(min(q_now),2),round(max(q_now),2)],'expected_wait_seconds':wait,
            'wait_scenario_range_seconds':[round(min(all_waits)),None if no_board else round(max(all_waits))],
            'some_scenarios_unserved':no_board,'range_kind':'assumption_sensitivity_not_confidence_interval',
            'mean_skipped_departures':round(statistics.mean(passed),2),'capacity_assumption':self.data['routes'][rid]['capacity'],
            'historical_signal':hist,'live_signal':{'available':bool(signal),'vehicles':len(signal),
                'newest_observed_at':max((v['at'] for v in signal),default=None),
                'oldest_age_seconds':round(max((asof-v['at'] for v in signal),default=0)) if signal else None,
                'source':'observed' if signal and all(asof-v['at']<=90 for v in signal) else 'last_observation_estimate' if signal else 'unavailable'},
            'current_demand_multiplier':round(multiplier(hist['percentile'],current,self.config),4),
            'live_arrival_conditioned':bool(real),'coefficients_calibrated':False,'unit':'weighted_expected_trip_events',
            'clock_observed_at':real[0]['provided_at'] if real else None,'crowd_observations_used':False,
            'label':'시간표·v5 수업/보행 유입·FIFO 모형 대기 추정 · 실측 아님' if has_cohort else '시간표 배차위상 시뮬레이션 대기 · 등교/심야 유입 코호트 없음 · 줄 인원 미산출',
            'limitations':self.data['limitations']}
        if not has_cohort:
            for key in ('queue_now','queue_at_arrival','queue_range','queue_now_range'):forecast[key]=None
        leave=ready+wait
        return [{'departure_at':leave,'earliest_departure_at':leave,'vehicle_id':None,'provided_at':None,'full':False,
            'crowd_cost':None,'crowd_label':'정보 부족','arrival_source':'shuttle_auto_queue_estimate',
            'observed_interval':None,'observed_at_stop':False,'eta_window_seconds':[wait,wait],
            'wait_seconds':wait,'prediction_note':forecast['label'],'automatic_queue':forecast,
            'next_scheduled_departure_at':base['departure_at'] if base.get('fixed_departure') else None,
            'fixed_departure':False,'expected_boarding_time':True,
            'wait_model':base['wait_model'],'source_url':base['source_url'],
            'based_on_observed_at':real[0]['provided_at'] if real else None}]
