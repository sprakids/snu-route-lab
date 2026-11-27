"""Recognize a downstream attempt to board the same already-offered main line.

This is topology/choice consideration only. It never reads future queue sizes,
waiting durations, vehicle capacity, demand counts or observed queue targets.
"""

def selected_primary(stages,timeline,destination,config,node_for):
    chain=list(stages);primary=None
    if not timeline:return None
    first_node=node_for(chain[0]) if chain else None
    for index,row in enumerate(timeline):
        if not chain:return None
        rid=row.get('route');board=row.get('board_index')
        entry=next((e for e in chain[0].get('pool',[chain[0]]) if e['rid']==rid and e['board']==board),None)
        if entry is None:return None
        main=(destination not in ('snu','daehak') or not rid.startswith('shuttle')
              or rid in config.get('commuter_shuttle_route_ids',('shuttle-41841','shuttle-daehak')))
        if main:primary={'rid':rid,'board':board,'alight':entry['alight'],'node':node_for(entry),'position':index,'first_node':first_node}
        chain=entry.get('continuation_stages',chain[1:])
    return primary if not chain else None

def same_main_downstream_access(stages,prediction,destination,config,node_for,bundle,reference_node=None):
    """True only when access precedes a later boarding of an offered main bus.

    Exact rid and final alight index match and the upstream board index must
    precede the new main boarding index. This preserves route direction and
    distinguishes an actually different homebound service. Direct first-leg
    boarding is left to the existing walking-downstream rule.
    """
    primary=selected_primary(stages,prediction.boarding_timeline,destination,config,node_for)
    if primary is None or primary['position']==0:return False
    refs={primary['first_node']}
    if reference_node is not None:refs.add(reference_node)
    for node in refs:
        for source in bundle.get('compatible_single_stage_pools',{}).get(f'{node}|{destination}',[]):
            for e in source.get('pool',[source]):
                if e.get('continuation_stages'):continue
                if (e['rid']==primary['rid'] and e['alight']==primary['alight']
                    and e['board']<primary['board'] and node_for(e)==node):return True
    return False
