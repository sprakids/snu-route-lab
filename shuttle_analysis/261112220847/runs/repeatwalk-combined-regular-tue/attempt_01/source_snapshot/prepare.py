"""Create private case inputs without touching frozen demand or supply."""
import copy,math,hashlib,json
from artifacts import ROOT,read,packed,save,sha
from physics import catalog

def stage_key(stages):
    return tuple(tuple(sorted((s['rid'],s['board'],s['alight'],s['next_walk'][0]) for s in st.get('pool',[st]))) for st in stages)

def prepare(case,config):
    amendment=read(ROOT/'capacity44_amendment.json') if (ROOT/'capacity44_amendment.json').exists() else None
    if (ROOT/'pair_amendment.json').exists():amendment=read(ROOT/'pair_amendment.json')
    bundle=read(ROOT/amendment['active_prepared'] if amendment else ROOT/'frozen/prepared.json.gz');day=case['day'];common=bundle['prepared']['common']
    bundle['supply']=read(ROOT/'frozen/supply.json');plans=bundle['prepared']['plans'][day]
    bundle['prepared']['plans']={day:plans}
    if config.get('cohort_release_lag_scale',1.)!=1.:
        meta=read(ROOT/'frozen/class_release_map.json.gz')
        assert meta['parent_prepared_sha256']==sha(ROOT/amendment['active_prepared'])
        alpha=config['cohort_release_lag_scale'];assert 0<alpha<=1.5
        for p in plans:
            event=meta['events'][(p[0]-1)//48]
            assert event['weekday']==day and event['building']==p[1]
            end=event['class_end_seconds'];lag=p[4]-end
            assert 60<=lag<=480
            p[4]=end+alpha*lag
    physical=config['physics']!='v9_frozen'
    heterogeneous=physical and config.get('restore_source_walking_variation',False)
    inherited_scales=dict(bundle['walk_scales'])
    if physical:
        spec={k:config[k] for k in ('walking_kmh','stairs_time_factor','slope_time_model')}
        spec['prepared']=amendment['prepared_sha256'] if amendment else read(ROOT/'input_manifest.json')['prepared_sha256']
        cache=ROOT/('physical_paths_'+hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()[:12]+'.json.gz')
        if cache.exists():paths=read(cache)
        else:
            paths=catalog(common['paths'],read(ROOT/'frozen/walking_osm.json'),config);packed(cache,paths)
        bundle['physical_paths']=paths
        def stages(rows):
            for stage in rows:
                stage['next_walk'][1]=paths[stage['next_walk'][0]]['seconds']
                if 'pool' in stage:stages(stage['pool'])
                if 'continuation_stages' in stage:stages(stage['continuation_stages'])
        for p in plans:
            p[5][1]=paths[p[5][0]]['seconds'];stages(p[6])
        for options in bundle['alternatives'].values():
            for option in options:
                option['walk'][1]=paths[option['walk'][0]]['seconds'];stages(option['stages'])
        for key in ('compatible_single_stage_pools','compatible_route_policies'):
            for rows in bundle.get(key,{}).values():stages(rows)
        if heterogeneous:
            from engine import scaled_stages
            # Nominal path-local4.8/stair/slope physics is retained. A person's
            # inherited relative factor scales every walking leg exactly once.
            for p in plans:
                factor=inherited_scales[str(p[0])]
                p[5][1]*=factor;p[6]=scaled_stages(p[6],factor)
            bundle['walk_scales']={str(p[0]):inherited_scales[str(p[0])] for p in plans}
        else:bundle['walk_scales']={str(p[0]):1. for p in plans}
    else:
        # Geometry still supplies lengths for costs and fare scenarios; times
        # and individual walking scales remain exactly as the source v9.
        from physics import distance
        bundle['physical_paths']=[{'meters':sum(distance(a,b) for a,b in zip(path,path[1:])),
            'seconds':None,'stairs_meters':0.,'unknown_slope_meters':None,'known_climb_meters':None} for path in common['paths']]
    original={str(p[0]):p[0] for p in plans};original_mass={str(p[0]):p[3] for p in plans}
    if config['behavior']!='v9_frozen':
        split=[];original={};scales={};dest={}
        for p in plans:
            n=max(1,math.ceil(p[3]/config['max_synthetic_packet_weight']));weights=[p[3]/n]*n
            weights[-1]=p[3]-sum(weights[:-1])
            for part,weight in enumerate(weights):
                q=copy.deepcopy(p);q[0]=p[0]*16+part;q[3]=weight
                original[str(q[0])]=p[0];scales[str(q[0])]=bundle['walk_scales'][str(p[0])]
                dest[str(q[0])]=bundle['destination_keys'][str(p[0])];split.append(q)
        plans=split;bundle['prepared']['plans'][day]=plans;bundle['walk_scales']=scales;bundle['destination_keys']=dest
    bundle['parent_ids']=original;bundle['source_parent_mass']=original_mass
    # All candidates begin at the exact same inherited origin coordinate.
    origin_catalog={}
    if config['origin_choice']:
        for p in plans:
            origin=tuple(common['paths'][p[5][0]][0]);key=repr((p[1],p[2],origin))
            sig=(p[5][0],stage_key(p[6]));target=origin_catalog.setdefault(key,{})
            if heterogeneous:
                from engine import scaled_stages
                factor=bundle['walk_scales'][str(p[0])]
                walk=[p[5][0],p[5][1]/factor];rows=scaled_stages(p[6],1/factor)
            else:walk=p[5];rows=p[6]
            target.setdefault(sig,{'walk':walk,'stages':rows,'key':repr(sig)})
        origin_catalog={k:list(v.values()) for k,v in origin_catalog.items()}
    bundle['origin_catalog']=origin_catalog
    if config.get('empirical_context'):
        from empirical_v12 import Evidence
        bundle['empirical_evidence']=Evidence(read(ROOT/'frozen/empirical_evidence.json'))
    bundle['prototype_config']=config
    if config.get('operations','baseline')!='baseline':
        bundle['operations']=read(ROOT/('frozen/operations_'+config['operations']+'.json'))
        common['city_operations']=bundle['operations'];common['city_speed_revision']=bundle['operations']['revision']
    return bundle
