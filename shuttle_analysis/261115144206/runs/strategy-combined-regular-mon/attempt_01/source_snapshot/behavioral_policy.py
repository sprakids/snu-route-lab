"""User-specified mode commitment; all thresholds are declared scenarios, not fits."""
from collections import Counter
import bisect,copy,math
from preferences import choose,lognormal,walking_weight
from artifacts import EPS,END

def mode_of(stages):
    return 'walk' if not stages else 'shuttle' if stages[0]['rid'].startswith('shuttle') else 'city'

def personal_patience(identity,mode,config):
    median=config['shuttle_patience_median_seconds'] if mode=='shuttle' else config['city_patience_median_seconds']
    return lognormal(config['seed'],identity,'student-patience',median,config['patience_log_sigma'])

def terminal_allowed(dest,meters,config):
    return dest!='snu' or meters<=config['far_terminal_walk_max_meters']

def boarding_score(pred,access):return access+pred.first_wait

def frustration(age,patience,denied,more,mode,config):
    return age>=patience or (mode=='city' and denied>=config['city_denial_trigger'] and more>=config['city_additional_pass_trigger'])

def configure(policy,bundle,config,node_for,current_stage,schedule,vehicles,queues,qmass,premass,push,decision_log):
    if not config.get('student_strategy'):return policy
    from engine import scaled_stages,stage_choice
    from policy import signature,strategy_taste_key
    paths=bundle['physical_paths'];common=bundle['prepared']['common'];stats=Counter();initial=Counter();draws=[];cache={}
    raw_maybe=policy.maybe_switch;raw_reschedule=policy.reschedule;raw_complete=policy.complete_same_stop
    raw_boarded=policy.boarded;raw_commit=policy.commit_switch;raw_report=policy.report

    def initialize(state):
        if 'student_preferred_mode' in state:return
        mode=mode_of(state['stages']);dest=state['dest']
        if mode=='walk' and dest=='snu' and not terminal_allowed(dest,paths[state['plan'][5][0]]['meters'],config):mode='city'
        state.update(student_preferred_mode=mode,student_committed_mode=mode,student_flexible=False,
          student_patience_seconds=personal_patience(state['plan'][0],mode,config),student_stop_history=[])
        initial[mode]+=state['w']
        if len(draws)<2000:draws.append({'uid':state['plan'][0],'mode':mode,'patience_seconds':state['student_patience_seconds']})

    def filter_stages(state,stages,allow_current=True):
        forbidden=frozenset(state.get('visited',()));current=state.get('node') if allow_current and (state.get('queued') or state.get('preparing')) else None
        # Cache only the structural history check, never time-dependent queues.
        key=(repr(stages),forbidden,current)
        if key in cache:return copy.deepcopy(cache[key])
        def clean(chain,blocked,allowed):
            if not chain:return []
            stage=chain[0];entries=[]
            for source in stage.get('pool',[stage]):
                node=node_for(source)
                if node in blocked and node!=allowed:continue
                suffix=source.get('continuation_stages',chain[1:])
                future=clean(suffix,blocked|{node},None)
                if future is None:continue
                if not future and not terminal_allowed(state['dest'],paths[source['next_walk'][0]]['meters'],config):continue
                entry={k:copy.deepcopy(v) for k,v in source.items() if k not in ('pool','continuation_stages')}
                entry['continuation_stages']=future;entry['choice_pool_locked']=True;entries.append(entry)
            if not entries:return None
            result=dict(entries[0]);result['pool']=entries;result['choice_pool_locked']=True
            return [result]
        result=clean(stages,set(forbidden),current)
        if len(cache)>25000:cache.clear()
        cache[key]=result
        return copy.deepcopy(result)

    def mode_allowed(state,stages,at):
        initialize(state)
        if not stages:return True
        mode=state['student_committed_mode']
        return state['student_flexible'] or mode=='walk' or mode_of(stages)==mode

    def patience(state):
        value=state['student_patience_seconds']
        if state['dest'].startswith('dorm'):value*=config['dorm_walk_patience_factor']
        return value

    def context(state,at,current=None):
        initialize(state);age=max(0.,at-state.get('stop_entry',at));mode=state['student_committed_mode'];more=0;unavailable=False
        # Count compatible departures BEFORE the first forecast-boardable bus.
        # This uses the causal forecast; no future realized loads are read.
        if mode=='city' and state.get('full_passes',0)>=config['city_denial_trigger']:
            if current is None:current=policy.predict(state['stages'][state['stage']:],at,state,keep=True)
            if current is None:unavailable=True
            else:
                board_time=at+current.first_wait;stage=current_stage(state)
                seen=set()
                for when,vid,k in schedule[state['node']]:
                    if when<at-EPS:continue
                    if when>=board_time-EPS:break
                    if stage_choice(stage,vehicles[vid]['rid'],k) is not None:seen.add(vid)
                more=len(seen)
        stressed=unavailable or frustration(age,patience(state),state.get('full_passes',0),more,mode,config)
        if state.get('node') is not None and state.get('stages'):
            stage=current_stage(state);rows=schedule[state['node']]
            start=bisect.bisect_left(rows,(at-EPS,-1,-1))
            if not any(vehicles[vid].get('last_stop',-1)<k and stage_choice(stage,vehicles[vid]['rid'],k) is not None for when,vid,k in rows[start:]):stressed=True
        return stressed,age,more

    def alternatives(state,at,current):
        initialize(state);count=len(state['history']);node=state['node'];candidates=[]
        if current is not None:candidates.append({'key':'stay','cost':policy.generalized(current,state),'prediction':current,'option':None,
          'taste_key':strategy_taste_key(state['stages'][state['stage']:],state['dest'])})
        stressed,age,more=context(state,at,current)
        if not stressed:return candidates
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
            pred=policy.predict(chain,at,state,access,state['factor'],False,access_path=source['walk'][0])
            if pred is None:continue
            option={**source,'stages':chain}
            candidates.append({'key':repr((first,source['walk'][0],signature(chain))),'cost':policy.generalized(pred,state,True),
              'prediction':pred,'option':option,'prior':prior,'taste_key':strategy_taste_key(chain,state['dest'])})
        # Same access and strict subset of the same one-stage boarding policy
        # must not receive extra probability merely through duplicate listings.
        groups={}
        for c in candidates:
            o=c['option']
            if o and len(o['stages'])==1:groups.setdefault(o['walk'][0],[]).append((c,frozenset(signature(o['stages'])[0])))
        redundant={c['key'] for group in groups.values() for c,s in group if any(s<other for d,other in group)}
        return [c for c in candidates if c['key'] not in redundant]

    def maybe_switch(state,at,reason,forced=False):
        initialize(state)
        if state.get('enroute_intercept') or state.get('student_enroute_active') or state.get('enroute_pending'):return False
        stressed,age,more=context(state,at)
        if not stressed:
            stats['loyalty_retained_reviews']+=1;return False
        state['student_flexible']=True;stats['eligible_reconsideration_reviews']+=1
        if state.get('full_passes',0)>=config['city_denial_trigger'] and more>=config['city_additional_pass_trigger']:stats['denial_and_remaining_queue_reviews']+=1
        return raw_maybe(state,at,reason,forced)

    def reschedule(state,at):
        initialize(state)
        if not state.get('queued') or state['done']:return
        if state.get('enroute_intercept') or state.get('student_enroute_active') or state.get('enroute_pending'):return
        stressed,age,more=context(state,at)
        if stressed:return raw_reschedule(state,at)
        due=state['stop_entry']+patience(state)
        state['check_version']+=1
        if due<=END:push(max(at+1e-6,due),2,'recheck',(state,state['check_version']))

    def initial_choice(state,at):
        initialize(state);mode=state['student_preferred_mode'];plan=state['plan']
        if mode=='walk':return
        if mode=='shuttle':
            safe=filter_stages(state,state['stages'],False)
            if safe is not None:
                state['stages']=safe;state['plan']=[*plan[:6],safe];return
        origin=tuple(common['paths'][plan[5][0]][0]);key=repr((plan[1],state['dest'],origin));options=bundle['student_origin_catalog'].get(key,[])
        candidates=[];fallback=[]
        for source in options:
            if mode_of(source['stages'])!=mode:continue
            chain=filter_stages(state,source['stages'],False)
            if not chain:continue
            access=source['walk'][1]*state['factor']
            fallback.append((access,source['key'],source,chain))
            pred=policy.predict(chain,at,state,access,state['factor'],access_path=source['walk'][0])
            if pred is None:continue
            candidates.append((boarding_score(pred,access),access,pred.eta,source['key'],source,chain))
        if not candidates:
            stats['initial_no_forecastable_option']+=1
            if not fallback:return
            # Keep a legal transit attempt and its explicit unserved outcome;
            # never silently turn a far station trip into terminal walking.
            o,chain=min(fallback,key=lambda x:x[:2])[-2:]
        else:
            best=min(candidates,key=lambda x:x[:4]);o,chain=best[-2:]
        changed=(plan[5][0],signature(plan[6]))!=(o['walk'][0],signature(chain))
        policy.initial_choices+=int(changed);stats['initial_city_stop_optimized']+=int(changed)
        rows=scaled_stages(chain,state['factor']);state['plan']=[*plan[:5],[o['walk'][0],o['walk'][1]*state['factor']],rows];state['stages']=rows

    def complete(state,stage,node):
        initialize(state);result=raw_complete(state,stage,node)
        if state.get('rides_taken',0)>0 and not state['student_flexible']:
            state['student_committed_mode']=mode_of([stage])
        # Before releasing a commitment, an expanded physical-stop pool must
        # not silently board a different mode.
        if not state['student_flexible'] and state['student_committed_mode']!='walk':
            entries=[s for s in result.get('pool',[result]) if mode_of([s])==state['student_committed_mode']]
            if entries:result={**entries[0],'pool':entries}
        cleaned=filter_stages(state,[result],True)
        if cleaned:return cleaned[0]
        stats['unexpected_invalid_incumbent_chain']+=1
        return result

    def accept(state,chosen,vehicle,k,at,available):
        # A compatible service with a seat is taken; no gratuitous refusal
        # caused by a fresh iid comparison against an already available bus.
        stats['available_compatible_boarding_accepted']+=1
        return True

    def boarded(state,rid,chosen,at,end):
        initialize(state);raw_boarded(state,rid,chosen,at,end);node=state.get('node')
        if node in state.get('visited',()):stats['revisit_boarding_violation_weight']+=state['w']
        if node is not None:
            state['visited']=state.get('visited',set())|{node}
            state['student_stop_history']=state.get('student_stop_history',[])+[node]

    def commit(state,at,reason,selected,current=None):
        node=state['node'];before={'student_mode_before':state['student_committed_mode'],
          'student_preferred_mode':state['student_preferred_mode'],'student_patience_seconds':patience(state),
          'student_visited_before':sorted(state.get('visited',())),
          'student_predicted_additional_passes':context(state,at,current)[2]}
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
          'patience_source':'user-shaped unmeasured heterogeneous scenario; median20min, log_sigma.25; dorm factor configurable, default1',
          'twenty_minutes_is_diagnostic_not_forced_exit':True,'initial_city_objective':'access walk + forecast first boardable wait/preparation',
          'no_stop_returns':True,'enroute_boarding_only_at_legal_platforms':True,'empirical_accuracy':'NOT_EVALUATED_ON_NEW_DATES'}
        return r

    policy.student_initialize=initialize;policy.student_filter_stages=filter_stages;policy.student_mode_allowed=mode_allowed
    policy.student_review_context=context;policy.student_patience=patience
    policy.alternative_choices=alternatives;policy.maybe_switch=maybe_switch;policy.reschedule=reschedule;policy.initial_choice=initial_choice
    policy.complete_same_stop=complete;policy.accept_boarding=accept;policy.boarded=boarded;policy.commit_switch=commit;policy.report=report
    return policy
