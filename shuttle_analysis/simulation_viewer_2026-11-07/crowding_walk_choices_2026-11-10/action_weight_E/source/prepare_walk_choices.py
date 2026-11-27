"""Add feasible walks to different city/shuttle services, using frozen v7 inputs."""
from pathlib import Path
from collections import defaultdict
import copy,gzip,json,hashlib,math
import capacity_model as base

ROOT=Path(__file__).resolve().parent
WORK=ROOT/'crowding_walk_choices_2026-11-10'/'action_weight_E'
SOURCE=ROOT/'gate_access_calibration_2026-11-09/candidates/alpha_075/prepared.json.gz'
RULE={'neighbor_walk_seconds':1250,'maximum_individual_transfer_walk_seconds':1800,
      'maximum_transfer_path_meters':1500,'diverse_route_targets':True,
      'neighbor_stops':6,'options_per_stop':2,'minimum_gain_seconds':120,
      'maximum_changes':None,'target_mean_changes':1.,'repeat_change_probability_multiplier':.30,
      'congestion_can_raise_change_probability':True,
      'same_line_downstream_consideration_probability':.08,
      'downstream_probability_applies_to_action_not_each_line':True,
      'previously_left_queue_reconsideration_probability':.05,
      'full_bus_stress_is_personally_experienced':True,
      'continuous_wait_review_limit_seconds':1200,
      'walking_willingness':{'plateau_meters':500,'weight_at_1000_meters':.30,'tail_decay_meters':150,
                             'meaning':'relative consideration weight, user scenario, not measured mode share'},
      'named_stop_queue_tolerance_range':[20.,35.],
      'review_threshold_is_forced_exit':False,
      'same_stop_policy_pool_freeflow_slack_seconds':300,
      'terminal_walk_reserved_for_final_change':False,
      'include_shuttle':True,'soft_queue_reference_people':40,
      'soft_reference_stop_ids':['120000167','120000168','120000196','120000197'],
      'reference_source':'user recollection, not counted observations',
      'do_not_clip_queue_or_delete_demand':True,'independent_empirical_validation':False}

def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def signature(stages):
    return tuple(tuple((s['rid'],s['board'],s['alight'],s['next_walk'][0]) for s in st.get('pool',[st])) for st in stages)

def prepare():
    WORK.mkdir(exist_ok=True)
    source_sha=base.sha(SOURCE);cache=WORK/'prepared.json.gz'
    provenance={'source_sha256':source_sha,'preparation_sha256':base.sha(Path(__file__)),
                'walking_graph_sha256':base.sha(ROOT/'model_snapshot/app/data/walking_osm.json'),'rule':RULE}
    if cache.exists():
        b=read(cache);assert b['walk_choice_provenance']==provenance,'Preserve old candidate before changing preparation rules'
        return b
    bundle=read(SOURCE);common=bundle['prepared']['common'];nodes=common['nodes'];ri=common['route_info']
    lookup={n['id']:i for i,n in enumerate(nodes)}
    def node_for(st):
        key=f"{st['rid']}|{st['board']}"
        return lookup[key] if st['rid'].startswith('shuttle') else bundle['city_node_lookup'][key]
    def cost(stages):
        return sum(min(ri[s['rid']]['offsets'][s['alight']]-ri[s['rid']]['offsets'][s['board']]+s['next_walk'][1]
                       for s in st.get('pool',[st])) for st in stages)
    catalog=defaultdict(dict)
    for key,options in bundle['alternatives'].items():
        dest=key.split('|',1)[1]
        for option in options:
            if not option['stages']:continue
            target=node_for(option['stages'][0]);sig=signature(option['stages'])
            row={**option,'freeflow_seconds':cost(option['stages'])}
            catalog[target,dest].setdefault(sig,row)
    engine=base.module('walk_choice_saved_engine',ROOT/'model_snapshot/engine/simulate_stop_inflow.py')
    graph=engine.WalkingGraph(base.read(ROOT/'model_snapshot/app/data/walking_osm.json'))
    points=[base.point(n) for n in nodes]
    walker=engine.MatrixWalker(graph,points);paths={};walks={};parent_trees={};added=defaultdict(int);geometry=[]
    def walking(a,b):
        key=(a,b)
        if key in walks:return walks[key]
        origin,target=points[a],points[b]
        if base.distance(origin,target)<.5:walks[key]=([origin],0.,0.);return walks[key]
        walk=walker.walk(origin,target)
        if not walk:walks[key]=None;return None
        na,_=walker.snaps[tuple(origin)];nb,_=walker.snaps[tuple(target)]
        if na not in parent_trees:parent_trees[na]=graph.tree(na)[1]
        parents=parent_trees[na];chain=[nb]
        while chain[-1]!=na:chain.append(parents[chain[-1]][0])
        pts=[origin]+[graph.nodes[k] for k in reversed(chain)]+[target]
        walks[key]=(pts,float(walk['seconds']),float(walk['meters']));return walks[key]
    gate=common['hot_nodes']['city_gate']
    for node,n in enumerate(nodes):
        # Walking distances come from the same connected pedestrian graph;
        # no straight-line shortcuts or synthetic crossing edges are added.
        neighbors=[]
        for target in range(len(nodes)):
            if target==node or base.distance(points[node],points[target])>1600:continue
            walk=walking(node,target)
            if walk and walk[1]<=RULE['neighbor_walk_seconds'] and walk[2]<=RULE['maximum_transfer_path_meters']:neighbors.append((walk[1],target))
        neighbors.sort()
        for dest in common['destinations']:
            key=f'{node}|{dest}';options=bundle['alternatives'][key]
            targets=[t for _,t in neighbors if catalog[t,dest]][:RULE['neighbor_stops']]
            covered={s['rid'] for t in targets for o in catalog[t,dest].values() for s in o['stages'][0].get('pool',[o['stages'][0]])}
            for _,target in neighbors:
                lines={s['rid'] for o in catalog[target,dest].values() for s in o['stages'][0].get('pool',[o['stages'][0]])}
                if lines-covered:targets.append(target);covered.update(lines)
            if dest=='snu' and gate!=node:
                w=walking(node,gate)
                if w and w[1]<=RULE['maximum_individual_transfer_walk_seconds'] and gate not in targets:targets.append(gate)
            existing={(node_for(o['stages'][0]),signature(o['stages'])) for o in options if o['stages']}
            for target in targets:
                rows=sorted(catalog[target,dest].values(),key=lambda o:(o['freeflow_seconds'],o['name']))
                picked=[];first_lines=set()
                pools=[o for o in rows if 'pool' in o['stages'][0]]
                if pools:picked.append(pools[0]);first_lines.update(s['rid'] for s in pools[0]['stages'][0]['pool'])
                for option in rows:
                    rid=option['stages'][0]['rid']
                    if rid in first_lines:continue
                    picked.append(option);first_lines.add(rid)
                    if len(picked)>=RULE['options_per_stop']:break
                for option in picked:
                    ident=(target,signature(option['stages']))
                    if ident in existing:continue
                    existing.add(ident);walk=walking(node,target)
                    if (node,target) not in paths:
                        paths[node,target]=len(common['paths']);common['paths'].append([[round(float(a),6),round(float(b),6)] for a,b in walk[0]])
                        geometry.append({'origin':node,'target':target,'seconds':walk[1],'meters':walk[2],
                                         'path':paths[node,target],'connector_max_m':max(walker.snaps[tuple(points[node])][1],walker.snaps[tuple(points[target])][1])})
                    options.append({'name':f"도보→{nodes[target]['name']} · {option['name']}",'kind':'walk_transfer',
                                    'walk':[paths[node,target],walk[1]],'stages':copy.deepcopy(option['stages']),
                                    'access_stop_node':target,'freeflow_seconds':option['freeflow_seconds'],
                                    'same_line_downstream_low_probability':True})
                    added[n['name']]+=1
        if node%20==0:print('WALK_CHOICES',node,len(nodes),flush=True)
    for options in bundle['alternatives'].values():
        for option in options:
            path=common['paths'][option['walk'][0]]
            option['walk_meters']=sum(base.distance(a,b) for a,b in zip(path,path[1:]))
    frozen=read(SOURCE)
    assert bundle['prepared']['plans']==frozen['prepared']['plans']
    assert common['route_info']==frozen['prepared']['common']['route_info']
    common['data_version']=9
    common['walk_choice_behavior']={**RULE,'source_simulation':'capacity_v7','not_observed_behavior':True}
    common['adaptive_settings']={**common['adaptive_settings'],'max_switches':None,
                                'repeat_change_probability_multiplier':.30,
                                'target_mean_changes':1.,'congestion_can_raise_change_probability':True,
                                'same_line_downstream_probability':.08,'continuous_wait_limit_seconds':1200}
    bundle['compatible_single_stage_pools']={}
    bundle['compatible_route_policies']={}
    for (node,dest),rows in catalog.items():
        policies={}
        for option in rows.values():
            for s in option['stages'][0].get('pool',[option['stages'][0]]):
                key=(s['rid'],s['board']);value=cost([s,*option['stages'][1:]])
                if key not in policies or value<policies[key][0]:
                    policies[key]=(value,{**copy.deepcopy(s),'continuation_stages':copy.deepcopy(option['stages'][1:]),
                                          'policy_freeflow_seconds':value})
        if policies:bundle['compatible_route_policies'][f'{node}|{dest}']=[v[1] for v in policies.values()]
        best={}
        for option in rows.values():
            if len(option['stages'])!=1:continue
            for s in option['stages'][0].get('pool',option['stages']):
                key=(s['rid'],s['board']);value=cost([s])
                if key not in best or value<best[key][0]:best[key]=(value,s)
        if best:bundle['compatible_single_stage_pools'][f'{node}|{dest}']=[copy.deepcopy(v[1]) for v in best.values()]
    common['city_route_stops']=base.read(ROOT/'public/data/capacity_v7/common.json')['city_route_stops']
    bundle['walk_choice_provenance']=provenance
    base.packed(cache,bundle)
    base.save(WORK/'walking_geometry.json',geometry)
    base.save(WORK/'preparation_verification.json',{'status':'PASS','new_access_paths':len(paths),'new_alternatives':sum(added.values()),
              'alternatives_by_origin_name':dict(added),'same_demand_and_initial_plans':True,'same_supply_speeds_capacities':True,
              'walking_graph_components':walker.component_profile,'maximum_connector_m':max(g['connector_max_m'] for g in geometry),
              'provenance':provenance})
    return bundle

if __name__=='__main__':prepare()
