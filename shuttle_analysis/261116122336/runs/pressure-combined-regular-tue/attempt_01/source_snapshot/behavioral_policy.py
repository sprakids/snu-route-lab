"""User-specified mode commitment; all thresholds are declared scenarios, not fits."""
from collections import Counter
import bisect,copy,math
from preferences import choose,lognormal,walking_weight
from artifacts import EPS,END

def mode_of(stages):
    return 'walk' if not stages else 'shuttle' if stages[0]['rid'].startswith('shuttle') else 'city'

def main_mode_after(rid,previous,config):
    if rid in config.get('commuter_shuttle_route_ids',('shuttle-41841','shuttle-daehak')):return 'shuttle'
    return previous if rid.startswith('shuttle') else 'city'

def trunk_modes(stages,config,previous=None):
    """Every member's own continuation; internal access is not a commute shuttle."""
    if not stages:return {previous or 'access_only'}
    stage=stages[0];result=set()
    for entry in stage.get('pool',[stage]):
        after=main_mode_after(entry['rid'],previous,config)
        result.update(trunk_modes(entry.get('continuation_stages',stages[1:]),config,after))
    return result

def split_primary_stops(stages,dest,config,node_for,last_primary=None,last_node=None):
    """Split complete policy branches by their intended primary boarding stop."""
    if not stages:return {last_primary if last_primary is not None else last_node:[]}
    stage=stages[0];grouped={}
    for source in stage.get('pool',[stage]):
        node=node_for(source);rid=source['rid']
        main=dest not in ('snu','daehak') or not rid.startswith('shuttle') or rid in config.get('commuter_shuttle_route_ids',('shuttle-41841','shuttle-daehak'))
        target=node if main else last_primary
        branches=split_primary_stops(source.get('continuation_stages',stages[1:]),dest,config,node_for,target,node)
        for primary,tail in branches.items():
            entry={k:copy.deepcopy(v) for k,v in source.items() if k not in ('pool','continuation_stages')}
            entry['continuation_stages']=tail;grouped.setdefault(primary,[]).append(entry)
    return {primary:[{**entries[0],'pool':entries}] for primary,entries in grouped.items()}

def primary_access_extension(pred,primary_node):
    """Access time after first boarding; future transfer waiting is not anticipated."""
    timeline=pred.boarding_timeline
    indices=[i for i,r in enumerate(timeline) if r['node']==primary_node]
    if not indices:return 0.
    target=indices[-1]
    if target==0:return 0.
    future_wait=math.fsum(r['time']-r['arrival'] for r in timeline[1:target])
    return max(0.,timeline[target]['arrival']-timeline[0]['time']-future_wait)

def personal_patience(identity,mode,config):
    median=config['shuttle_patience_median_seconds'] if mode=='shuttle' else config['city_patience_median_seconds']
    return lognormal(config['seed'],identity,'student-patience',median,config['patience_log_sigma'])

def terminal_allowed(dest,meters,config):
    return dest!='snu' or meters<=config['far_terminal_walk_max_meters']

def terminal_direction_allowed(dest,service,config,routes):
    allowed=config.get('terminal_direction_requirements',{}).get(dest,{}).get(service['rid'])
    if allowed is None:return True
    stops=routes.get(service['rid'],{}).get('stops',[])
    board=service['board']
    return 0<=board<len(stops) and stops[board].get('direction') in allowed

def boarding_score(pred,access):return access+pred.first_wait

def residual_wait_seconds(times,ready):
    """Uniform unknown phase: triangular waiting areas, not a personal wait."""
    hour=math.floor(ready/3600)*3600
    gaps=[b-a for a,b in zip(times,times[1:]) if b>a and hour<=(a+b)/2<hour+3600]
    if not gaps:return None
    return math.fsum(h*h for h in gaps)/(2*math.fsum(gaps))

def expected_boarding_score(pred,access,preparation,phase_wait,empty_reference):
    # Keep current causal FIFO/capacity delay; replace only the unobserved
    # second-exact empty-queue departure phase by a headway expectation.
    queue_delay=max(0.,pred.first_wait-preparation-phase_wait)
    return access+preparation+empty_reference+queue_delay

def complete_signature(stages):
    if not stages:return ()
    stage=stages[0];entries=[]
    for e in stage.get('pool',[stage]):
        entries.append((e['rid'],e['board'],e['alight'],e['next_walk'][0],complete_signature(e.get('continuation_stages',stages[1:]))))
    return tuple(sorted(entries,key=repr))

def remove_redundant(candidates):
    # With compulsory first-compatible boarding, a larger service set may
    # force a slow earlier bus. Only identical strategies are duplicates.
    unique={}
    for c in candidates:
        o=c.get('option')
        key=('stay',c['key']) if o is None else (o['walk'][0],complete_signature(o['stages']))
        if key not in unique or c['cost']<unique[key]['cost']:unique[key]=c
    return list(unique.values())

def frustration(age,patience,denied,more,mode,config):
    return age>=patience or (mode=='city' and denied>=config['city_denial_trigger'] and more>=config['city_additional_pass_trigger'])

def configure(policy,bundle,config,node_for,current_stage,schedule,vehicles,queues,qmass,premass,push,decision_log):
    if not config.get('student_strategy'):return policy
    from engine import scaled_stages,stage_choice
    from policy import signature,strategy_taste_key
    paths=bundle['physical_paths'];common=bundle['prepared']['common'];stats=Counter();initial=Counter();draws=[];cache={}
    arrival_cache={};frequency_cache={};initial_stops=Counter();initial_samples=[];same_stop_updates=[];trunk_checks=Counter();primary_cache={};primary_stops=Counter()
    raw_maybe=policy.maybe_switch;raw_reschedule=policy.reschedule;raw_complete=policy.complete_same_stop
    raw_boarded=policy.boarded;raw_commit=policy.commit_switch;raw_report=policy.report

    def initialize(state):
        if 'student_preferred_mode' in state:return
        mode=mode_of(state['stages']);dest=state['dest']
        if mode=='walk' and dest=='snu' and not terminal_allowed(dest,paths[state['plan'][5][0]]['meters'],config):mode='city'
        state.update(student_preferred_mode=mode,student_committed_mode=mode,student_flexible=False,
          student_patience_seconds=personal_patience(state['plan'][0],mode,config),student_stop_history=[])
        intended=trunk_modes(state['stages'],config)
        if mode=='city' and not state['stages']:intended={'city'}
        state.update(student_preferred_trunk_modes=sorted(intended),student_last_main_mode=None)
        initial[mode]+=state['w']
        if len(draws)<2000:draws.append({'uid':state['plan'][0],'mode':mode,'patience_seconds':state['student_patience_seconds']})

    def filter_stages(state,stages,allow_current=True):
        forbidden=set(state.get('visited',()))
        if not allow_current and state.get('node') is not None and ('arrival' in state or state.get('queued') or state.get('preparing')):forbidden.add(state['node'])
        forbidden=frozenset(forbidden);current=state.get('node') if allow_current and (state.get('queued') or state.get('preparing')) else None
        # Cache only the structural history check, never time-dependent queues.
        required=frozenset(state.get('student_preferred_trunk_modes',())) if config.get('initial_trunk_preservation') and state['dest'] in ('snu','daehak') and not state.get('student_flexible') else frozenset()
        previous=state.get('student_last_main_mode')
        key=(state['dest'],repr(stages),forbidden,current,required,previous)
        if key in cache:return copy.deepcopy(cache[key])
        def clean(chain,blocked,allowed,last_main):
            if not chain:return []
            stage=chain[0];entries=[]
            for source in stage.get('pool',[stage]):
                node=node_for(source)
                if node in blocked and node!=allowed:continue
                suffix=source.get('continuation_stages',chain[1:])
                after=main_mode_after(source['rid'],last_main,config)
                future=clean(suffix,blocked|{node},None,after)
                if future is None:continue
                if not future and required and (after or 'access_only') not in required:continue
                if not future and not terminal_allowed(state['dest'],paths[source['next_walk'][0]]['meters'],config):continue
                if not future and not terminal_direction_allowed(state['dest'],source,config,bundle['prepared']['routes']):continue
                entry={k:copy.deepcopy(v) for k,v in source.items() if k not in ('pool','continuation_stages')}
                entry['continuation_stages']=future;entry['choice_pool_locked']=True;entries.append(entry)
            if not entries:return None
            result=dict(entries[0]);result['pool']=entries;result['choice_pool_locked']=True
            return [result]
        result=clean(stages,set(forbidden),current,previous)
        if len(cache)>25000:cache.clear()
        cache[key]=result
        return copy.deepcopy(result)

    def mode_allowed(state,stages,at):
        initialize(state)
        if not stages:return True
        mode=state['student_committed_mode']
        allowed=state['student_flexible'] or mode=='walk' or mode_of(stages)==mode
        if not allowed:return False
        if config.get('initial_trunk_preservation') and state['dest'] in ('snu','daehak') and not state['student_flexible']:
            return trunk_modes(stages,config,state.get('student_last_main_mode'))<=set(state['student_preferred_trunk_modes'])
        return True

    def patience(state):
        value=state['student_patience_seconds']
        if state['dest'].startswith('dorm'):value*=config['dorm_walk_patience_factor']
        return value

    missing=object()
    def context(state,at,current=missing):
        initialize(state);age=max(0.,at-state.get('stop_entry',at));mode=state['student_committed_mode'];more=0;unavailable=False
        if current is missing:current=policy.decision_predict(state['stages'][state['stage']:],at,state,keep=True)
        expected=age+current.first_wait if current is not None else None
        state['student_expected_queue_wait_seconds']=expected
        if state.get('student_entry_forecast_visit')!=state.get('visit'):
            state['student_entry_forecast_visit']=state.get('visit')
            state['student_entry_forecast']={'issued_at':at,'first_wait_seconds':current.first_wait if current else None,'expected_total_queue_wait_seconds':expected}
        # Count compatible departures BEFORE the first forecast-boardable bus.
        # This uses the causal forecast; no future realized loads are read.
        if mode=='city' and state.get('full_passes',0)>=config['city_denial_trigger']:
            if current is None:unavailable=True
            else:
                board_time=at+current.first_wait;stage=current_stage(state)
                seen=set()
                for when,vid,k in schedule[state['node']]:
                    if when<at-EPS or vehicles[vid].get('last_stop',-1)>=k or vehicles[vid].get('processing_stop')==k:continue
                    if when>=board_time-EPS:break
                    if stage_choice(stage,vehicles[vid]['rid'],k) is not None:seen.add(vid)
                more=len(seen)
        stressed=current is None or unavailable or frustration(expected,patience(state),state.get('full_passes',0),more,mode,config)
        if state.get('node') is not None and state.get('stages'):
            stage=current_stage(state);rows=schedule[state['node']]
            start=bisect.bisect_left(rows,(at-EPS,-1,-1))
            if not any(vehicles[vid].get('last_stop',-1)<k and stage_choice(stage,vehicles[vid]['rid'],k) is not None for when,vid,k in rows[start:]):stressed=True
        if config.get('retain_released_mode_flexibility') and state.get('student_flexible') and not config.get('review_requires_current_queue_pressure'):
            stressed=True
        return stressed,age,more

    def alternatives(state,at,current):
        initialize(state);count=len(state['history']);node=state['node'];candidates=[]
        if current is not None:candidates.append({'key':'stay','cost':policy.generalized(current,state),'prediction':current,'option':None,
          'taste_key':strategy_taste_key(state['stages'][state['stage']:],state['dest'])})
        if config.get('gate_is_final_fallback') and state['dest']=='snu' and node==config['gate_fallback_node']:return candidates
        stressed,age,more=context(state,at,current)
        if not stressed:return candidates
        if config.get('same_stop_flexible_pool_choice'):
            # Unlocking a mode must also make legal services at THIS platform
            # reconsiderable. Keep each candidate's suffix; do not force a union
            # whose first bus might be an unnecessary slow detour.
            incumbent=state['stages'][state['stage']:]
            stage=current_stage(state);old_services={(s['rid'],s['board']) for s in stage.get('pool',[stage])}
            source_entries=scaled_stages(bundle.get('compatible_route_policies',{}).get(f"{node}|{state['dest']}",[]),state['factor'])
            additions=[];seen_services=set(old_services)
            for entry in source_entries:
                service=(entry['rid'],entry['board'])
                if service in seen_services or service in state.get('used_services',()):continue
                chain=filter_stages(state,[entry],True)
                if chain is None or not chain or node_for(chain[0])!=node:continue
                additions.extend(chain[0].get('pool',[chain[0]]))
                seen_services.add(service)
            # Individual added services and their union are distinct legitimate
            # boarding policies, including the existing incumbent pool.
            groups=[[entry] for entry in additions]
            if len(additions)>1:groups.append(additions)
            same_stop_choices=[]
            for group in groups:
                entries=[copy.deepcopy(e) for e in stage.get('pool',[stage])]+copy.deepcopy(group)
                for e in entries:e.setdefault('continuation_stages',incumbent[1:])
                expanded=[{**entries[0],'pool':entries,'choice_pool_locked':True}]
                pred=policy.decision_predict(expanded,at,state,keep=True)
                if pred is None:continue
                same_stop_choices.append({'key':repr(('same-stop',complete_signature(expanded))),
                    'cost':policy.generalized(pred,state),'prediction':pred,'option':None,
                    'replacement_stages':expanded,'same_stop_pool_update':True,
                    'taste_key':strategy_taste_key(expanded,state['dest'])})
            # One tactical alternative per platform, rather than more random
            # choice weight at a platform merely having more listed suffixes.
            if same_stop_choices:candidates.append(min(same_stop_choices,key=lambda c:(c['cost'],c['key'])))
        stage=current_stage(state);old={s['rid']:s['board'] for s in stage.get('pool',[stage])}
        for source in bundle['alternatives'].get(f"{node}|{state['dest']}",[]):
            meters=source.get('walk_meters',paths[source['walk'][0]]['meters'])
            if not source['stages'] and not terminal_allowed(state['dest'],meters,config):
                stats['far_terminal_walk_excluded']+=1;continue
            chain=filter_stages(state,source['stages'],False)
            if chain is None:stats['revisit_chain_excluded']+=1;continue
            first=node_for(chain[0]) if chain else None
            if chain and (first==node or first in state.get('visited',())):continue
            access=source['walk'][1]*state['factor']
            if access<=EPS:continue
            prior=walking_weight(meters);relief=math.exp(-.35*state['full_passes']-age/1800)
            prior=1-(1-prior)*relief if prior>0 else 0.
            if chain and all(s['rid'] in old and s['board']>old[s['rid']] for s in chain[0].get('pool',[chain[0]])):
                prior*=config['same_line_downstream_prior']
            if prior<=0:continue
            lower=state['traits'].walk*access/60+state['traits'].change*(1+.5*count)
            best=min((c['cost'] for c in candidates),default=math.inf)
            if lower>best+12*config['choice_temperature_minutes'] and not (config.get('exponential_repeat_walk') and count>0 and not chain):continue
            pred=policy.decision_predict(chain,at,state,access,state['factor'],False,access_path=source['walk'][0])
            if pred is None:continue
            option={**source,'stages':chain}
            candidates.append({'key':repr((first,source['walk'][0],complete_signature(chain))),'cost':policy.generalized(pred,state,True),
              'prediction':pred,'option':option,'prior':prior,'taste_key':(state['dest'],complete_signature(chain))})
        # Same access and strict subset of the same one-stage boarding policy
        # must not receive extra probability merely through duplicate listings.
        return remove_redundant(candidates)

    def maybe_switch(state,at,reason,forced=False):
        initialize(state)
        if config.get('gate_is_final_fallback') and state['dest']=='snu' and state.get('node')==config['gate_fallback_node']:return False
        if state.get('enroute_intercept') or state.get('student_enroute_active') or state.get('enroute_pending'):return False
        stressed,age,more=context(state,at)
        if not stressed:
            stats['loyalty_retained_reviews']+=1;return False
        if not state['student_flexible']:
            state['student_first_release']={'time':at,'node':state.get('node'),'age':age,'patience':patience(state),
                'expected_total_queue_wait_seconds':state.get('student_expected_queue_wait_seconds'),
                'full_passes':state.get('full_passes',0),'predicted_additional_passes':more,
                'mode':state['student_committed_mode']}
        state['student_flexible']=True;stats['eligible_reconsideration_reviews']+=1
        if state.get('full_passes',0)>=config['city_denial_trigger'] and more>=config['city_additional_pass_trigger']:stats['denial_and_remaining_queue_reviews']+=1
        return raw_maybe(state,at,'student_anticipated_wait_review' if reason=='arrival' else reason,forced)

    def reschedule(state,at):
        initialize(state)
        if not state.get('queued') or state['done']:return
        if config.get('gate_is_final_fallback') and state['dest']=='snu' and state.get('node')==config['gate_fallback_node']:return
        if state.get('enroute_intercept') or state.get('student_enroute_active') or state.get('enroute_pending'):return
        stressed,age,more=context(state,at)
        if stressed:return raw_reschedule(state,at)
        due=state['stop_entry']+patience(state)
        state['check_version']+=1
        if due<=END:push(max(at+1e-6,due),2,'recheck',(state,state['check_version']))

    def initial_choice(state,at):
        initialize(state);mode=state['student_preferred_mode'];plan=state['plan']
        def check(chain):
            if not config.get('initial_trunk_preservation') or state['dest'] not in ('snu','daehak'):return
            allowed=set(state['student_preferred_trunk_modes']);actual=trunk_modes(chain,config)
            trunk_checks['checked_weight']+=state['w']
            if len(allowed)>1:trunk_checks['ambiguous_source_weight']+=state['w']
            if not actual<=allowed:trunk_checks['violation_weight']+=state['w']
            assert actual<=allowed,('Unreleased initial trunk change',state['plan'][0],actual,allowed)
        if mode=='walk':check(state['stages']);return
        if mode=='shuttle':
            safe=filter_stages(state,state['stages'],False)
            if safe is not None:
                check(safe)
                state['stages']=safe;state['plan']=[*plan[:6],safe];return
        origin=tuple(common['paths'][plan[5][0]][0]);key=repr((plan[1],state['dest'],origin));options=bundle['student_origin_catalog'].get(key,[])
        primary_choice=mode=='city' and config.get('city_initial_primary_stop',False)
        if primary_choice:
            expanded=[]
            for source in options:
                cache_key=(state['dest'],source['walk'][0],complete_signature(source['stages']))
                if cache_key not in primary_cache:
                    branches=split_primary_stops(source['stages'],state['dest'],config,node_for)
                    primary_cache[cache_key]=[{**source,'stages':chain,'primary_node':node,'key':repr((source['key'],'primary',node))} for node,chain in branches.items() if node is not None]
                expanded.extend(primary_cache[cache_key])
            options=expanded
        candidates=[];fallback=[];use_frequency=mode=='city' and config.get('city_initial_information')=='headway_expectation'
        for source in options:
            if mode_of(source['stages'])!=mode:continue
            chain=filter_stages(state,source['stages'],False)
            if not chain:continue
            access=source['walk'][1]*state['factor']
            fallback.append((access,source['key'],source,chain))
            if primary_choice:pred=policy.predict(chain,at,state,access,state['factor'],access_path=source['walk'][0],initial_myopic=True)
            else:pred=policy.predict(chain,at,state,access,state['factor'],access_path=source['walk'][0])
            if pred is None:continue
            score=boarding_score(pred,access);info=None
            if use_frequency:
                node=node_for(chain[0]);services=frozenset((e['rid'],e['board']) for e in chain[0].get('pool',[chain[0]]))
                key=(node,services)
                if key not in arrival_cache:
                    arrival_cache[key]=sorted({when for when,vid,k in schedule[node] if (vehicles[vid]['rid'],k) in services})
                times=arrival_cache[key];ready=at+access+config['preparation_seconds'];cell=(key,int(ready//3600))
                if cell not in frequency_cache:frequency_cache[cell]=residual_wait_seconds(times,ready)
                reference=frequency_cache[cell];i=bisect.bisect_left(times,ready-EPS)
                if reference is not None and i<len(times):
                    phase=max(0.,times[i]-ready)
                    score=expected_boarding_score(pred,access,config['preparation_seconds'],phase,reference)
                    info={'empty_queue_reference_seconds':reference,'discarded_second_exact_phase_seconds':phase,
                          'causal_queue_delay_seconds':max(0.,pred.first_wait-config['preparation_seconds']-phase)}
            if primary_choice:
                extension=primary_access_extension(pred,source['primary_node']);score+=extension
                if info is not None:info={**info,'primary_access_after_first_boarding_seconds':extension,'future_transfer_wait_anticipated':False}
            # Future transfer waiting must not re-enter via an ETA tie-break.
            candidates.append((score,access,0. if primary_choice else pred.eta,source['key'],source,chain,info,pred.eta))
        if not candidates:
            stats['initial_no_forecastable_option']+=1
            if not fallback:return
            # Keep a legal transit attempt and its explicit unserved outcome;
            # never silently turn a far station trip into terminal walking.
            o,chain=min(fallback,key=lambda x:x[:2])[-2:]
        else:
            best=min(candidates,key=lambda x:x[:4])
            if use_frequency and any(c[6] is not None for c in candidates):
                # One alternative per physical stop prevents a stop with more
                # duplicated paths/route suffixes gaining probability by count.
                bystop={}
                for candidate in candidates:
                    node=candidate[4]['primary_node'] if primary_choice and config.get('city_initial_group_primary_stop',True) else node_for(candidate[5][0])
                    if node not in bystop or candidate[:4]<bystop[node][:4]:bystop[node]=candidate
                choices=[]
                for node,c in bystop.items():
                    choices.append({'key':str(node),'cost':c[0]/60,'prior':walking_weight(paths[c[4]['walk'][0]]['meters']),
                        'option':{'walk':c[4]['walk'],'stages':c[5]},'taste_key':('initial-stop',state['dest'],node),'candidate':c})
                selected=choose(choices,plan[0],('initial-headway-stop',),config)
                if selected:best=selected['candidate']
                stats['frequency_initial_choice_weight']+=state['w']
            o,chain=best[4:6]
            initial_stops[str(node_for(chain[0]))]+=state['w']
            if primary_choice:primary_stops[str(o['primary_node'])]+=state['w']
            if len(initial_samples)<100:
                initial_samples.append({'uid':plan[0],'time':at,'node':node_for(chain[0]),'score_seconds':best[0],
                    'access_seconds':best[1],'exact_forecast_eta':best[7],'reference':best[6],
                    'primary_node':o.get('primary_node'),'future_eta_used_in_tie_break':not primary_choice,
                    'information':config.get('city_initial_information'),'feasible_strategy_count':len(candidates)})
        changed=(plan[5][0],complete_signature(plan[6]))!=(o['walk'][0],complete_signature(chain))
        check(chain)
        policy.initial_choices+=int(changed);stats['initial_city_stop_optimized']+=int(changed)
        rows=scaled_stages(chain,state['factor']);state['plan']=[*plan[:5],[o['walk'][0],o['walk'][1]*state['factor']],rows];state['stages']=rows

    def complete(state,stage,node):
        initialize(state);result=stage if stage.get('choice_pool_locked') else raw_complete(state,stage,node)
        if config.get('gate_is_final_fallback') and state['dest']=='snu' and node==config['gate_fallback_node']:
            entries=scaled_stages(bundle.get('compatible_route_policies',{}).get(f"{node}|snu",[]),state['factor'])
            for e in entries:e.setdefault('continuation_stages',[])
            if entries:result={**entries[0],'pool':entries,'choice_pool_locked':True}
        if state.get('rides_taken',0)>0 and not state['student_flexible']:
            state['student_committed_mode']=mode_of([stage])
        # Before releasing a commitment, an expanded physical-stop pool must
        # not silently board a different mode.
        if not state['student_flexible'] and state['student_committed_mode']!='walk':
            entries=[s for s in result.get('pool',[result]) if mode_of([s])==state['student_committed_mode']]
            if entries:result={**entries[0],'pool':entries}
        cleaned=filter_stages(state,[result],True)
        if cleaned:return cleaned[0]
        stats['invalid_incumbent_blocked']+=1
        return {**result,'pool':[],'choice_pool_locked':True}

    def accept(state,chosen,vehicle,k,at,available):
        # A compatible service with a seat is taken; no gratuitous refusal
        # caused by a fresh iid comparison against an already available bus.
        stats['available_compatible_boarding_accepted']+=1
        return True

    def boarded(state,rid,chosen,at,end):
        initialize(state);raw_boarded(state,rid,chosen,at,end);node=state.get('node')
        state['student_last_main_mode']=main_mode_after(rid,state.get('student_last_main_mode'),config)
        if node in state.get('visited',()):stats['revisit_boarding_violation_weight']+=state['w']
        if node is not None:
            state['visited']=state.get('visited',set())|{node}
            state['student_stop_history']=state.get('student_stop_history',[])+[node]

    def commit(state,at,reason,selected,current=None):
        if selected is not None and selected.get('same_stop_pool_update'):
            # A policy extension within one physical queue changes neither its
            # ticket nor elapsed wait, denial experience, walking or stop history.
            before=list(state['entry_eligibility']);chain=selected['replacement_stages']
            state['stages']=[*state['stages'][:state['stage']],*copy.deepcopy(chain)]
            after=[(s['rid'],s['board']) for s in current_stage(state).get('pool',[current_stage(state)])]
            periods=state.get('eligibility_periods',[{'from':state['arrival'],'services':before}])
            state['eligibility_periods']=[*periods,{'from':at,'services':after}]
            state['entry_eligibility']=list(dict.fromkeys(tuple(x) for x in before+after))
            # Rebuild sparse FIFO pattern indexes without moving this person.
            policy.invalidate_queue(state['node'])
            policy.refresh_committed_services(state)
            stats['same_stop_policy_update_weight']+=state['w']
            if len(same_stop_updates)<5000:
                same_stop_updates.append({'time':at,'uid':state['plan'][0],'node':state['node'],
                    'weight':state['w'],'ticket':state.get('queue_ticket'),'before':before,'after':after,
                    'stop_entry':state['stop_entry'],'full_passes':state['full_passes'],
                    'route_change_count':len(state['history']),'reason':reason})
            # Engine callers continue the existing arrival or review scheduling.
            return False
        node=state['node'];before={'student_mode_before':state['student_committed_mode'],
          'student_preferred_mode':state['student_preferred_mode'],'student_patience_seconds':patience(state),
          'student_visited_before':sorted(state.get('visited',())),
          'student_predicted_additional_passes':context(state,at,current)[2],
          'student_expected_queue_wait_seconds':state.get('student_expected_queue_wait_seconds')}
        changed=raw_commit(state,at,reason,selected,current)
        if changed:
            decision_log[-1].update(before)
            state['student_stop_history']=state.get('student_stop_history',[])+[node]
            option=selected['option'];state['student_committed_mode']=mode_of(option['stages'])
            stats['mode_or_stop_change_weight']+=state['w']
            if state['dest'].startswith('dorm') and not option['stages']:stats['dorm_terminal_walk_weight']+=state['w']
            if option['stages'] and node_for(option['stages'][0])==config['gate_fallback_node'] and state['dest']=='snu':stats['snu_gate_fallback_weight']+=state['w']
        return changed

    def report():
        r=raw_report();r['student_strategy']={'initial_mode_weights':dict(initial),'counts':dict(stats),'patience_draw_sample':draws,
          'patience_source':f"user-shaped unmeasured heterogeneous scenario; median20min, log_sigma{config['patience_log_sigma']}; dorm factor configurable, default1",
          'initial_city_information':config.get('city_initial_information'),'retains_released_flexibility':bool(config.get('retain_released_mode_flexibility')),
          'review_requires_current_queue_pressure':bool(config.get('review_requires_current_queue_pressure')),
          'initial_city_stop_weights':dict(initial_stops),'initial_city_choice_samples':initial_samples,
           'initial_primary_stop_weights':dict(primary_stops),'initial_primary_stop_choice':bool(config.get('city_initial_primary_stop')),
           'initial_primary_information':'First boarding delay and physical prefix access; no anticipation of transfer waiting. Actual queues/boarding capacity and subsequent reviews are unchanged.',
           'same_stop_policy_updates':same_stop_updates,'same_stop_policy_updates_cap':5000,
           'trunk_preservation':bool(config.get('initial_trunk_preservation')),
           'initial_trunk_checks':dict(trunk_checks),
           'trunk_scope':'SNU/Daehak before release, including initial alternatives and enroute boarding; source whole-chain policy mode set, not measured preference. Ambiguous source pools retain every original mode.',
          'twenty_minutes_is_diagnostic_not_forced_exit':True,'patience_includes_visible_forecast':True,'gate_is_final_fallback':True,'initial_city_objective':config.get('city_initial_information','legacy_exact'),
          'no_stop_returns':True,'enroute_boarding_only_at_legal_platforms':True,'empirical_accuracy':'NOT_EVALUATED_ON_NEW_DATES'}
        return r

    policy.student_initialize=initialize;policy.student_filter_stages=filter_stages;policy.student_mode_allowed=mode_allowed
    policy.student_review_context=context;policy.student_patience=patience
    policy.alternative_choices=alternatives;policy.maybe_switch=maybe_switch;policy.reschedule=reschedule;policy.initial_choice=initial_choice
    policy.complete_same_stop=complete;policy.accept_boarding=accept;policy.boarded=boarded;policy.commit_switch=commit;policy.report=report
    return policy
