"""Causal sequential decisions on top of shared physical vehicle/FIFO states."""
from collections import Counter
import math
from preferences import Prediction,traits,cost,choose,uniform,walking_weight
from hazard import ReviewClock
from fares import FareLedger,board,alight
from artifacts import EPS,END

def signature(stages):
    return tuple(tuple(sorted((s['rid'],s['board'],s['alight'],s['next_walk'][0]) for s in st.get('pool',[st]))) for st in stages)

def attach_policy(bundle,config,node_for,current_stage,legacy_forecast,waiting_before,schedule,vehicles,
                  queues,qmass,premass,queue_versions,ri,walk_next,record_wait,push,decisions,behavior_decisions):
    from engine import first_boardable,scaled_stages,stage_choice
    paths=bundle['physical_paths'];nodes=bundle['prepared']['common']['nodes'];routes=bundle['prepared']['routes']

    class Policy:
        def __init__(self):
            self.counts=Counter();self.boarding_choices=[];self.initial_choices=0
        def make_traits(self,uid):return traits(uid,config)
        def empty_ledger(self):return FareLedger()
        def base_fare(self,rid):
            if rid.startswith('shuttle'):return 0
            name=routes[rid]['name']
            return 1200 if name.startswith(('관악','동작','서초','금천')) else 1500
        def alighted(self,state,rid,at):
            state['fare_ledger']=alight(state['fare_ledger'],rid,at,self.base_fare(rid))
        def boarded(self,state,rid,chosen,at,end):
            charge,state['fare_ledger']=board(state['fare_ledger'],rid,at,self.base_fare(rid),paths[chosen['ride_path']]['meters'])
            state['fare_paid']=state.get('fare_paid',0.)+charge;state['rides_taken']=state.get('rides_taken',0)+1
        def predict(self,stages,now,state,access=0.,factor=1.,keep=False,override=None,access_path=None):
            cursor=now+access;walk=access;wait=ride=prep=fee=crowd=fatigue=0.;chain=list(stages);count=0
            ledger=state['fare_ledger']
            if access_path is not None:fatigue+=paths[access_path]['stairs_meters']/(config['walking_kmh']/3.6)
            while chain:
                stage=chain[0];node=node_for(stage)
                ready=max(cursor,state['ready_time']) if keep and count==0 else cursor+config['preparation_seconds']
                prep+=ready-cursor
                if count==0 and override is not None:
                    when,vehicle,k,chosen=override;ready=when;prep=0.;choice=(when,vehicle['id'],k,chosen)
                else:
                    view=waiting_before(node,state,keep and count==0)
                    choice=first_boardable(schedule[node],vehicles,ready,now,stage,state['w'],view)
                if choice is None:return None
                when,vid,k,chosen=choice;vehicle=vehicles[vid];info=ri[vehicle['rid']]
                target=k+chosen['alight']-chosen['board'];duration=info['offsets'][target]-info['offsets'][k]
                if when<ready-EPS:return None
                wait+=max(0.,when-ready);ride+=duration;cursor=when+duration
                occupied=sum(s['w'] for dest,s in vehicle['onboard'] if dest>k)
                fraction=min(1.,(occupied+state['w'])/vehicle['cap']);crowd+=duration*fraction*fraction
                charge,ledger=board(ledger,vehicle['rid'],when,self.base_fare(vehicle['rid']),paths[chosen['ride_path']]['meters'])
                fee+=charge;ledger=alight(ledger,vehicle['rid'],cursor,self.base_fare(vehicle['rid']))
                last_walk=chosen['next_walk'][1]*factor;walk+=last_walk;cursor+=last_walk
                fatigue+=paths[chosen['next_walk'][0]]['stairs_meters']/(config['walking_kmh']/3.6)
                chain=chosen['continuation_stages'] if 'continuation_stages' in chosen else chain[1:];count+=1
                assert count<=8,'Cyclic candidate chain, unrelated to the unlimited rerouting count'
            assert abs((cursor-now)-(walk+wait+ride+prep))<1e-5
            transfers=max(0,count-1+(1 if state.get('rides_taken',0)>0 and count else 0))
            return Prediction(cursor,walk,wait,ride,prep,transfers,fee,crowd,fatigue)
        def generalized(self,pred,state,changing=False):
            return cost(pred,state['traits'],len(state['history']),changing,config['fare_in_choice'])
        def reschedule(self,state,at):
            if not state['queued'] or state['done']:return
            clock=state.get('hazard_clock')
            if clock is None or clock.stop_entry!=state['stop_entry']:
                clock=ReviewClock.start(at,state['stop_entry'],len(state['history']),state['full_passes'],state['plan'][0],state['traits'].response,config,state['review_ordinal'])
                state['hazard_clock']=clock
            else:clock.update(at,len(state['history']),state['full_passes'],config)
            due=clock.due(config);state['check_version']+=1
            if due<=END:push(max(at+1e-6,due),2,'recheck',(state,state['check_version']))
        def maybe_switch(self,state,at,reason,forced=False):
            assert not forced,'Prototype has no forced-abandonment mechanism'
            count=len(state['history']);identity=state['plan'][0];node=state['node']
            if reason=='arrival':
                p=config['arrival_review_probability']*config['repeat_multiplier']**count
                if uniform(config['seed'],identity,'arrival-review',state['visit'])>=p:return False
            else:state['hazard_clock']=None
            state['review_ordinal']+=1;self.counts[reason]+=1
            current=self.predict(state['stages'][state['stage']:],at,state,keep=True)
            candidates=[]
            if current is not None:
                candidates.append({'key':'stay','cost':self.generalized(current,state),'prediction':current,'option':None})
            stage=current_stage(state);old_lines={s['rid']:s['board'] for s in stage.get('pool',[stage])}
            for option in bundle['alternatives'].get(f"{node}|{state['dest']}",[]):
                chain=option['stages'];factor=state['factor'];access=option['walk'][1]*factor
                first=node_for(chain[0]) if chain else None
                if chain and first==node:continue
                if access<=EPS:continue  # Same physical place belongs to one compatible boarding policy.
                prior=walking_weight(option.get('walk_meters',paths[option['walk'][0]]['meters']))
                # Stress relaxes distance aversion, while downstream/revisit
                # actions keep their separate low consideration multipliers.
                relief=math.exp(-.35*state['full_passes']-max(0.,at-state['stop_entry'])/1800)
                prior=1-(1-prior)*relief if prior>0 else 0.
                if chain:
                    services=chain[0].get('pool',[chain[0]])
                    # One action prior for walking downstream, never one draw per line.
                    if all(s['rid'] in old_lines and s['board']>old_lines[s['rid']] for s in services):prior*=config['same_line_downstream_prior']
                    if first in state['visited']:prior*=config['revisit_prior']
                # Bound the minimum possible preference cost before forecasting.
                lower=state['traits'].walk*access/60+state['traits'].change*(1+.5*count)
                best_so_far=min((c['cost'] for c in candidates),default=math.inf)
                if lower>best_so_far+12*config['choice_temperature_minutes']:
                    self.counts['far_cost_pruned']+=1;continue
                pred=self.predict(chain,at,state,access,factor,False,access_path=option['walk'][0])
                if pred is None:continue
                key=repr((first,option['walk'][0],signature(chain)))
                candidates.append({'key':key,'cost':self.generalized(pred,state,True),'prediction':pred,'option':option,'prior':prior})
            # If a compatible superset at the same physical target exists, a
            # one-stage subset with the same access geometry adds no new strategy.
            supersets={}
            for c in candidates:
                op=c['option']
                if op and len(op['stages'])==1:
                    key=op['walk'][0];services=frozenset(signature(op['stages'])[0]);supersets.setdefault(key,[]).append((c,services))
            redundant=set()
            for group in supersets.values():
                for c,s in group:
                    if any(s<other for d,other in group):redundant.add(c['key'])
            candidates=[c for c in candidates if c['key'] not in redundant]
            selected=choose(candidates,identity,('reroute',state['visit'],state['review_ordinal']),config)
            if selected is None or selected['option'] is None:return False
            option=selected['option'];pred=selected['prediction'];first=node_for(option['stages'][0]) if option['stages'] else None
            visible=qmass[node]+premass[node]
            if state['queued']:
                queues[node].remove(state);qmass[node]-=state['w'];state['queued']=False;queue_versions[node]+=1
            if state.get('preparing'):premass[node]-=state['w'];state['preparing']=False
            record_wait(state,at,'switched')
            name=option.get('name',option['kind']);old_eta=current.eta if current else None
            decisions.append([at,node,state['w'],identity,stage['rid'],option['kind'],name,old_eta,pred.eta,reason])
            behavior_decisions.append({'time':at,'origin':node,'target':first,'uid':identity,'weight':state['w'],'kind':option['kind'],
                'forced':False,'reason':reason,'visible_queue':visible,'continuous_wait_seconds':at-state['stop_entry'],
                'full_passes':state['full_passes'],'change_count_before':count,'old_eta':old_eta,'new_eta':pred.eta,
                'generalized_cost_minutes':selected['cost'],'physical_prediction':pred.components(),
                'old_services':state['entry_eligibility'],
                'new_services':[(s['rid'],s['board']) for s in option['stages'][0].get('pool',[option['stages'][0]])] if option['stages'] else []})
            state['history']=state['history']+[[at,option['kind'],name]];state['last_switch']=at
            state['visited']=state['visited']|{node};state['check_version']+=1;state['hazard_clock']=None
            state['stages']=scaled_stages(option['stages'],state['factor']);state['stage']=0
            walk_next(state,at,option['walk'][0],option['walk'][1]*state['factor'],config['preparation_seconds'])
            return True
        def initial_choice(self,state,at):
            plan=state['plan'];origin=tuple(bundle['prepared']['common']['paths'][plan[5][0]][0])
            options=bundle['origin_catalog'].get(repr((plan[1],plan[2],origin)),[]);candidates=[]
            for option in options:
                pred=self.predict(option['stages'],at,state,option['walk'][1],1.,access_path=option['walk'][0])
                if pred is None:continue
                prior=walking_weight(paths[option['walk'][0]]['meters'])
                candidates.append({'key':option['key'],'cost':self.generalized(pred,state),'option':option,'prediction':pred,'prior':prior})
            selected=choose(candidates,plan[0],('departure',),config)
            if selected:
                op=selected['option'];self.initial_choices+=int((plan[5][0],signature(plan[6]))!=(op['walk'][0],signature(op['stages'])))
                # Departure, origin, destination and mass stay fixed. Initial
                # choice is distinct from a later walking reroute count.
                state['plan']=[*plan[:5],list(op['walk']),op['stages']];state['stages']=op['stages']
        def accept_boarding(self,state,chosen,vehicle,k,at,available):
            if 'pool' not in current_stage(state):return True
            chain=[chosen,*state['stages'][state['stage']+1:]]
            if 'continuation_stages' in chosen:chain=[chosen,*chosen['continuation_stages']]
            ride=self.predict(chain,at,state,keep=True,override=(at,vehicle,k,chosen))
            future=self.predict(state['stages'][state['stage']:],at+1e-5,state,keep=True)
            if ride is None or future is None:return True
            options=[{'key':'board','cost':self.generalized(ride,state)}, {'key':'wait','cost':self.generalized(future,state)}]
            selected=choose(options,state['plan'][0],('board',state['visit'],vehicle['id'],k),config)
            accept=selected['key']=='board'
            if not accept:
                self.boarding_choices.append({'time':at,'uid':state['plan'][0],'ticket':state['queue_ticket'],
                    'node':state['node'],'vehicle':vehicle['id'],'route':vehicle['rid'],'stop_index':k,'weight':state['w'],
                    'seats_available':available,'action':'voluntary_continue_waiting','board_cost':options[0]['cost'],'wait_cost':options[1]['cost']})
            return accept
        def report(self):
            return {'opportunity_counts':dict(self.counts),'voluntary_boarding_declines':len(self.boarding_choices),
                    'initial_plan_changes':self.initial_choices,'generalized_cost_unit':'minute_equivalent_not_eta',
                    'max_route_changes':None,'forced_abandonment':False,'polling_controls_behavior':False,
                    'alighting_scope':'inherited candidate alighting targets; new choices after alighting. Endogenous early alighting not implemented.',
                    'fare_scenario':config['fare_scenario'],'fare_used_in_choice':config['fare_in_choice']}
    return Policy()
