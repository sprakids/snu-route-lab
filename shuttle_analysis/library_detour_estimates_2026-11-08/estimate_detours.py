"""Conditional library-detour demand estimates, not a new vehicle/queue simulation.

Frozen weighted v5 origin-departure cohorts are split, never added or removed.
Annual facility counts supply a reference scale, not identified daily people.
"""
from pathlib import Path
from collections import Counter,defaultdict
import ast,csv,gzip,hashlib,importlib.util,json,math,sys
import numpy as np

HERE=Path(__file__).resolve().parent
VIEW=HERE.parent/'simulation_viewer_2026-11-07'
RESEARCH=HERE.parent/'library_flow_research_2026-11-08'
DAYS=['월','화','수','목','금']
ANNUAL_READING,ANNUAL_KWAN=265935,783972
ANNUAL=ANNUAL_READING+ANNUAL_KWAN
LIBS=[('main','중앙도서관 본관',ANNUAL_READING/ANNUAL),('kwan','관정관',ANNUAL_KWAN/ANNUAL)]
COUNT_CASES={'low':{'class_related_share':.30,'entries_per_visit':1.50},
             'reference':{'class_related_share':.50,'entries_per_visit':1.25},
             'high':{'class_related_share':.70,'entries_per_visit':1.00}}
DWELLS={'short':1.,'reference':2.,'long':4.}
Q=9
MIN_STUDY=1800.
STEP=1800
HORIZON=36*3600

def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,x):
    (HERE/name).write_text(json.dumps(x,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8')
def csvfile(name,rows):
    with (HERE/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def clock(t):
    s=int(t);suffix='(+1일)' if s>=86400 else ''
    return f'{s//3600%24:02d}:{s//60%60:02d}'+suffix
def hist(times,weights):return np.histogram(times,bins=np.arange(0,HORIZON+STEP,STEP),weights=weights)[0]
def percentile(times,weights,q):
    # One-minute aggregation is disclosed; avoids claiming sub-minute precision.
    bins=np.bincount(np.floor(times/60).astype(int),weights=weights,minlength=HORIZON//60)
    if bins.sum()<1e-9:return None
    return int(np.searchsorted(np.cumsum(bins),q*bins.sum()))*60+30

def walking_inputs(bundle):
    # Reuse only frozen, pure routing definitions; no app imports or network calls.
    sys.dont_write_bytecode=True
    routing_path=VIEW/'model_snapshot/app/routing.py'
    spec=importlib.util.spec_from_file_location('library_frozen_routing',routing_path)
    routing=importlib.util.module_from_spec(spec);spec.loader.exec_module(routing)
    engine_path=VIEW/'model_snapshot/engine/simulate_stop_inflow.py'
    tree=ast.parse(engine_path.read_text(encoding='utf-8'))
    cls=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='MatrixWalker')
    scope={'Counter':Counter,'np':np,'distance':routing.distance}
    exec(compile(ast.Module(body=[cls],type_ignores=[]),str(engine_path),'exec'),scope)
    payload_path=VIEW/'model_snapshot/app/data/walking_osm.json'
    graph=routing.WalkingGraph(read(payload_path))
    buildings={b['id']:(b['lat'],b['lon']) for b in bundle['prepared']['common']['buildings']}
    map_path=VIEW/'model_snapshot/runtime/sources/campus_buildings.json'
    raw=read(map_path)['rows'];points={}
    for key,name,_ in LIBS:
        row=next(r for r in raw if r['vil_dong_nm']==('62' if key=='main' else '62-1'))
        points[key]=(float(row['lat_val']),float(row['lon_val']))
    node=bundle['prepared']['common']['nodes'][bundle['prepared']['common']['hot_nodes']['admin_snu']]
    admin=(node['lat'],node['lon'])
    walker=scope['MatrixWalker'](graph,list(buildings.values())+list(points.values())+[admin])
    paths={};rows=[]
    for bid,origin in buildings.items():
        for key,name,_ in LIBS:
            result=walker.walk(origin,points[key]);paths[bid,key]=result
            rows.append({'building':bid,'library':key,'walk_seconds_reference':result['seconds'] if result else None,
                'meters':result['meters'] if result else None,'steps_m':result['steps_m'] if result else None,
                'connector_m':result['connectors_m'] if result else None,'origin_snap_m':walker.snaps[origin][1],
                'library_snap_m':walker.snaps[points[key]][1]})
    toadmin={key:walker.walk(point,admin) for key,point in points.items()}
    save('walking_inputs.json',{'component':walker.component_profile,'libraries':points,'paths':rows,'library_to_admin':toadmin,
        'walking_assumption':'Frozen v5 group profile: ordinary1.2m/s, mapped steps0.7m/s, each saved particle scale also applied. Not app personal4.8km/h.'})
    return paths,toadmin,[routing_path,engine_path,payload_path,map_path]

def main():
    HERE.mkdir(exist_ok=True)
    bundle_path=VIEW/'city_bus_model_2026-11-08/prepared.json.gz';bundle=read(bundle_path)
    walk,toadmin,walk_sources=walking_inputs(bundle)
    sources=[bundle_path,*walk_sources,RESEARCH/'annual_utilization_verified.json',RESEARCH/'sources/bulletin_148_2026.pdf',RESEARCH/'sources/rinfo_2026_survey_manual.pdf']
    hashes=[{'path':p.relative_to(HERE.parent).as_posix(),'sha256':sha(p)} for p in sources]
    byday={};eligibility={}
    for day in DAYS:
        plans=bundle['prepared']['plans'][day]
        dep=np.array([p[4] for p in plans]);mass=np.array([p[3] for p in plans]);upper=np.array([p[1] in ('301','302') for p in plans])
        external=np.array([p[2]!='dorm' for p in plans]);snu=np.array([p[2]=='snu' for p in plans])
        scale=np.array([bundle['walk_scales'][str(p[0])] for p in plans])
        arrivals={key:np.array([walk[p[1],key]['seconds'] if walk[p[1],key] else np.nan for p in plans])*scale+dep for key,_,_ in LIBS}
        byday[day]={'plans':plans,'dep':dep,'mass':mass,'upper':upper,'external':external,'snu':snu,'scale':scale,'arrivals':arrivals}
    weekly_source=math.fsum(float(x['mass'].sum()) for x in byday.values())
    assert abs(weekly_source-78169)<1e-6
    # No claim that annual/365 is an observed weekday; it is a normalization only.
    ref_week=ANNUAL/365*5
    cases=[]
    for count in COUNT_CASES:
        for dwell in DWELLS:cases.append((count+'_'+dwell,count,dwell,1.,False))
    cases.extend([('weekday_scale_1p5','reference','reference',1.5,False),
                  ('main_24h_reference','reference','reference',1.,True),
                  ('main_24h_long','reference','long',1.,True)])
    summary=[];cells=[];checks=[];profiles={};config=[]
    for case,count,dwell,weekday_scale,main24 in cases:
        count_spec=COUNT_CASES[count];budget=ref_week*count_spec['class_related_share']/count_spec['entries_per_visit']*weekday_scale
        eligible_mass=0.
        for day,x in byday.items():
            for key,name,libshare in LIBS:
                cap=np.inf if main24 and key=='main' else 23*3600.
                eligible=np.isfinite(x['arrivals'][key])&(x['arrivals'][key]+MIN_STUDY<=cap)
                eligibility[case,day,key]=eligible
                eligible_mass+=float(x['mass'][eligible].sum())*libshare
        p=budget/eligible_mass;assert 0<=p<=1
        config.append({'case':case,'count_case':count,'dwell_case':dwell,'target_weekly_library_visits':budget,
            'eligible_source_mass':eligible_mass,'library_probability_given_eligible':p,'weekday_scale':weekday_scale,
            'mean_unconstrained_dwell_hours':DWELLS[dwell],'dwell_distribution':'Uniform[0.5*mean,1.5*mean],9 midpoint quadrature values',
            'main_24hour_sensitivity':main24,**count_spec})
        for day,x in byday.items():
            kept=x['mass'].copy();parts=[]
            for key,name,libshare in LIBS:
                eligible=eligibility[case,day,key];selected=x['mass']*p*libshare*eligible;kept-=selected
                arr=x['arrivals'][key];valid=selected>0
                cap=np.inf if main24 and key=='main' else 23*3600.
                for i in range(Q):
                    dwell_seconds=DWELLS[dwell]*3600*(.5+(i+.5)/Q)
                    raw_exit=arr[valid]+dwell_seconds;exit=np.minimum(raw_exit,cap)
                    weights=selected[valid]/Q
                    assert np.all(exit>=arr[valid]+MIN_STUDY-1e-7)
                    parts.append({'library':key,'arrival':arr[valid],'exit':exit,'departure':x['dep'][valid],
                        'weight':weights,'upper':x['upper'][valid],'external':x['external'][valid],
                        'snu':x['snu'][valid],'closure':raw_exit>cap,
                        'admin_arrival':exit+toadmin[key]['seconds']*x['scale'][valid]})
            assert kept.min()>-1e-7
            for scope,mask in [('all',np.ones(len(kept),bool)),('external',x['external']),('upper',x['upper']),('upper_external',x['upper']&x['external']),('snu',x['snu'])]:
                ts=[];ws=[];arrs=[];deps=[];closures=[];admin_ts=[];admin_ws=[]
                for part in parts:
                    if scope=='all':m=np.ones(len(part['weight']),bool)
                    elif scope=='upper_external':m=part['upper']&part['external']
                    else:m=part[scope]
                    ts.append(part['exit'][m]);ws.append(part['weight'][m]);arrs.append(part['arrival'][m]);deps.append(part['departure'][m]);closures.append(part['closure'][m])
                    if scope=='snu':admin_ts.append(part['admin_arrival'][m]);admin_ws.append(part['weight'][m])
                exits=np.concatenate(ts);weights=np.concatenate(ws);arrivals=np.concatenate(arrs);departures=np.concatenate(deps);clipped=np.concatenate(closures)
                source=float(x['mass'][mask].sum());direct=float(kept[mask].sum());lib=float(weights.sum())
                assert abs(source-direct-lib)<1e-6,(case,day,scope)
                assert not len(exits) or exits.max()<HORIZON
                bh=hist(x['dep'][mask],x['mass'][mask]);dh=hist(x['dep'][mask],kept[mask]);lh=hist(exits,weights);eh=hist(arrivals,weights)
                after18=exits>=18*3600;end=exits>=23*3600+10*60
                hists={'baseline_origin_departures':bh.tolist(),'retained_direct_origin_departures':dh.tolist(),'library_exits':lh.tolist(),'library_entries':eh.tolist()}
                late_origin=departures>=18*3600
                late_exit_hist=hist(exits[late_origin],weights[late_origin])
                profiles[case,day,scope]=hists
                # Queue-free classroom/libraries only. This is not a home ETA or a gate crossing.
                row={'case':case,'weekday':day,'scope':scope,'source_weight':source,'retained_direct_weight':direct,
                    'library_detour_weight':lib,'after18_library_exit_weight':float(weights[after18].sum()),
                    'after18_origin_departure_library_weight':float(weights[departures>=18*3600].sum()),
                    'after18_origin_departure_exit_after18_weight':float(weights[(departures>=18*3600)&after18].sum()),
                    'after18_origin_median_exit_seconds_1min':percentile(exits[late_origin],weights[late_origin],.5),
                    'after18_origin_p90_exit_seconds_1min':percentile(exits[late_origin],weights[late_origin],.9),
                    'after18_origin_exit_21_24_weight':float(weights[late_origin&(exits>=75600)&(exits<86400)].sum()),
                    'library_present_at18_weight':float(weights[(arrivals<=18*3600)&(exits>18*3600)].sum()),
                    'exit_18_21_weight':float(weights[(exits>=18*3600)&(exits<21*3600)].sum()),
                    'exit_21_24_weight':float(weights[(exits>=21*3600)&(exits<24*3600)].sum()),
                    'exit_after24_weight':float(weights[exits>=86400].sum()),
                    'exit_beyond_old_horizon_weight':float(weights[end].sum()),
                    'forced_closing_weight':float(weights[clipped].sum()),
                    'mean_dwell_min':float(np.sum((exits-arrivals)*weights)/lib/60) if lib else None,
                    'mean_exit_seconds':float(np.sum(exits*weights)/lib) if lib else None,
                    'median_exit_seconds_1min':percentile(exits,weights,.5),'p90_exit_seconds_1min':percentile(exits,weights,.9),
                    'after18_median_exit_seconds_1min':percentile(exits[after18],weights[after18],.5),
                    'after18_p90_exit_seconds_1min':percentile(exits[after18],weights[after18],.9),
                    'baseline_commute_phase_departures_18_19':float(x['mass'][mask&(x['dep']>=64800)&(x['dep']<68400)].sum()),
                    'retimed_commute_phase_departures_18_19':float(kept[mask&(x['dep']>=64800)&(x['dep']<68400)].sum()+weights[(exits>=64800)&(exits<68400)].sum()),
                    'baseline_commute_phase_departures_21_24':float(x['mass'][mask&(x['dep']>=75600)&(x['dep']<86400)].sum()),
                    'retimed_commute_phase_departures_21_24':float(kept[mask&(x['dep']>=75600)&(x['dep']<86400)].sum()+weights[(exits>=75600)&(exits<86400)].sum()),
                    'peak_library_exit_bin_start':int(lh.argmax())*STEP,
                    'peak_library_exit_bin_weight':float(lh.max())}
                summary.append(row)
                for k in range(len(lh)):
                    if bh[k]+dh[k]+lh[k]+eh[k]<=1e-9:continue
                    cells.append({'case':case,'weekday':day,'scope':scope,'start_seconds':k*STEP,'end_seconds':(k+1)*STEP,
                        'window':clock(k*STEP)+'~'+clock((k+1)*STEP),'baseline_origin_departures':float(bh[k]),
                        'retained_direct_origin_departures':float(dh[k]),'library_entries':float(eh[k]),'library_exits':float(lh[k]),
                        'library_exits_from_after18_origin':float(late_exit_hist[k]),
                        'retimed_commute_phase_departures':float(dh[k]+lh[k]),'net_change_commute_phase_departures':float(dh[k]+lh[k]-bh[k]),
                        'location_note':'Original classroom-origin departures and later library-origin departures; not stop inflow or boardings.'})
                checks.append({'case':case,'weekday':day,'scope':scope,'mass_error':source-direct-lib,
                    'histogram_total_error':float((dh+lh).sum()-bh.sum())})
            print(case,day,'done',flush=True)
    save('scenario_specs.json',{'source_annual_count':ANNUAL,'scope':'본관 열람실+관정관; 자료실245392 제외',
        'reference_week_formula':'annual/365*5*class_related_share/entries_per_visit*weekday_scale; calendar-average reference, not an observed weekday estimate',
        'not_identified_from_observations':['class_related_share','entries_per_visit','weekday_scale','dwell_distribution','building_and_weekday_detour_preference','daily_unique_persons'],
        'source_weekly_trip_weight':weekly_source,'cases':config,'current_data_year':'2025-03-01 through2026-02-28','course_snapshot':'2026-11-06',
        'counts_are_confidence_intervals':False,'individual_last_classes_known':False,'new_vehicle_queue_simulation':False})
    save('daily_estimates.json',summary);csvfile('daily_estimates.csv',summary);save('half_hour_departures.json',cells);csvfile('half_hour_departures.csv',cells)
    # Compact handoff covers demand shifts only; never insert these rows as unchanged-stop flows.
    save('integration_contract.json',{'schema':'library_detour_conditional_demand_v1','time_unit':'seconds since source weekday midnight; >=86400 belongs to next day',
        'count_unit':'weighted class-end trip/visit events, not unique students','base_weekly_mass':weekly_source,
        'case_default_for_review':'reference_reference','scenario_is_fitted':False,'transit_queue_rerun':False,
        'new_flow_files':['daily_estimates.json','half_hour_departures.json'],'source_hashes':hashes,
        'route_integration_rule':'Subtract diverted mass from its original classroom-origin cohort, then route library-origin exits at their new times; do not add exits to old demand without subtraction. Raw cohorts can be regenerated from frozen bundle and this script.',
        'preserved_unknown_population':'The unmodeled other50percent of class enrollment is not added. Actual final home addresses are unavailable.'})
    for r in hashes:assert sha(HERE.parent/r['path'])==r['sha256']
    maxerr=max(abs(c['mass_error']) for c in checks);histerr=max(abs(c['histogram_total_error']) for c in checks)
    assert maxerr<1e-6 and histerr<1e-6
    for case,_,_,_,_ in cases:
        actual=sum(r['library_detour_weight'] for r in summary if r['case']==case and r['scope']=='all')
        target=next(r['target_weekly_library_visits'] for r in config if r['case']==case)
        assert abs(actual-target)<1e-6
    save('verification.json',{'status':'PASS','cases':len(cases),'weekday_scope_cases':len(checks),'max_mass_error':maxerr,'max_histogram_mass_error':histerr,
        'annual_subtotals_reconciled':True,'weekly_source_weight':weekly_source,'all_source_hashes_unchanged':True,'sources':hashes,
        'model_or_app_modified':False,'new_upstream_api_calls':0,'observed_daily_library_data_available':False,'unique_people_or_home_eta_claimed':False})
    print('PASS',len(cases),len(summary),len(cells),flush=True)

if __name__=='__main__':main()
