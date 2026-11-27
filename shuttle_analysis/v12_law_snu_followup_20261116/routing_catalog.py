"""Recover known legal policies without inventing geometry, supply or demand."""
from collections import OrderedDict
from itertools import product
import copy

def service(entry):return (entry['rid'],entry['board'])

def signature(stages):
    if not stages:return ()
    stage=stages[0]
    return tuple(sorted((e['rid'],e['board'],e['alight'],e['next_walk'][0],
        signature(e.get('continuation_stages',stages[1:]))) for e in stage.get('pool',[stage])))

def entry_signature(entry):
    return (entry['rid'],entry['board'],entry['alight'],entry['next_walk'][0],
            signature(entry.get('continuation_stages',[])))

def direct_triples(chain):
    if not chain:return set()
    result=set()
    for e in chain[0].get('pool',[chain[0]]):
        if e.get('continuation_stages',chain[1:]):return set()
        result.add((e['rid'],e['board'],e['alight']))
    return result

def unique_first_service_policies(chain):
    """Separate continuation choices, never duplicate a service in a pool.

    The caller chooses one representative before its existing random stop
    choice. These variants never acquire separate independent stop tastes.
    """
    if not chain:return [[]]
    choices=OrderedDict()
    for source in chain[0].get('pool',[chain[0]]):
        e=copy.deepcopy(source);e.pop('pool',None)
        e.setdefault('continuation_stages',copy.deepcopy(chain[1:]))
        choices.setdefault(service(e),OrderedDict()).setdefault(entry_signature(e),e)
    result=[]
    for entries in product(*(list(group.values()) for group in choices.values())):
        pool=copy.deepcopy(list(entries))
        result.append([{**pool[0],'pool':pool,'choice_pool_locked':True}])
    return result

def same_platform_policies(incumbent,eligible_entries):
    """Keep one alighting/continuation plan for each offered service.

    Include a separate replacement policy for a different continuation of
    the SAME rid/board. Merely appending it would hide it behind stage_choice's
    first match. No queue ticket, clocks, weights or history are handled here.
    """
    base={}
    for e in incumbent[0].get('pool',[incumbent[0]]):
        key=service(e)
        if key in base:raise ValueError('Ambiguous incumbent boarding service')
        x=copy.deepcopy(e);x.pop('pool',None)
        x.setdefault('continuation_stages',copy.deepcopy(incumbent[1:]));base[key]=x
    candidates=[];seen={signature(incumbent)};new_services=OrderedDict()
    def emit(entries):
        pool=copy.deepcopy(list(entries.values()));chain=[{**pool[0],'pool':pool,'choice_pool_locked':True}]
        key=signature(chain)
        if key not in seen:seen.add(key);candidates.append(chain)
    for source in eligible_entries:
        x=copy.deepcopy(source);x.pop('pool',None);x.setdefault('continuation_stages',[])
        key=service(x)
        if key in base and entry_signature(base[key])==entry_signature(x):continue
        changed=dict(base);changed[key]=x;emit(changed)
        if key not in base:new_services.setdefault(key,OrderedDict()).setdefault(entry_signature(x),x)
    # Retain the old union-of-additional-services option. If an added service
    # has several continuations, each union variant has a unique first match.
    if len(new_services)>1:
        for entries in product(*(list(g.values()) for g in new_services.values())):
            changed=dict(base)
            for x in entries:changed[service(x)]=x
            emit(changed)
    return candidates

def restore_known_snu_direct_policies(bundle,node_for):
    """Reconcile full catalog with its already-frozen direct-service catalog.

    Only SNU direct services absent by (rid, board, alight) are restored.
    Alternative final-walk path IDs do not manufacture another service.
    The direct entry is copied verbatim and gets an explicit empty suffix.
    """
    full=bundle.setdefault('compatible_route_policies',{})
    direct=bundle.get('compatible_single_stage_pools',{})
    added=[];targets={}
    for key,entries in direct.items():
        if not key.endswith('|snu'):continue
        known=direct_triples([])
        for source in full.get(key,[]):known.update(direct_triples([source]))
        canonical=[]
        for source in entries:
            for e in source.get('pool',[source]):
                if e.get('continuation_stages'):continue
                triple=(e['rid'],e['board'],e['alight'])
                canonical.append(copy.deepcopy(e))
                if triple in known:continue
                node=int(key.split('|')[0]);assert node_for(e)==node
                row=copy.deepcopy(e);row.pop('pool',None);row['continuation_stages']=[]
                full.setdefault(key,[]).append(row);known.add(triple)
                added.append({'key':key,'rid':e['rid'],'board':e['board'],'alight':e['alight'],
                    'ride_path':e['ride_path'],'next_walk_path':e['next_walk'][0],
                    'source':'frozen compatible_single_stage_pools'})
        if any(x['key']==key for x in added):targets[key]=canonical
    # Reuse an existing approach walk only. If it already offers this direct
    # service, do not add another route differing merely by a final walk ID.
    walk_additions=[]
    for origin_key,options in bundle.get('alternatives',{}).items():
        if not origin_key.endswith('|snu'):continue
        access=OrderedDict()
        for o in options:
            if not o['stages']:continue
            node=node_for(o['stages'][0]);key=f'{node}|snu'
            if key in targets:access.setdefault((o['walk'][0],node),o)
        for (pid,node),source in access.items():
            entries=targets[f'{node}|snu']
            wanted={(e['rid'],e['board'],e['alight']) for e in entries}
            covered=any(o['walk'][0]==pid and wanted<=direct_triples(o['stages']) for o in options)
            if covered:continue
            pool=[];seen=set()
            for e in entries:
                triple=(e['rid'],e['board'],e['alight'])
                if triple in seen:continue
                seen.add(triple);x=copy.deepcopy(e);x.pop('pool',None);x['continuation_stages']=[];pool.append(x)
            option=copy.deepcopy(source)
            option['stages']=[{**pool[0],'pool':pool,'choice_pool_locked':True}]
            option['name']=source.get('name','도보 접근')+' · 기존 직통 정책 복원'
            options.append(option);walk_additions.append({'origin':origin_key,'walk_path':pid,'target_node':node})
    report={'scope':'SNU direct-policy consistency only; existing services/paths/supply/demand and numeric behavior coefficients unchanged.',
        'added_direct_policies':added,'added_direct_policy_count':len(added),'added_walk_options':walk_additions,
        'new_geometry':False,'new_services':False,'new_field_outcomes':False}
    bundle['catalog_repair_report']=report
    return report
