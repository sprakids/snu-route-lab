"""Make seat-feasibility and fallback crowding share the same FIFO projection."""
def replace(path,old,new,count=1):
    text=path.read_text(encoding='utf8');assert text.count(old)==count,(path,old[:80],text.count(old))
    path.write_text(text.replace(old,new),encoding='utf8')
def apply(work,known_only=False):
    replace(work/'engine.py','def indexed_boardable(rows,vehicles,ready,now,stage,weight,view,indivisible=False):','''def boarding_projection(when,vid,k,choice,vehicle,available_after_ahead,request,project_load):
    result=(when,vid,k,choice)
    if not project_load:return result
    cap=vehicle['cap'];free=max(0.,available_after_ahead)
    detail={'capacity':cap,'free_after_known_ahead':free,'requested_marginal_mass':request,
        'projected_after_self':min(cap,max(0.,cap-free+request)),
        'basis':'same_conditional_FIFO_seat_forecast_including_past_residual_proxy',
        'is_observed_occupancy':False}
    return (*result,detail)


def indexed_boardable(rows,vehicles,ready,now,stage,weight,view,indivisible=False,project_load=False):''')
    replace(work/'engine.py','def first_boardable(rows,vehicles,ready,now,stage,weight,waiting,indivisible=False):','def first_boardable(rows,vehicles,ready,now,stage,weight,waiting,indivisible=False,project_load=False):')
    replace(work/'engine.py','return indexed_boardable(rows,vehicles,ready,now,stage,weight,waiting,indivisible)','return indexed_boardable(rows,vehicles,ready,now,stage,weight,waiting,indivisible,project_load)')
    replace(work/'engine.py','if need<=available+EPS:return when,vid,k,choice','if need<=available+EPS:return boarding_projection(when,vid,k,choice,vehicle,available,need,project_load)',2)
    replace(work/'preferences.py','    empirical_context:tuple=()','    empirical_context:tuple=()\n    boarding_load_projections:tuple=()')
    replace(work/'policy.py','            contexts=[]','            contexts=[];load_projections=[]')
    replace(work/'policy.py',"                stage=chain[0];node=node_for(stage)","                stage=chain[0];node=node_for(stage);projection=None")
    replace(work/'policy.py',"                    when,vehicle,k,chosen=override;ready=when;prep=0.;choice=(when,vehicle['id'],k,chosen)","""                    when,vehicle,k,chosen=override;ready=when;prep=0.;choice=(when,vehicle['id'],k,chosen)
                    if config.get('project_queue_load_for_crowding'):
                        occupied_now=sum(s['w'] for target,s in vehicle['onboard'] if target>k)
                        request=max(1.,state['w']) if config.get('forecast_person_requires_whole_seat') else state['w']
                        projection={'capacity':vehicle['cap'],'free_after_known_ahead':max(0.,vehicle['cap']-occupied_now),
                            'requested_marginal_mass':request,'projected_after_self':min(vehicle['cap'],occupied_now+request),
                            'basis':'actual_current_simulated_onboard_at_boarding_opportunity','is_observed_occupancy':False}
""")
    replace(work/'policy.py','choice=first_boardable(rows,vehicles,ready,now,stage,request,view,indivisible=whole)','choice=first_boardable(rows,vehicles,ready,now,stage,request,view,indivisible=whole,project_load=config.get(\'project_queue_load_for_crowding\',False))')
    replace(work/'policy.py',"                when,vid,k,chosen=choice;vehicle=vehicles[vid];info=ri[vehicle['rid']]", "                when,vid,k,chosen=choice[:4];vehicle=vehicles[vid];info=ri[vehicle['rid']]\n                if len(choice)>4:projection=choice[4]")
    replace(work/'policy.py',"                fraction=min(1.,(occupied+state['w'])/vehicle['cap'])", """                fraction=min(1.,(occupied+state['w'])/vehicle['cap'])
                if projection is not None:fraction=min(1.,projection['projected_after_self']/vehicle['cap'])""")
    replace(work/'policy.py',"                if context is not None:contexts.append(context)","""                if context is not None:contexts.append(context)
                if projection is not None:
                    load_projections.append({**projection,'route':vehicle['rid'],'vehicle':vid,'board_index':k,
                        'time':when,'used_for_fallback_crowding_cost':exposure is None,
                        'trajectory_scope':'boarding-entry-load proxy held over inherited ride; no numeric grade conversion'})""")
    replace(work/'policy.py','wait_squared,wait_cubed,tuple(contexts))','wait_squared,wait_cubed,tuple(contexts),tuple(load_projections))')
    replace(work/'policy.py',"'joint_board_wait_walk_choice':bool(config.get('joint_board_wait_walk_choice')),", "'joint_board_wait_walk_choice':bool(config.get('joint_board_wait_walk_choice')),'project_queue_load_for_crowding':bool(config.get('project_queue_load_for_crowding')),")
    if known_only:
        replace(work/'engine.py','def boarding_projection(when,vid,k,choice,vehicle,available_after_ahead,request,project_load):','def boarding_projection(when,vid,k,choice,vehicle,available_after_ahead,request,project_load,free_before_ahead=None):')
        replace(work/'engine.py',"    cap=vehicle['cap'];free=max(0.,available_after_ahead)\n    detail={'capacity':cap,'free_after_known_ahead':free,'requested_marginal_mass':request,\n        'projected_after_self':min(cap,max(0.,cap-free+request)),\n        'basis':'same_conditional_FIFO_seat_forecast_including_past_residual_proxy',\n        'is_observed_occupancy':False}","""    cap=vehicle['cap'];free=max(0.,available_after_ahead)
    retained=sum(s['w'] for target,s in vehicle['onboard'] if target>k)
    before=cap-retained if free_before_ahead is None else free_before_ahead
    ahead=max(0.,before-free);reserved=max(0.,cap-retained-before)
    known=retained+ahead+request;upper=known+reserved
    assert known<=cap+2*EPS and upper<=cap+2*EPS,(known,upper,cap,'FIFO load projection exceeds capacity')
    detail={'capacity':cap,'known_retained_onboard':retained,'known_ahead_boarded_here':ahead,
        'unidentified_reserved_capacity':reserved,'free_before_known_ahead':before,
        'free_after_known_ahead':free,'requested_marginal_mass':request,
        'projected_after_self':min(cap,max(0.,known)),
        'quota_implied_load_upper_proxy':min(cap,max(0.,upper)),
        'basis':'known_retained_plus_this_vehicle_FIFO_boardings_plus_marginal_person; reservation excluded from crowd cost',
        'is_observed_occupancy':False}""")
        replace(work/'engine.py',"        if available<=EPS:continue\n", "        if available<=EPS:continue\n        free_before_ahead=available\n",2)
        replace(work/'engine.py','boarding_projection(when,vid,k,choice,vehicle,available,need,project_load)','boarding_projection(when,vid,k,choice,vehicle,available,need,project_load,free_before_ahead)',2)
