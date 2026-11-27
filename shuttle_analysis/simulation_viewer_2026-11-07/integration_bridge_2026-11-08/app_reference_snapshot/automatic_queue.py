"""Automatic class/walk-informed fluid queues. All outputs are estimates, not counts."""
import bisect,hashlib,json,math,statistics
from collections import OrderedDict,defaultdict,deque
from datetime import datetime
from pathlib import Path
from shuttle_timetable import KST,service_day

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
    def series(start,end,h):
        t=start+phase*h;out=[]
        while t<end-1e-7:out.append(t*60);t+=h
        return out
    if rid=='shuttle-41841':
        rows=[]
        for a,b,h in [(420,480,15),(480,660,4),(660,900,10),(900,1140,4),(1140,1200,15),(1200,1260,30)]:rows+=series(a,b,h)
        return rows+[m*60 for m in (1270,1300,1330,1360,1390)]
    if rid=='shuttle-41946':return series(480,1140,6)+series(1140,1260,20)+[1260*60]
    return [m*60 for m in range(590,1031,20)]

def simulate(route,day,phase,scale,reserve,factor,step=30):
    """One shared vehicle serves upstream stops before downstream queues."""
    n=route['n'];events=[];serial=0;input_mass=0.;boarded=0.;max_load=0.
    for d,node,minute,mass in route['flows']:
        if d!=day:continue
        pieces=300//step
        for part in range(pieces):
            at=minute*60+(part+.5)*step+20
            w=mass/pieces*scale*factor(node,at)
            if w<=0:continue
            input_mass+=w;serial+=1;events.append((at,0,serial,node,w))
    for vid,leave in enumerate(dispatches(route['id'],phase)):
        origin=leave-route['offsets'][route['anchor']]
        for k,offset in enumerate(route['offsets']):
            serial+=1;events.append((origin+offset,1,serial,vid,k))
    events.sort();queues=[deque() for _ in range(n)];mass=[0.]*n
    keys=[[] for _ in range(n)];values=[[] for _ in range(n)];supply=[[] for _ in range(n)];loads={}
    cap=route['capacity']*(1-reserve)
    for at,kind,_,a,b in events:
        if kind==0:
            queues[a].append(b);mass[a]+=b;keys[a].append((at,0));values[a].append(mass[a]);continue
        vid,k=a,b;onboard=loads.setdefault(vid,{})
        for target in [target for target in onboard if target<=k]:onboard.pop(target)
        occupied=math.fsum(onboard.values())
        if k>=n or not route['stops'][k]['board_allowed']:continue
        free=max(0.,cap-occupied);supply[k].append({'at':at,'free':free,'vehicle':vid})
        remaining=free;counts=route['od'].get(f'{day}:{k}')
        if not counts:counts=[[n if route['loop'] else max(1,n-1-k),1.]]
        normalizer=math.fsum(p for _,p in counts)
        while queues[k] and remaining>1e-9:
            w=min(queues[k][0],remaining);queues[k][0]-=w;mass[k]-=w;remaining-=w;boarded+=w
            for delta,p in counts:onboard[k+int(delta)]=onboard.get(k+int(delta),0)+w*p/normalizer
            if queues[k][0]<=1e-9:queues[k].popleft()
        mass[k]=max(0.,mass[k]);keys[k].append((at,1));values[k].append(mass[k])
        max_load=max(max_load,math.fsum(onboard.values()))
    return {'keys':keys,'values':values,'supply':supply,'input_mass':input_mass,'boarded_mass':boarded,
            'remaining_mass':math.fsum(mass),'max_load':max_load,'capacity':cap}

def queue_at(profile,index,at):
    k=bisect.bisect_right(profile['keys'][index],(at,0))-1
    return profile['values'][index][k] if k>=0 else 0.

class AutomaticQueue:
    def __init__(self,historical,path=None):
        p=Path(path) if path else Path(__file__).parent/'data/auto_queue_inputs.json'
        self.data=json.loads(p.read_text(encoding='utf-8'));self.config=self.data['model'];self.historical=historical
        self.cache=OrderedDict();self.hist_cache={}
        for rid,route in self.data['routes'].items():route['id']=rid

    def info(self):
        return {'model_id':self.config['id'],'automatic':True,'calibrated':False,'observed_queue':False,
                'unit':self.data['unit'],'course_end_events':self.data['course_end_events'],
                'signal_coefficients':{k:self.config[k] for k in ('historical_beta','live_beta','factor_bounds')},
                'scope':'정규 학기 평일 · 행정관·순환·역순환 43개 노선별 정차 위치',
                'note':'수업 종료·보행·시내버스 수요 신호의 자동 추정. 범위는 가정 민감도이며 신뢰구간이 아닙니다.',
                'limitations':self.data['limitations']}

    def historical_signal(self,rid,index,at):
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
        route=self.data['routes'][rid];signals=[grade_signals(node,snapshot.get('vehicles',[]),asof) if live else [] for node in route['stops']]
        signature=hashlib.sha256(json.dumps(signals,sort_keys=True).encode()).hexdigest()[:16]
        # Profile inputs are date + retained observation values/times; query time is
        # used only below to read the profile. Reuse it across visitors and ticks.
        key=(rid,date.date().isoformat(),signature)
        if key in self.cache:self.cache.move_to_end(key);return self.cache[key],signals,mid
        def factor(index,seconds):
            h=self.historical_signal(rid,index,mid+seconds)['percentile']
            return multiplier(h,pressure(signals[index],mid+seconds,self.config),self.config)
        values=[]
        for scenario in self.config['sensitivity']:
            for phase in self.config['phases']:
                values.append({'scenario':scenario,**simulate(route,date.weekday(),phase,scenario['demand'],scenario['reserve'],factor,self.config['step_seconds'])})
        self.cache[key]=values
        while len(self.cache)>6:self.cache.popitem(last=False)
        return values,signals,mid

    def arrival(self,route,index,ready,observed,timetable,asof,snapshot=None,live=True):
        rid=route['id']
        if rid not in self.data['routes'] or not service_day(ready):return None
        index=index%self.data['routes'][rid]['n']
        if not self.data['routes'][rid]['stops'][index]['board_allowed']:return None
        if not timetable._schedule_arrival(route,index,ready) and not observed:return None
        profiles,signals,mid=self.profiles(rid,ready,snapshot or {},live,asof)
        now=(asof if live else ready)-mid;target=ready-mid;out=[];all_waits=[];q_now=[];q_arrival=[];central_now=[];central_arrival=[];central=[];passed=[];no_board=False
        real=sorted([a for a in observed if live and a.get('arrival_source')=='live_shuttle' and
            a.get('provided_at') is not None and -5<=asof-a['provided_at']<=60 and a.get('earliest_departure_at',a['departure_at'])>=ready],key=lambda a:a['departure_at'])
        for profile in profiles:
            ahead=queue_at(profile,index,target);need=ahead+1;skip=0;chosen=None
            rows=[r for r in profile['supply'][index] if r['at']>=target-1e-8]
            shift=real[0]['departure_at']-mid-rows[0]['at'] if real and rows else 0.
            for k,row in enumerate(rows):
                at=real[k]['departure_at'] if k<len(real) else mid+row['at']+shift
                if at<ready:continue
                if k>=len(real) and not timetable._schedule_arrival(route,index,at-1):continue
                free=row['free']
                if k<len(real):
                    a=real[k];seats=a.get('seats_available')
                    if isinstance(seats,(int,float)) and math.isfinite(seats) and 0<=seats<=route.get('capacity',self.data['routes'][rid]['capacity']):free=seats
                    if a.get('full'):free=0
                if need<=free+1e-8:chosen=at;break
                need-=min(need,free);skip+=1
            is_central=profile['scenario']['demand']==1.
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
        forecast={'model_id':self.config['id'],'source':'automatic_class_walk_bus_pressure','observed_queue':False,'calibrated':False,
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
            'label':'수업 종료·도보 유입·과거 수요·시내버스 혼잡 신호 기반 자동 대기줄 추정 · 실측 아님',
            'limitations':self.data['limitations']}
        leave=ready+wait
        return [{'departure_at':leave,'earliest_departure_at':leave,'vehicle_id':None,'provided_at':None,'full':False,
            'crowd_cost':None,'crowd_label':'정보 부족','arrival_source':'shuttle_auto_queue_estimate',
            'observed_interval':None,'observed_at_stop':False,'eta_window_seconds':[wait,wait],
            'wait_seconds':wait,'prediction_note':forecast['label'],'automatic_queue':forecast}]
