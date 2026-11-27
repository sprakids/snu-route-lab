"""Restore known direct options in student choice; keep the global catalog intact."""
import copy

def signature(chain):
    if not chain:return ()
    return tuple(sorted(((e['rid'],e['board'],e['alight'],e['next_walk'][0],
        signature(e.get('continuation_stages',chain[1:]))) for e in chain[0].get('pool',[chain[0]])),key=repr))

def known_direct_registry(bundle,node_for):
    """Use only already-frozen single-stage services absent from the full catalog.

    Registry entries are separate complete policies. Do NOT append duplicate
    rid/board entries into a first-match vehicle boarding pool.
    """
    result={};evidence=[]
    for key,rows in bundle.get('compatible_single_stage_pools',{}).items():
        if not key.endswith('|snu'):continue
        known=set()
        for source in bundle.get('compatible_route_policies',{}).get(key,[]):
            for entry in source.get('pool',[source]):
                if not entry.get('continuation_stages'):
                    known.add((entry['rid'],entry['board'],entry['alight']))
        for source in rows:
            for entry in source.get('pool',[source]):
                if entry.get('continuation_stages'):continue
                triple=(entry['rid'],entry['board'],entry['alight'])
                if triple in known:continue
                assert node_for(entry)==int(key.split('|')[0])
                x=copy.deepcopy(entry);x.pop('pool',None);x['continuation_stages']=[]
                x['known_direct_policy_restored']=True
                result.setdefault(key,[]).append(x);known.add(triple)
                evidence.append({'key':key,'rid':entry['rid'],'board':entry['board'],'alight':entry['alight'],
                    'ride_path':entry['ride_path'],'wait_path':entry['wait_path'],'next_walk_path':entry['next_walk'][0],
                    'source':'frozen compatible_single_stage_pools'})
    report={'scope':'Known SNU direct policies only; initial choices and same-platform continuation reconsideration.',
        'restored_count':len(evidence),'restored_policies':evidence,'global_compatible_catalog_mutated':False,
        'new_geometry':False,'new_services':False,'demand_added':False,
        'enroute_continuation_selection':'unchanged'}
    return result,report

def append_origin_options(target,pid,node,bundle,signature_fn=signature):
    """Reuse the existing origin-to-platform walk, with a separate direct policy."""
    added=0
    for entry in bundle.get('restored_direct_policies',{}).get(f'{node}|snu',[]):
        chain=[copy.deepcopy(entry)];key=repr((pid,signature_fn(chain)))
        if key in target:continue
        target[key]={'walk':[pid,bundle['physical_paths'][pid]['seconds']],'stages':chain,'key':key}
        added+=1
    return added

def same_service_direct_policy(incumbent,direct):
    """Replace its alighting/continuation, retaining one entry per rid/board.

    If the service is new, add it once. The caller keeps existing FIFO ticket,
    wait/preparation/full-pass clocks and physical change count unchanged.
    """
    if not incumbent:return None
    pool=[];seen=set();matched=False
    key=(direct['rid'],direct['board'])
    for source in incumbent[0].get('pool',[incumbent[0]]):
        service=(source['rid'],source['board'])
        if service in seen:raise ValueError('Ambiguous incumbent service policy')
        seen.add(service)
        x=copy.deepcopy(direct if service==key else source);x.pop('pool',None)
        x.setdefault('continuation_stages',copy.deepcopy(incumbent[1:]));pool.append(x)
        matched|=service==key
    if not matched:
        x=copy.deepcopy(direct);x.pop('pool',None);x.setdefault('continuation_stages',[]);pool.append(x)
    chain=[{**pool[0],'pool':pool,'choice_pool_locked':True}]
    return None if signature(chain)==signature(incumbent) else chain
