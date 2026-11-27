"""Offline, assumption-labelled spatial demand simulation; never calls live APIs.

Counts are enrollment-weighted trip events, not distinct students or observed riders.
Routing reuses the product's OSM pedestrian graph and direct/one-transfer candidates.
"""
from pathlib import Path
from collections import defaultdict, Counter
from types import SimpleNamespace
import csv, json, sys, math, hashlib, time
import numpy as np

ROOT = Path(__file__).resolve().parent
APP = ROOT.parent / 'app'
sys.path.insert(0, str(APP))
from routing import WalkingGraph, Planner, distance

DAYS = '월화수목금토일'
START, END = 11 * 60 + 20, 23 * 60 + 10
REPS, PARTICLES, SEED = 10, 12, 20261106
REFERENCE_DORM = 5772 / 29613
REFERENCE_SCENARIO = 'reference_dorm19p49_depart50'
REVERSE_DEPARTURE_CACHE = {}

def load(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def dump(p, v): Path(p).write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding='utf-8')
def clock(m): return f'{int(m)//60:02d}:{int(m)%60:02d}'
def write_csv(name, rows):
    if not rows: return
    with (ROOT / 'outputs' / name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

class MatrixWalker:
    """Cache only endpoint path costs, not hundreds of complete Dijkstra trees."""
    def __init__(self, graph, points):
        self.graph = graph
        self.points = list(dict.fromkeys(tuple(p) for p in points))
        # Building representative pins sometimes snap to disconnected courtyard fragments.
        # Snap to the existing main public pedestrian component; never create graph edges.
        parent = {n:n for n in graph.nodes}
        def find(n):
            while parent[n]!=n:
                parent[n]=parent[parent[n]]; n=parent[n]
            return n
        for a,edges in graph.edges.items():
            for b,*_ in edges:
                ra,rb=find(a),find(b)
                if ra!=rb:parent[rb]=ra
        components=Counter(find(n) for n in graph.nodes)
        largest=max(components,key=components.get)
        public_points=[(n,p) for n,p in graph.points if find(n)==largest]
        self.component_profile={'nodes_total':len(graph.nodes),'component_count':len(components),
                                'main_component_nodes':len(public_points)}
        ids, coords = zip(*public_points)
        coords = np.array(coords)
        self.snaps = {}
        for p in self.points:
            d = (coords[:, 0]-p[0])**2 + ((coords[:, 1]-p[1])*.794)**2
            i = int(d.argmin()); self.snaps[p] = (ids[i], distance(p, coords[i]))
        self.rows = {}

    def walk(self, a, b):
        a, b = tuple(a), tuple(b)
        na, da = self.snaps[a]; nb, db = self.snaps[b]
        if max(da, db) > 110: return None
        if a not in self.rows:
            costs, parents = self.graph.tree(na)
            meters = {na: 0.0}; steps = {na: 0.0}
            def length(n):
                chain = []
                while n not in meters:
                    chain.append(n); n = parents[n][0]
                for child in reversed(chain):
                    parent, m, st = parents[child]
                    meters[child] = meters[parent]+m; steps[child] = steps[parent]+st
            row = {}
            for p, (node, connector) in self.snaps.items():
                if connector > 110 or node not in costs: continue
                length(node)
                row[p] = {'seconds': round(costs[node]+(da+connector)/1.2),
                          'meters': round(meters[node]+da+connector),
                          'steps_m': round(steps[node]), 'connectors_m': round(da+connector)}
            self.rows[a] = row
        return self.rows[a].get(b)

def shuttle_routes(catalog):
    public = load(ROOT/'sources/campus_bus_stops.json')['bus_station_list']
    by_code = {str(x['bus_station_code']): x for x in public}
    # Correct a legacy catalog mismatch using the official map, within this simulation.
    # Culture Hall is stop 300, not administration stop 410.
    corrections=[]
    for spec in catalog['routes']:
        for a in spec['anchors']:
            if spec['id']=='41914' and a['name']=='문화관':
                x=by_code['300']
                corrections.append({'route':spec['id'],'name':a['name'],'old_id':a['stop_id'],
                    'new_id':'snu-300','coordinate_source':'https://map.snu.ac.kr/api/bus/search.action?search_word=',
                    'lat':float(x['bus_station_latitude']),'lon':float(x['bus_station_longitude'])})
                a.update(stop_id='snu-300',lat=float(x['bus_station_latitude']),lon=float(x['bus_station_longitude']))
    dump(ROOT/'outputs/coordinate_corrections.json',corrections)
    result = []
    for spec in catalog['routes']:
        base = [{ 'id': a['stop_id'], 'name': a['name'], 'lat': a['lat'], 'lon': a['lon'],
                  'board_allowed': a['board_allowed'], 'alight_allowed': a['alight_allowed'],
                  'direction': spec['direction_label'] }
                for a in spec['anchors'] if a.get('lat') and a.get('lon') and
                (a['board_allowed'] or a['alight_allowed'])]
        stops = [{**s, 'seq': i+1, 'board_allowed': s['board_allowed'] and i<len(base)}
                 for i,s in enumerate(base+base if spec['loop'] else base)]
        result.append({'id': 'shuttle-'+spec['id'], 'name': spec['name'], 'kind': 'shuttle',
                       'stops': stops, 'interval_minutes': 0,
                       'cycle_length': len(base) if spec['loop'] else None})
    # Public campus map stop codes 410 (administration), 2501 (Daehak pickup),
    # 2500 (Daehak dropoff). Timetable-only addition, never a live-vehicle claim.
    def stop(code, name, board=True, alight=True):
        x = by_code[str(code)]
        return {'id': f'snu-{code}', 'name': name, 'lat': float(x['bus_station_latitude']),
                'lon': float(x['bus_station_longitude']), 'board_allowed': board,
                'alight_allowed': alight, 'direction': '행정관 ↔ 대학동'}
    result.append({'id': 'shuttle-daehak', 'name': '대학동 셔틀(시간표)', 'kind': 'shuttle',
                   'interval_minutes': 0, 'cycle_length': None,
                   'stops': [{**s,'seq':i+1} for i,s in enumerate([
                       stop(410,'행정관'), stop(2500,'대학동(하차)',False,True),
                       stop(2501,'대학동(승차)',True,False), stop(410,'행정관',False,True)])]})
    return result

def headway(route, board, minute):
    """Minutes; timetable windows are planned operation, not observed departures."""
    if route.get('kind') != 'shuttle':
        # Conservative analysis window only; first/last bus data not inferred here.
        return float(route['interval_minutes']) if 8*60 <= minute < END else math.inf
    rid = route['id']
    if rid == 'shuttle-41841':
        # Campus -> station from administration; reverse direction ends 18:00.
        campus = route['stops'][board]['id'] == 'snu-410'
        if not campus and minute >= 18*60: return math.inf
        if 8*60 <= minute < 11*60 or 15*60 <= minute < 19*60: return 4.0
        if 11*60 <= minute < 15*60: return 10.0
        if 19*60 <= minute < 20*60: return 15.0
        if 20*60 <= minute < 21*60: return 30.0
    elif rid == 'shuttle-daehak':
        if 8*60 <= minute < 11*60: return 6.5
        if 11*60 <= minute < 19*60: return 10.0
    elif rid == 'shuttle-41946':
        if 8*60 <= minute < 19*60: return 6.0
        if 19*60 <= minute < 20*60+50: return 20.0
    elif rid == 'shuttle-41914':
        if 9*60+50 <= minute < 17*60+10: return 20.0
    return math.inf

def wait_seconds(route, board, ready, uniforms):
    minute = ready/60
    if route['id']=='shuttle-41914':
        # Official 302-building departure clock; downstream stops inherit travel offsets.
        key=(route['id'],board)
        if key not in REVERSE_DEPARTURE_CACHE:
            offset=0
            for a,b in zip(route['stops'][:board],route['stops'][1:board+1]):
                offset += distance((a['lat'],a['lon']),(b['lat'],b['lon']))*1.2/5+15
            REVERSE_DEPARTURE_CACHE[key]=np.arange((9*60+50)*60,(17*60+10)*60+1,20*60)+offset
        departures=REVERSE_DEPARTURE_CACHE[key]
        indices=np.searchsorted(departures,ready)
        return np.where(indices<len(departures),departures[np.minimum(indices,len(departures)-1)]-ready,math.inf)
    if route['id'] in ('shuttle-41841','shuttle-daehak') and route['stops'][board]['id']=='snu-410':
        # Fixed night departures are respected; no immediate departure at terminal.
        night = np.array([21*60+10,21*60+40,22*60+10,22*60+40,23*60+10])*60
        daytime = minute < (21*60 if route['id']=='shuttle-41841' else 19*60)
        h = np.array([headway(route,board,m) for m in minute])
        wait = h*60*uniforms
        for k in np.flatnonzero(~daytime):
            eligible = night[night>=ready[k]]
            wait[k] = eligible[0]-ready[k] if len(eligible) else math.inf
        return wait
    return np.array([headway(route,board,m) for m in minute])*60*uniforms

def build_candidates(events):
    network = load(APP/'data/network.json'); catalog = load(APP/'data/shuttle_network.json')
    network['routes'] += shuttle_routes(catalog)
    # Work only with point coordinates already present in official/current sources.
    by_stop = {s['id']: s for r in network['routes'] for s in r['stops']}
    buildings = {e['building']: (e['lat'],e['lon']) for e in events if e['building']}
    official_buildings = {str(x['vil_dong_nm']): x for x in load(ROOT/'sources/campus_buildings.json')['rows']}
    def building_point(code):
        b=official_buildings[code]; return float(b['lat_val']),float(b['lon_val'])
    destinations = {
        'dorm_ug': building_point('919'), 'dorm_grad': building_point('900'),
        'snu': (by_stop['120000150']['lat'],by_stop['120000150']['lon']),
        'nak': (by_stop['120900119']['lat'],by_stop['120900119']['lon']),
        'daehak': (by_stop['120000056']['lat'],by_stop['120000056']['lon'])}
    points = list(buildings.values())+list(destinations.values())+[
        (s['lat'],s['lon']) for r in network['routes'] for s in r['stops']]
    walker = MatrixWalker(WalkingGraph(load(APP/'data/walking_osm.json')), points)
    transit = SimpleNamespace(shuttle=SimpleNamespace(available=lambda r:True))
    planner = Planner(network,walker,transit)
    choices = {}; coverage=[]; catalog_out=[]
    for n,(building,origin) in enumerate(sorted(buildings.items())):
        for dest,point in destinations.items():
            patterns = planner.patterns(origin, point, include_shuttle=True)
            candidates = []
            direct = walker.walk(origin, point)
            if direct: candidates.append({'rides': [], 'first_walk':direct, 'last_walk':{'seconds':0,'meters':0}})
            for p in patterns:
                rides = []
                for rid,i,j in p['rides']:
                    route=planner.by_id[rid]
                    rides.append({'route_id':rid,'route_name':route['name'], 'board':i,'alight':j,
                                  'ride_seconds':planner.ride_seconds(route,i,j),
                                  'stop_id':route['stops'][i]['id'], 'stop_name':route['stops'][i]['name'],
                                  'direction':route['stops'][i].get('direction',''),
                                  'lat':route['stops'][i]['lat'],'lon':route['stops'][i]['lon']})
                candidates.append({'rides':rides,'first_walk':p['first_walk'],'last_walk':p['last_walk'],
                                   'transfer_walk':p.get('transfer_walk',{'seconds':0,'meters':0})})
            choices[(building,dest)] = candidates
            coverage.append({'building':building,'destination':dest,'candidate_count':len(candidates),
                             'direct_walk_seconds':direct['seconds'] if direct else None,
                             'snap_connector_m':round(walker.snaps[origin][1],1)})
            for i,c in enumerate(candidates):
                catalog_out.append({'building':building,'destination':dest,'candidate':i,
                    'access_walk_seconds':c['first_walk']['seconds'],
                    'access_walk_m':c['first_walk']['meters'],
                    'route_ids':' / '.join(x['route_id'] for x in c['rides']),
                    'boarding_stops':' / '.join(x['stop_id'] for x in c['rides']),
                    'boarding_names':' / '.join(x['stop_name'] for x in c['rides'])})
        if n%15==0: print(f'route candidates: {n+1}/{len(buildings)} buildings',flush=True)
    write_csv('route_candidate_coverage.csv',coverage)
    write_csv('route_candidates.csv',catalog_out)
    dump(ROOT/'outputs/simulation_routes.json',network)
    dump(ROOT/'outputs/walking_component_profile.json',walker.component_profile)
    return choices,planner.by_id,destinations,coverage

def run_rep(events,choices,routes,seed,walk_factor=1.0):
    rng=np.random.default_rng(seed)
    bins=defaultdict(float); modes=defaultdict(float); stopmeta={}; lags=[]; missing=Counter()
    # Each destination is simulated conditionally. Scenario probabilities are applied later.
    for e in events:
        day=e['weekday']; n=PARTICLES
        for group,dest in [('dorm','dorm_ug' if e['degree_level']=='학사' else 'dorm_grad'),('snu','snu'),('nak','nak'),('daehak','daehak')]:
            weight=e['enrollment']/n
            speed=rng.triangular(.9,1.2,1.5,n)*walk_factor
            scale=1.2/speed
            egress=rng.triangular(60,180,480,n)
            departure=e['end_minute']*60+egress
            options=choices[(e['building'],dest)]
            costs=[]; arrivals=[]
            # Common route phases across travelers in a cohort; unknown bus phase is random.
            phases={rid:np.full(n,rng.random()) for rid in routes}
            for c in options:
                t=departure+c['first_walk']['seconds']*scale
                stops=[]
                for j,ride in enumerate(c['rides']):
                    if j: t=t+c['transfer_walk']['seconds']*scale
                    stops.append(t.copy())
                    t=t+20
                    t=t+wait_seconds(routes[ride['route_id']],ride['board'],t,phases[ride['route_id']])
                    t=t+ride['ride_seconds']
                if c['rides']: t=t+c['last_walk']['seconds']*scale
                # Transfers have a disclosed 2 min perceived cost for route choice only.
                costs.append(t-departure+120*max(0,len(c['rides'])-1))
                arrivals.append(stops)
            if not options:
                modes[(day,group,'unassigned')]+=e['enrollment']; missing[e['building']]+=e['enrollment']; continue
            cost=np.array(costs)
            # Modest taste heterogeneity, Gumbel scale 90 seconds, scenario not fitted.
            choicecost=cost+rng.gumbel(0,90,cost.shape)
            chosen=np.argmin(choicecost,axis=0)
            valid=np.isfinite(cost[chosen,np.arange(n)])
            modes[(day,group,'unassigned')]+=float((~valid).sum())*weight
            for ci,c in enumerate(options):
                selected=(chosen==ci)&valid
                count=int(selected.sum())
                if not count:continue
                mode='walk' if not c['rides'] else 'shuttle_first' if c['rides'][0]['route_id'].startswith('shuttle-') else 'city_first'
                modes[(day,group,mode)]+=count*weight
                for stage,ride in enumerate(c['rides']):
                    stopkey=(ride['stop_id'],ride['direction'],ride['route_id'])
                    stopmeta[stopkey]=ride
                    times=arrivals[ci][stage][selected]/60
                    for minute in times:
                        b=int(minute//5)*5
                        bins[(day,group,*stopkey,b,stage)]+=weight
                    if stage==0:
                        for lag in (arrivals[ci][0][selected]-e['end_minute']*60)/60:
                            lags.append((float(lag),weight,group))
    return bins,modes,stopmeta,lags,missing

def scenarios():
    result=[{'id':REFERENCE_SCENARIO,'dorm_share':REFERENCE_DORM,
             'immediate_trip_share':.5,'external_mix':[1/3]*3}]
    for dorm in (.1,.2,.3):
        for dep in (.25,.5,.75):
            result.append({'id':f'dorm{int(dorm*100)}_depart{int(dep*100)}',
                'dorm_share':dorm,'immediate_trip_share':dep,'external_mix':[1/3]*3})
    for label,mix in [('snu_dominant',[.6,.2,.2]),('nak_dominant',[.2,.6,.2]),('daehak_dominant',[.2,.2,.6])]:
        result.append({'id':label,'dorm_share':REFERENCE_DORM,'immediate_trip_share':.5,'external_mix':mix})
    return result

def probabilities(s):
    return {'dorm':s['dorm_share'],**dict(zip(('snu','nak','daehak'),[(1-s['dorm_share'])*x for x in s['external_mix']]))}

def main():
    t0=time.time(); all_events=load(ROOT/'outputs/course_endings_current.json')
    # Include earlier endings so arrivals after 11:20 are retained. All outputs cover weekdays.
    events=[e for e in all_events if e['included_main'] and e['weekday'] in DAYS[:5] and e['end_minute']<=END]
    choices,routes,destinations,coverage=build_candidates(events)
    combined=defaultdict(float); modes_mean=defaultdict(float); reps=[]; lagpoints=[]; meta={}; missing_total=Counter()
    for rep in range(REPS):
        bins,modes,sm,lags,missing=run_rep(events,choices,routes,SEED+rep)
        for k,v in bins.items():combined[k]+=v/REPS
        for k,v in modes.items():modes_mean[k]+=v/REPS
        meta.update(sm);missing_total.update(missing)
        reps.append(bins);lagpoints.extend((v,w/REPS,g) for v,w,g in lags)
        print(f'Monte Carlo replication {rep+1}/{REPS} completed',flush=True)
    by_day_input=Counter()
    for e in events:by_day_input[e['weekday']]+=e['enrollment']
    conservation=[]
    for day,n in by_day_input.items():
        for group in ('dorm','snu','nak','daehak'):
            total=sum(v for (d,g,m),v in modes_mean.items() if d==day and g==group)
            assert abs(n-total)<1e-6,(day,group,n,total)
            conservation.append({'weekday':day,'conditional_destination':group,'input_event_weight':n,'assigned_plus_unassigned':round(total,8)})
    write_csv('simulation_conservation.csv',conservation)
    output=[];scenario_summary=[];summaries={}
    for scenario in scenarios():
        prob=probabilities(scenario); share=scenario['immediate_trip_share']; stopbins=defaultdict(float); daymode=defaultdict(float)
        for (day,group,stop,direction,rid,b,stage),v in combined.items():
            if START<=b<END:
                stopbins[(day,stop,direction,rid,b,stage)]+=v*prob[group]*share
        for (day,group,mode),v in modes_mean.items():daymode[(day,mode)]+=v*prob[group]*share
        for (day,stop,direction,rid,b,stage),v in stopbins.items():
            m=meta[(stop,direction,rid)]
            output.append({'scenario':scenario['id'],'weekday':day,'stop_id':stop,'stop_name':m['stop_name'],
                'direction':direction,'route_id':rid,'route_name':m['route_name'],'time_bin':clock(b),
                'bin_minute':b,'boarding_stage':stage+1,'expected_trip_events':round(v,6),'lat':m['lat'],'lon':m['lon']})
        tops={}
        for day in DAYS[:5]:
            physical=defaultdict(float); times=defaultdict(float)
            for (d,stop,direction,rid,b,stage),v in stopbins.items():
                if d==day: physical[(stop,b)]+=v;times[b]+=v
            top=sorted(physical.items(),key=lambda x:x[1],reverse=True)[:8]
            tops[day]=[{'stop_id':s,'stop_name':next(m['stop_name'] for (sid,di,ri),m in meta.items() if sid==s),
                        'time':clock(b),'bin_minute':b,'expected_trip_events':round(v,2)} for (s,b),v in top]
            row={'scenario':scenario['id'],'weekday':day,'input_enrollment_events':by_day_input[day],
                 'generated_trip_events':by_day_input[day]*share,
                 **{mode:round(daymode[(day,mode)],3) for mode in ('walk','city_first','shuttle_first','unassigned')},
                 'boarding_events_in_window':round(sum(times.values()),3)}
            assert abs(sum(row[m] for m in ('walk','city_first','shuttle_first','unassigned'))-row['generated_trip_events'])<.005
            scenario_summary.append(row)
        summaries[scenario['id']]=tops
    write_csv('stop_inflow_5min_scenarios.csv',output)
    write_csv('scenario_summary.csv',scenario_summary)
    dump(ROOT/'outputs/top_stop_peaks.json',summaries)
    # Baseline selects six non-overlapping 5-min windows of maximum total boarding inflow.
    baseline=[r for r in output if r['scenario']==REFERENCE_SCENARIO]
    polling=[]; polling_summary=[]
    for day in DAYS[:5]:
        mass=defaultdict(float)
        for r in baseline:
            if r['weekday']==day:mass[r['bin_minute']]+=r['expected_trip_events']
        peaks=sorted(sorted(mass,key=lambda b:mass[b],reverse=True)[:6])
        base=set(range(START*60,END*60+1,600))
        fast={s for b in peaks for s in range(b*60,(b+5)*60,15)}
        times=sorted(base|fast)
        calls=5*len(times)
        assert calls<=950,(day,calls)
        for second in times:
            polling.append({'weekday':day,'seconds_after_midnight':second,
                'time':f'{second//3600:02d}:{second//60%60:02d}:{second%60:02d}',
                'route_calls':5,'cadence_reason':'15초 집중' if second in fast else '10분 기본'})
        polling_summary.append({'weekday':day,'peak_windows':[f'{clock(b)}–{clock(b+5)}' for b in peaks],
            'full_refreshes':len(times),'planned_api_calls':calls,'within_950_retry_reserve':950-calls,
            'peak_boarding_event_share':round(sum(mass[b] for b in peaks)/sum(mass.values()),4)})
    write_csv('polling_schedule_proposal.csv',polling)
    dump(ROOT/'outputs/polling_summary.json',polling_summary)
    # Stability describes simulation repeatability only, never real-world accuracy.
    stability=[]
    for day in DAYS[:5]:
        peaks=[]
        for bins in reps:
            mass=defaultdict(float)
            for (d,g,s,di,r,b,stage),v in bins.items():
                if d==day and START<=b<END:mass[(s,b)]+=v*({'dorm':REFERENCE_DORM,'snu':(1-REFERENCE_DORM)/3,'nak':(1-REFERENCE_DORM)/3,'daehak':(1-REFERENCE_DORM)/3}[g])*.5
            if mass:peaks.append(max(mass,key=mass.get))
        stability.append({'weekday':day,'replications':len(peaks),'peak_locations_and_times':[
            {'stop_id':s,'time':clock(b),'replications':n} for (s,b),n in Counter(peaks).most_common()]})
    def weighted_quantile(q):
        values=sorted((v,w*({'dorm':REFERENCE_DORM,'snu':(1-REFERENCE_DORM)/3,'nak':(1-REFERENCE_DORM)/3,'daehak':(1-REFERENCE_DORM)/3}[g])) for v,w,g in lagpoints)
        target=sum(w for v,w in values)*q;acc=0
        for v,w in values:
            acc+=w
            if acc>=target:return round(v,2)
    result={'label':'Enrollment-weighted conditional scenarios; no observed passenger or queue counts',
        'seed':SEED,'replications':REPS,'weighted_particles_per_cohort_destination':PARTICLES,
        'eligible_weekday_ending_events':len(events),'eligible_weekday_enrollment_event_sum':sum(by_day_input.values()),
        'building_count':len({e['building'] for e in events}),'destinations':destinations,
        'reference_scenario':REFERENCE_SCENARIO,'reference_dorm_share':REFERENCE_DORM,
        'residence_input':load(ROOT/'sources/residence_user_reference.json'),
        'walking_graph_sha256':hashlib.sha256((APP/'data/walking_osm.json').read_bytes()).hexdigest(),
        'unreachable_building_destination_pairs':[r for r in coverage if r['candidate_count']==0],
        'assumptions':{'immediate_trip_shares':[.25,.5,.75],'dorm_shares':[.1,.2,.3],
            'destination_mix':'Off-campus equal thirds, plus 60/20/20 sensitivity in each direction',
            'walking_speed_mps':'Triangular(0.9, 1.2, 1.5); mapped stairs originally at 0.7 m/s',
            'indoor_egress_seconds':'Triangular(60,180,480), not actual room exit observations',
            'route_choice':'Minimum sampled travel time + 120 sec/transfer + Gumbel(scale 90 sec)',
            'bus_phase':'Uniform phase by route and ending cohort; not synchronized real departures',
            'ride_time':'existing segment distance / 5 m/s + 15 sec per stop',
            'shuttle_service':'2026-2 timetable windows and headway midpoints; fixed administration night / reverse-302 departures',
            'dorm_targets':'919 undergraduate / 900 graduate representative buildings, no individual dorm identity'},
        'conditional_boarding_lag_minutes':{'p10':weighted_quantile(.1),'median':weighted_quantile(.5),'p90':weighted_quantile(.9)},
        'repeatability_not_accuracy':stability,'polling':polling_summary,
        'limits':['Not unique people; individual last-class, attendance, residence and destination are unavailable.',
                  'No background passengers, capacity, live GPS or calibrated queue-length model.',
                  'OSM walking access, representative building pins and elevations require field validation.',
                  'Unknown/timetable-less/crosslisted/remote/ambiguous-subgroup rows excluded from main analysis.',
                  'Polling schedule is an offline proposal; no production scheduler/database was changed.'],
        'elapsed_seconds':round(time.time()-t0,1)}
    dump(ROOT/'outputs/simulation_validation.json',result)
    print(json.dumps({'elapsed_seconds':result['elapsed_seconds'],
        'reference_dorm_share':REFERENCE_DORM,'baseline_top1':{d:rows[:1] for d,rows in summaries[REFERENCE_SCENARIO].items()},
        'planned_daily_calls':[p['planned_api_calls'] for p in polling_summary],
        'unreachable_pairs':len(result['unreachable_building_destination_pairs'])},ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
