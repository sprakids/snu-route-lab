"""Export compact immutable v5 timing inputs; never modify app or model files."""
from pathlib import Path
from datetime import datetime,timezone
import ast,copy,gzip,hashlib,json,math,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT))
import capacity_model as base
import city_capacity_model as reference
import speed_capacity_model as speed
from bridge import kinematic_profile,first_boardable,ride_seconds


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(name,value):
    (HERE/name).write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8')


def main():
    bundle_path=ROOT/'city_bus_model_2026-11-08/prepared.json.gz'
    bundle=json.loads(gzip.decompress(bundle_path.read_bytes()));prepared=bundle['prepared'];common=prepared['common']
    assert common['city_speed_revision']=='campus_stop_corridors_20261108'
    ring=common['bus_speed_model']['campus_polygon']
    road=base.read(ROOT/'model_snapshot/road_geometry.json')['routes']
    gate=next(i for i,s in enumerate(prepared['routes']['100100251']['stops']) if s['id']=='120000029')
    for rid in ('100100252','100100263','100100521'):road[rid]={'segments':road['100100251']['segments'][gate:gate+4]}
    routes={};fixtures=[];checks=0;max_error=0.;sample_kinds=set()
    for rid,info in common['route_info'].items():
        original=prepared['routes'][rid];segments=[];city=info.get('city',False)
        for i,pid in enumerate(info['segments']):
            stored=common['motion_profiles'][str(pid)]
            points=road[rid]['segments'][i]['geometry'] if city else common['paths'][pid]
            source=info.get('segment_time_sources',[{}]*len(info['segments']))[i]
            forced=source.get('campus_stop_corridor_40',False)
            actual=kinematic_profile(points,[len(points)-1],ring,forced)
            error=abs(actual['duration']-stored['duration']);max_error=max(max_error,error)
            assert error<1e-5,(rid,i,error)
            assert actual['cap']==stored['cap'],(rid,i,'zone phases')
            assert abs(actual['d'][-1]-stored['d'][-1])<1e-5
            for k,cap in enumerate(actual['cap']):assert max(actual['v'][k],actual['v'][k+1])*3.6<=cap+1e-4
            seconds=info['offsets'][i+1]-info['offsets'][i]
            assert seconds>=stored['duration']-1e-5
            segments.append({'from_index':i,'to_index':i+1,'model_seconds':seconds,
                'meters':stored['d'][-1],'kinematic_seconds':stored['duration'],
                'inside_m':stored['inside_m'],'outside_m':stored['outside_m'],
                'kinematic_destination_dwell_seconds':15.,'campus_stop_corridor_40':forced,
                'saved_speed_kmh':source.get('speed_kmh'),'observed_trip_time':False})
            kinds={'override' if forced else 'mixed' if stored['inside_m']>0 and stored['outside_m']>0 else 'outside' if not stored['inside_m'] else 'polygon'}
            kind=next(iter(kinds))
            if kind not in sample_kinds:
                sample_kinds.add(kind);fixtures.append({'name':kind,'route_id':rid,'segment_index':i,
                    'points':points,'cuts':[len(points)-1],'force_campus':forced,
                    'expected_kinematic_seconds':stored['duration'],'expected_model_seconds':seconds})
            checks+=1
        row={'name':original['name'],'city':city,'boarding_node_count':info['n'],'anchor_index':info['anchor'],
             'offsets_seconds':info['offsets'],'segments':segments,
             'stops':[{'index':i,'id':s['id'],'source_seq':s.get('seq'),'name':s['name'],
                       'lat':s['lat'],'lon':s['lon'],'board_allowed':s.get('board_allowed',True),
                       'alight_allowed':s.get('alight_allowed',True)} for i,s in enumerate(original['stops'])],
             'capacity_scenario':info.get('capacity',25 if rid=='shuttle-41914' else 60),
             'actual_vehicle_capacity_verified':False,
             'partial_route':bool(original.get('partial_route')),
             'zone_rule':'campus_stop_override_plus_polygon' if city else 'frozen_v3_polygon'}
        if city:row.update(weekday_plan=info['plan'],origin_to_modeled_first_seconds=info['origin_to_modeled_first_stop_seconds'])
        else:row['anchor_dispatches_seconds']={s:base.dispatches(rid,s) for s in base.SCENARIOS}
        routes[rid]=row
    data={'schema_version':1,'scenario_revision':common['city_speed_revision'],'units':{'time':'seconds after KST service-day midnight','distance':'metres','point':'latitude,longitude'},
          'observed_operations':False,'destination_dwell_convention':'kinematic profile includes final-stop dwell; city max with snapshot-speed total adds no second dwell',
          'campus_polygon':ring,'campus_stop_names':common['city_campus_stop_names'],'routes':routes}
    save('route_time_inputs.json',data)
    from prepare_city import CampusRoad
    for name,points,cuts in [
        ('zero_distance_destination_dwell',[[37.45,126.95]],[0]),
        ('two_stops_two_destination_dwells',[[37.45,126.95],[37.451,126.95],[37.452,126.95]],[1,2]),
    ]:
        p=speed.profile(points,cuts,CampusRoad())
        fixtures.append({'name':name,'points':points,'cuts':cuts,'force_campus':True,
            'expected_kinematic_seconds':p['duration'],'expected_model_seconds':p['duration']})
    # Inputs exercise the original reference branch, not an invented fleet load.
    stage=lambda rid='A':{'rid':rid,'board':0,'alight':1}
    vehicle=lambda rid='A',load=0,target=1:{'rid':rid,'cap':50.,'last_stop':-1,'onboard':[(target,{'w':load})] if load else []}
    cases=[
        {'name':'full_bus_skip','rows':[(100.,0,0),(200.,1,0)],'vehicles':[vehicle(load=50),vehicle()],'stage':stage(),'weight':1.,'waiting':[],'expected':200.},
        {'name':'alight_frees_space','rows':[(100.,0,0)],'vehicles':[vehicle(load=50,target=0)],'stage':stage(),'weight':1.,'waiting':[],'expected':100.},
        {'name':'incompatible_queue','rows':[(100.,0,0)],'vehicles':[vehicle()],'stage':stage(),'weight':1.,'waiting':[{'w':100.,'stages':[stage('B')],'stage':0}],'expected':100.},
        {'name':'weighted_partial_completion','rows':[(100.,0,0),(200.,1,0)],'vehicles':[vehicle(),vehicle()],'stage':stage(),'weight':30.,'waiting':[{'w':30.,'stages':[stage()],'stage':0}],'expected':200.},
        {'name':'first_pool_bus_with_space','rows':[(100.,0,0),(110.,1,0)],'vehicles':[vehicle(load=50),vehicle('B')],'stage':{**stage(),'pool':[stage(),stage('B')]},'weight':1.,'waiting':[],'expected':110.},
    ]
    for case in cases:
        args=[case[k] for k in ('rows','vehicles')]+[0.,0.,case['stage'],case['weight'],case['waiting']]
        before=copy.deepcopy(args);a=first_boardable(*args);b=reference.first_boardable(*copy.deepcopy(args))
        assert args==before and a==b and a[0]==case['expected'],case['name']
    save('fixtures.json',{'profile_cases':fixtures,'queue_cases':cases,'ring_source':'route_time_inputs.json:campus_polygon'})
    files=['capacity_model.py','speed_capacity_model.py','city_capacity_model.py','prepare_city.py','prepare_adaptive.py',
           'model_snapshot/app/routing.py','model_snapshot/engine/simulate_stop_inflow.py','verify_city.py']
    manifest=[]
    for name in files:
        path=ROOT/name;tree=ast.parse(path.read_text(encoding='utf-8'))
        definitions=[{'name':n.name,'line':n.lineno} for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.ClassDef))]
        manifest.append({'path':name,'sha256':sha(path),'definitions':definitions})
    app_refs=[];snap=HERE/'app_reference_snapshot';snap.mkdir(exist_ok=True)
    for name in ['routing.py','travel_time.py','gate_service.py','automatic_queue.py','prepare_auto_queue.py','shuttle_timetable.py']:
        path=ROOT.parent/'app'/name;raw=path.read_bytes();(snap/name).write_bytes(raw)
        app_refs.append({'path':'app/'+name,'sha256':hashlib.sha256(raw).hexdigest()})
    save('source_manifest.json',{'captured_at_utc':datetime.now(timezone.utc).isoformat(),'simulation_sources':manifest,'app_sources_compared':app_refs,'v5_prepared_sha256':sha(bundle_path),
         'bridge_sha256':sha(HERE/'bridge.py'),'output_sha256':sha(HERE/'route_time_inputs.json')})
    save('verification.json',{'status':'PASS','routes':len(routes),'segments_compared_to_frozen_v5':checks,
         'max_duration_error_seconds':max_error,'queue_reference_cases':len(cases),'capacity_and_speed_phases_checked':True,
         'standard_library_runtime':True,'app_files_modified':False,'original_model_modified':False,'original_results_recomputed':False})
    print(json.dumps({'status':'PASS','routes':len(routes),'segments':checks,'max_error':max_error,'queue_cases':len(cases),'json_bytes':(HERE/'route_time_inputs.json').stat().st_size}))


if __name__=='__main__':main()
