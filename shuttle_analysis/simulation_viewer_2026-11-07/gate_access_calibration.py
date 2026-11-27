"""Provisional initial gate access choices; preserve v5 demand, clocks and IDs."""
from pathlib import Path
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from bisect import bisect_right
import argparse, copy, csv, gzip, hashlib, json, math, subprocess, sys, time

sys.dont_write_bytecode = True
import capacity_model as base
import city_capacity_model as model

ROOT = Path(__file__).resolve().parent
WORK = ROOT / 'gate_access_calibration_2026-11-09'
SOURCE = ROOT / 'city_bus_model_2026-11-08/prepared.json.gz'
FIELD = ROOT.parent / 'field_observations_2026-11-09'
ALPHAS = (.25,.5,.75)
CUTOFF = 900.0
SALT = 'initial-gate-choice-20261109-v1'
OBSERVATIONS = [
    {'id':'admin_snu_1653','stop':'admin_snu','minute':1013,'people_interval':[53,53]},
    {'id':'culture_1655','stop':'city_120000195','minute':1015,'people_interval':[5,5]},
    {'id':'snu_gate_1703','stop':'city_gate','minute':1023,'people_interval':[33,39]},
]


def read(path):
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_bytes())


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    base.save(path,data)


def folder(alpha):
    return WORK / 'candidates' / f'alpha_{round(alpha*100):03}'


def protected():
    paths=[SOURCE,ROOT/'capacity_model.py',ROOT/'city_capacity_model.py',ROOT/'prepare_city.py',ROOT/'verify_city.py']
    for dataset in ('capacity_v5','capacity_v6'):
        paths.extend(sorted((ROOT/'public/data'/dataset).glob('*')))
    paths.extend(sorted((ROOT/'public/routing-model').rglob('*.json')))
    return {p.relative_to(ROOT).as_posix():base.sha(p) for p in paths if p.is_file()}


def geometry():
    cached=WORK/'gate_geometry.json.gz'
    source_sha=base.sha(SOURCE)
    if cached.exists():
        result=read(cached);assert result['source_sha256']==source_sha;return result
    bundle=read(SOURCE);prepared=bundle['prepared'];common=prepared['common']
    gate=base.point(common['nodes'][common['hot_nodes']['city_gate']])
    origins={tuple(common['paths'][p[5][0]][0]) for plans in prepared['plans'].values() for p in plans
             if p[6] and bundle['destination_keys'][str(p[0])]=='snu'}
    engine=base.module('gate_access_saved_engine',ROOT/'model_snapshot/engine/simulate_stop_inflow.py')
    graph=engine.WalkingGraph(base.read(ROOT/'model_snapshot/app/data/walking_osm.json'))
    walker=engine.MatrixWalker(graph,[*origins,gate]);result={}
    for origin in sorted(origins):
        walk=walker.walk(origin,gate)
        if not walk:continue
        a,_=walker.snaps[origin];b,_=walker.snaps[tuple(gate)]
        parents=graph.tree(a)[1];chain=[b]
        while chain[-1]!=a:chain.append(parents[chain[-1]][0])
        points=[origin]+[graph.nodes[n] for n in reversed(chain)]+[gate]
        result[json.dumps(origin)]={'seconds':walk['seconds'],'meters':walk['meters'],
                                    'connector_max_m':max(walker.snaps[origin][1],walker.snaps[tuple(gate)][1]),
                                    'points':[[round(float(x),6),round(float(y),6)] for x,y in points]}
    data={'source_sha256':source_sha,'walking_graph_sha256':base.sha(ROOT/'model_snapshot/app/data/walking_osm.json'),
          'source':'preserved_main_component_OSM_walking_graph_110m_connector_limit', 'origins':result}
    base.packed(cached,data);return data


def prepare(alpha):
    work=folder(alpha);work.mkdir(parents=True,exist_ok=True)
    cached=work/'prepared.json.gz'
    if cached.exists():
        result=read(cached)
        assert result['gate_access_calibration']['source_sha256']==base.sha(SOURCE)
        assert result['gate_access_calibration']['alpha']==alpha
        return result
    bundle=read(SOURCE);prepared=bundle['prepared'];common=prepared['common'];geo=geometry()
    gate=common['hot_nodes']['city_gate'];template=next(o for o in bundle['alternatives'][f'{gate}|snu'] if o['kind']=='gate_pool')
    identifiers=set();rows=[];paths={};before=Counter();after=Counter();checked=0
    for day,plans in prepared['plans'].items():
        for p in plans:
            assert p[0] not in identifiers;identifiers.add(p[0])
            before[day]+=p[3]
            if not p[6] or bundle['destination_keys'][str(p[0])]!='snu':continue
            first=p[6][0];stop=prepared['routes'][first['rid']]['stops'][first['board']]
            if stop['id']=='120000029':continue
            origin=common['paths'][p[5][0]][0];key=json.dumps(tuple(origin));walk=geo['origins'].get(key)
            if not walk:continue
            factor=bundle['walk_scales'][str(p[0])];seconds=walk['seconds']*factor
            if seconds>=CUTOFF:continue
            probability=alpha*(1-seconds/CUTOFF)
            uniform=int.from_bytes(hashlib.sha256(f'{SALT}:{p[0]}'.encode()).digest()[:8],'big')/2**64
            checked+=1
            if uniform>=probability:continue
            if key not in paths:
                paths[key]=len(common['paths']);common['paths'].append(walk['points'])
            rows.append({'weekday':day,'particle_id':p[0],'building':p[1],'destination':p[2],
                         'departure_second':p[4],'departure_half_hour':int(p[4]//1800)*1800,
                         'original_first_route':first['rid'],'original_first_stop':stop['id'],
                         'weight':p[3],'gate_walk_seconds':seconds,'gate_walk_meters':walk['meters'],
                         'planned_gate_ready_second':p[4]+seconds+20,
                         'choice_probability':probability,'stable_uniform':uniform})
            p[5]=[paths[key],seconds]
            p[6]=model.scaled_stages(template['stages'],factor)
        after[day]=math.fsum(p[3] for p in plans)
    assert set(before)==set(after) and all(abs(before[d]-after[d])<1e-6 for d in before)
    expected={d:math.fsum(p[3] for p in plans) for d,plans in prepared['plans'].items()}
    source=read(SOURCE)
    for day,plans in prepared['plans'].items():
        old={p[0]:p for p in source['prepared']['plans'][day]}
        for p in plans:
            q=old[p[0]];assert p[:5]==q[:5]
    assert common['route_info']==source['prepared']['common']['route_info']
    model_id=datetime.now(timezone(timedelta(hours=9))).strftime('%y%m%d%H%M%S')
    meta={'model_id':model_id,'algorithm_id':'provisional_initial_gate_access_v1','alpha':alpha,
          'walking_cutoff_seconds':CUTOFF,'probability_rule':'alpha * max(0, 1 - individual_gate_walk_seconds / 900)',
          'gate_ars':'21128','source_simulation':'capacity_v5','source_sha256':base.sha(SOURCE),
          'observations_used_for_candidate_selection':[o['id'] for o in OBSERVATIONS],
          'observation_second':'unknown; uniform within reported minute',
          'independent_validation':False,'observed_mode_shares':False,'new_demand_added':False,
          'timetable_speed_capacity_changed':False,'candidate_only':True}
    bundle['gate_access_calibration']=meta
    common['gate_access_calibration']=meta
    common['source_note']='관측 3건을 참고한 정문 초기 도보 접근 보정 후보 · 독립 검증 전 · 전체 가중 수요 보존'
    common['data_version']=7
    base.packed(cached,bundle)
    moved=Counter();groups=Counter()
    for row in rows:
        moved[row['weekday']]+=row['weight']
        groups[row['weekday'],row['building'],row['departure_half_hour'],row['original_first_route']]+=row['weight']
    save(work/'preparation_verification.json',{'status':'PASS','metadata':meta,'eligible_particles':checked,
         'rerouted_particles':len(rows),'total_weight_by_day':expected,'rerouted_weight_by_day':dict(moved),
         'demand_mass_max_error':max(abs(before[d]-after[d]) for d in before),
         'same_ids_weights_origins_destinations_departures':True,'same_vehicle_supply_and_speed':True})
    with (work/'reallocated_particles.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
    with (work/'reallocation_by_building_time_mode.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['weekday','building','departure_half_hour_second','original_first_route','weight'])
        w.writerows([*k,v] for k,v in sorted(groups.items()))
    return bundle


def minute_summary(data,common):
    result=[]
    for obs in OBSERVATIONS:
        node=common['hot_nodes'][obs['stop']];rows=data['queue_timeline'][node];times=[r[0] for r in rows]
        start=obs['minute']*60;end=start+60;low,high=obs['people_interval']
        def point(t):
            i=bisect_right(times,t)-1;return rows[i][1] if i>=0 else 0.
        breaks=[start,*[t for t in times if start<t<end],end]
        vals=[point(t) for t in breaks[:-1]]
        mean=math.fsum(point(a)*(b-a) for a,b in zip(breaks,breaks[1:]))/60
        error=math.fsum(max(low-point(a),point(a)-high,0)*(b-a) for a,b in zip(breaks,breaks[1:]))/60
        coverage=math.fsum((b-a) for a,b in zip(breaks,breaks[1:]) if low-.5<=point(a)<=high+.5)/60
        result.append({**obs,'node':node,'uniform_minute_mean':mean,'temporal_min_max':[min(vals),max(vals)],
                       'expected_absolute_distance_to_report_interval':error,
                       'fraction_of_minute_in_report_interval_with_half_person_rounding':coverage,
                       'not_independent_validation':True})
    return result


def run(alpha,day,scenario):
    bundle=prepare(alpha);work=folder(alpha);out=work/'public_data';out.mkdir(exist_ok=True)
    model.WORK=work;model.OUT=out;base.OUT=out
    base.public('common.json',bundle['prepared']['common'])
    t=time.perf_counter();data=model.simulate(bundle,day,scenario)
    result={'status':'PASS','model_id':bundle['gate_access_calibration']['model_id'],'alpha':alpha,
            'elapsed_seconds':time.perf_counter()-t,'scenario':scenario,'weekday':day,'report':data['report']}
    if day=='월':result['observation_fit']=minute_summary(data,bundle['prepared']['common'])
    save(work/f'run-{scenario}-{base.DAYS[day]}.json',result)


def screen():
    WORK.mkdir(exist_ok=True)
    if (WORK/'screening_results.json').exists():
        previous=read(WORK/'screening_results.json');assert previous['status']=='PASS'
        print('SCREEN_ALREADY_COMPLETE',previous['selected_alpha'],previous['selected_model_id'],flush=True)
        return
    if (WORK/'experiment_plan.json').exists():
        raise RuntimeError('An incomplete bounded screening exists; inspect preserved evidence before attempting another run.')
    before=protected()
    save(WORK/'protected_source_hashes.json',before)
    save(WORK/'experiment_plan.json',{'status':'predeclared_screening','alphas':ALPHAS,'cutoff_seconds':CUTOFF,
         'selection_scenario':'peak','selection_day':'월','observations':OBSERVATIONS,
         'timing_model':'uniform within minute; no selected best-fitting second',
         'primary_metric':'mean of per-observation expected absolute interval distance divided by max(5, interval midpoint)',
         'tie_breaker':'smaller alpha','originals_and_current_default_preserved':True,
         'independent_validation':False})
    geometry()
    for alpha in ALPHAS:prepare(alpha)
    def worker(alpha):
        log=folder(alpha)/'screen-peak-mon.log'
        with log.open('w',encoding='utf-8') as f:
            r=subprocess.run([sys.executable,str(Path(__file__)), '--run',str(alpha),'--day','월','--scenario','peak'],
                             stdout=f,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert r.returncode==0,(alpha,str(log));print('SCREEN_DONE',alpha,flush=True)
        return read(folder(alpha)/'run-peak-mon.json')
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,ALPHAS))
    for r in results:
        r['normalized_fit_loss']=statistics_score(r['observation_fit'])
    selected=min(results,key=lambda r:(r['normalized_fit_loss'],r['alpha']))
    baseline=read(ROOT/'public/data/capacity_v5/peak-mon.json')
    baseline_fit=minute_summary(baseline,read(SOURCE)['prepared']['common'])
    assert before==protected(),'protected original files changed'
    save(WORK/'screening_results.json',{'status':'PASS','candidates':results,'selected_alpha':selected['alpha'],
         'selected_model_id':selected['model_id'],'baseline_fit':baseline_fit,
         'baseline_normalized_fit_loss':statistics_score(baseline_fit),
         'selection_uses_same_three_observations':True,'independent_validation':False,'protected_sources_unchanged':True})
    print('SELECTED',selected['alpha'],selected['normalized_fit_loss'],flush=True)


def statistics_score(rows):
    return math.fsum(r['expected_absolute_distance_to_report_interval']/max(5,sum(r['people_interval'])/2) for r in rows)/len(rows)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--screen',action='store_true');parser.add_argument('--run',type=float)
    parser.add_argument('--day',choices=list(base.DAYS),default='월');parser.add_argument('--scenario',choices=list(base.SCENARIOS),default='peak')
    args=parser.parse_args()
    if args.screen:screen()
    else:run(args.run,args.day,args.scenario)


if __name__=='__main__':main()
