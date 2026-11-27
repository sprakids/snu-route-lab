"""Refactor pure alternative generation and apply joint board/wait/walk actions."""
from pathlib import Path
def replace(path,old,new):
    text=path.read_text(encoding='utf8');assert text.count(old)==1,(path,old[:70],text.count(old))
    path.write_text(text.replace(old,new),encoding='utf8')
def apply(work):
    path=work/'policy.py';text=path.read_text(encoding='utf8')
    start=text.index('        def maybe_switch(');end=text.index('        def initial_choice(',start)
    old=text[start:end]
    head_end=old.index('            candidates=[]')
    collection_end=old.index('            selected=choose(')
    commit_start=old.index("            if selected is None or selected['option'] is None:return False")
    collection=old[head_end:collection_end]
    selector=old[collection_end:commit_start]
    # Same pure action set for a normal reconsideration and an available vehicle.
    collection_method='''        def alternative_choices(self,state,at,current):
            count=len(state['history']);identity=state['plan'][0];node=state['node']
'''+collection+'''            return candidates
'''
    reconsider=old[:head_end]+'''            candidates=self.alternative_choices(state,at,current)
'''+selector+'''            return self.commit_switch(state,at,reason,selected,current)
'''
    commit='''        def commit_switch(self,state,at,reason,selected,current=None):
            count=len(state['history']);identity=state['plan'][0];node=state['node'];stage=current_stage(state)
'''+old[commit_start:]
    text=text[:start]+collection_method+reconsider+commit+text[end:]
    text=text.replace('        def accept_boarding(self,state,chosen,vehicle,k,at,available):','        def legacy_accept_boarding(self,state,chosen,vehicle,k,at,available):')
    insert=text.index('        def legacy_accept_boarding(')
    new='''        def accept_boarding(self,state,chosen,vehicle,k,at,available):
            if not config.get('joint_board_wait_walk_choice'):
                return self.legacy_accept_boarding(state,chosen,vehicle,k,at,available)
            state.pop('pending_boarding_walk',None)
            chain=[chosen,*state['stages'][state['stage']+1:]]
            if 'continuation_stages' in chosen:chain=[chosen,*chosen['continuation_stages']]
            ride=self.predict(chain,at,state,keep=True,override=(at,vehicle,k,chosen))
            future=self.predict(state['stages'][state['stage']:],at,state,keep=True,exclude_vehicle=vehicle['id'])
            options=self.alternative_choices(state,at,future)
            for option in options:
                if option['option'] is None:option['key']='wait'
            if ride is not None:
                options.append({'key':'board','cost':self.generalized(ride,state),'option':None,'prediction':ride,
                    'taste_key':strategy_taste_key(chain,state.get('dest'))})
            selected=choose(options,state['plan'][0],('board',state['visit'],vehicle['id'],k),config)
            # No forecastable suffix: preserve physically feasible boarding rather than delete demand.
            if selected is None or selected['key']=='board':return True
            walking=selected['option'] is not None
            if walking:state['pending_boarding_walk']=(selected,future)
            self.boarding_choices.append({'time':at,'uid':state['plan'][0],'ticket':state['queue_ticket'],
                'node':state['node'],'vehicle':vehicle['id'],'route':vehicle['rid'],'stop_index':k,'weight':state['w'],
                'seats_available':available,'action':'voluntary_walk_instead' if walking else 'voluntary_continue_waiting',
                'board_cost':self.generalized(ride,state) if ride else None,
                'wait_cost':self.generalized(future,state) if future else None,
                'selected_cost':selected['cost'],'joint_action_count':len(options),'selected_key':selected['key']})
            self.counts['joint_boarding_walk' if walking else 'joint_boarding_wait']+=1
            return False
        def apply_boarding_walk(self,state,at):
            pending=state.pop('pending_boarding_walk',None)
            if pending is None:return False
            selected,current=pending
            return self.commit_switch(state,at,'boarding_joint_choice',selected,current)
'''
    path.write_text(text[:insert]+new+text[insert:],encoding='utf8')
    # A walk removes queue mass during a boarding event. Refresh the sparse index
    # after that version change; ordinary boarding retains live-prefix updates.
    replace(work/'engine.py',"            live=waiting_before(node).cache\n            for row in live['types']:\n                if 'live_mass' not in row:row['live_mass']=LiveMass([b-a for a,b in zip(row['prefix'],row['prefix'][1:])])\n            # Incompatible", "            # Incompatible")
    replace(work/'engine.py',"                if chosen is None or available<=EPS:continue\n                if config['boarding_choice']", "                if chosen is None or available<=EPS:continue\n                live=waiting_before(node).cache\n                for row in live['types']:\n                    if 'live_mass' not in row:row['live_mass']=LiveMass([b-a for a,b in zip(row['prefix'],row['prefix'][1:])])\n                if config['boarding_choice']")
    replace(work/'engine.py',"                    voluntary.add(state['sid'])\n                    if state.get('service_review_pending_clock')!=t:", "                    voluntary.add(state['sid'])\n                    if policy.apply_boarding_walk(state,t):continue\n                    if state.get('service_review_pending_clock')!=t:")
    replace(work/'analyze_followup.py',"assert r['action']=='voluntary_continue_waiting' and r['seats_available']>0", "assert r['action'] in ('voluntary_continue_waiting','voluntary_walk_instead') and r['seats_available']>0")
    replace(work/'policy.py',"'polling_controls_behavior':False,", "'polling_controls_behavior':False,'joint_board_wait_walk_choice':bool(config.get('joint_board_wait_walk_choice')),\n                    'forecast_continuation_limitation':'Future pooled service remains first-boardable approximation; joint action set fixed at the actual boarding opportunity only.',")
