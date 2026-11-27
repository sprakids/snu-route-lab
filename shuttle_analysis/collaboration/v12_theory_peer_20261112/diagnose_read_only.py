"""Old frozen V12 audit plus algebra/decision-function checks only; no model run."""
import ast
import bisect
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
ANALYSIS=HERE.parents[1]
V12=ANALYSIS/'261112111627'
sys.dont_write_bytecode=True
sys.path.insert(0,str(V12))
from preferences import choose,traits,Prediction
from policy import prospective_age_discomfort

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def total(trip):return trip['legs'][-1][2]-trip['start']

def main():
    run=V12/'runs/v12_empirical-combined-regular-tue/attempt_01'
    protected=[V12/n for n in ['preferences.py','policy.py','engine.py','hazard.py','config.json']]+[run/'audit-regular-tue.json.gz',run/'result.json']
    before={str(p.relative_to(ANALYSIS)):sha(p) for p in protected}
    receipt=json.loads((run/'result.json').read_text(encoding='utf-8'));config=receipt['config']
    assert config['behavior']=='sequential' and config['boarding_choice'] and config['origin_choice']
    choices=[{'key':'stay','cost':10.},{'key':'switch','cost':12.}]
    fixed=[choose(choices,1,('reroute',1,1),config)['key'] for _ in range(10)]
    refreshed=[choose(choices,1,('reroute',1,i),config)['key'] for i in range(1,21)]
    assert len(set(fixed))==1
    taste=traits(1,config);assert taste==traits(1,config)
    p_switch=1/(1+math.exp((12.-10.)/config['choice_temperature_minutes']))
    age=900.;future=300.
    pred=Prediction(eta=future,wait=future,first_wait=future,wait_squared=future**2,wait_cubed=future**3)
    old=prospective_age_discomfort(pred,age,0,config)/60
    reset=prospective_age_discomfort(pred,0.,0,config)/60
    # This is an illustrative one-person coefficient1 calculation, not a fit.
    assert abs(old-15.416666666666666)<1e-9 and abs(reset-.4166666666666667)<1e-9
    temp=config['choice_temperature_minutes'];costs={'board':12.,'wait':10.,'walk':11.}
    ex={k:math.exp(-v/temp) for k,v in costs.items()};den=sum(ex.values())
    flat={k:v/den for k,v in ex.items()}
    root_board=ex['board']/(ex['board']+ex['wait']);continuing=1-root_board
    nested={'board':root_board,'wait':continuing*ex['wait']/(ex['wait']+ex['walk']),
            'walk':continuing*ex['walk']/(ex['wait']+ex['walk'])}
    # Extract the actual early-return decision function without attaching/running the engine.
    tree=ast.parse((V12/'policy.py').read_text(encoding='utf-8'))
    node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='accept_boarding')
    scope={'current_stage':lambda state:{'pool':[state['stages'][0]]},'choose':choose,'config':config}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<frozen boarding early return>','exec'),scope)
    proxy=SimpleNamespace(predict=lambda *args,**kw:Prediction(3600.) if 'override' in kw else None)
    state={'stages':[{'rid':'R'}],'stage':0,'plan':[1],'visit':1}
    early_accept=scope['accept_boarding'](proxy,state,state['stages'][0],{'id':1,'rid':'R'},0,0.,44.)
    assert early_accept is True
    with gzip.open(run/'audit-regular-tue.json.gz','rt',encoding='utf-8') as f:audit=json.load(f)
    worst=max(audit['legs'],key=total);components=Counter()
    waits=[];merged=[]
    for leg in worst['legs']:
        components[str(leg[0])]+=leg[2]-leg[1]
        if leg[0]==1:
            waits.append((leg[2]-leg[1])/60)
            if merged and merged[-1][0]==leg[4] and abs(merged[-1][2]-leg[1])<1e-5:merged[-1][2]=leg[2]
            else:merged.append([leg[4],leg[1],leg[2]])
    assert abs(sum(components.values())-total(worst))<1e-5
    declines=audit['boarding_choices'];switches=audit['behavior_decisions'];index=defaultdict(list)
    for x in switches:index[(x['uid'],x['origin'])].append(x)
    for group in index.values():group.sort(key=lambda x:x['time'])
    paired=[]
    for x in declines:
        group=index.get((x['uid'],x['node']),[])
        i=bisect.bisect_left([y['time'] for y in group],x['time'])
        while i<len(group) and group[i]['time']-x['time']<.01:
            y=group[i]
            if 0<y['time']-x['time']<.01:
                paired.append({'uid':x['uid'],'node':x['node'],'decline_at':x['time'],'switch_at':y['time'],
                  'delay_seconds':y['time']-x['time'],'weight':x['weight'],'available':x['seats_available'],
                  'board_cost':x['board_cost'],'wait_cost':x['wait_cost'],'new_kind':y['kind'],'new_eta':y['new_eta']})
                break
            i+=1
    worst_decisions=[x for x in switches if x['uid']==worst['id'] and any(abs(x['time']-h[0])<1e-5 for h in worst['history'])]
    slower=[x for x in worst_decisions if x['old_eta'] is not None and x['new_eta']>x['old_eta']+1e-7]
    unchanged=all(sha(ANALYSIS/k)==v for k,v in before.items());assert unchanged
    result={'scope':'old frozen Tuesday V12 audit; algebra and isolated decision functions only; no new simulator run/new-day outcome/source edits',
      'reviewed_at':datetime.now(timezone(timedelta(hours=9))).isoformat(),
      'source_sha256':before,'source_unchanged':unchanged,
      'effective_config':{k:config[k] for k in ['behavior','boarding_choice','origin_choice','choice_temperature_minutes','integrate_future_wait_discomfort','waiting_discomfort_age_scale_seconds','repeat_multiplier']},
      'noise_check':{'fixed_person_traits':taste.record(),'same_event_repeated':fixed,'different_events_same_costs':refreshed,
        'illustrative_stay_cost':10.,'illustrative_switch_cost':12.,'one_review_switch_probability':p_switch,
        'ten_independent_same_cost_reviews_any_switch_probability':1-(1-p_switch)**10,
        'is_empirical_behavior_estimate':False},
      'age_reset_algebra':{'current_local_age_seconds':age,'remaining_wait_seconds':future,
        'extra_cost_if_stay_minutes_at_wait_coefficient1':old,'extra_cost_if_age_reset_minutes_at_wait_coefficient1':reset,
        'cost_drop_minutes':old-reset,'physical_wait_added_or_deleted':0,'hypothetical_two_minute_walk_plus_first_change_cost_minutes':2*2+1.5,
        'is_empirical_behavior_estimate':False},
      'two_stage_algebra':{'cost_minutes':costs,'flat_joint_logit_probabilities':flat,'board_wait_then_wait_walk_probabilities':nested,
        'need_inclusive_value_or_same_joint_action_set_for_equivalent_static_RUM':True,
        'actual_boarding_early_return_when_future_none':early_accept,'is_claim_all_sequential_models_are_invalid':False},
      'old_audit':{'decision_record_unit':'weighted simulated lineage events; not independent people',
        'voluntary_boarding_decline_records':len(declines),
        'declines_when_deterministic_board_cost_lower':sum(x['board_cost']<x['wait_cost'] for x in declines),
        'decline_then_same_uid_node_switch_within_10ms_records':len(paired),
        'paired_count_is_not_unique_people_or_causal_attribution':True,
        'paired_first_examples':paired[:8],
        'worst_lineage':{'uid':worst['id'],'weight':worst['weight'],'parent_id':worst.get('parent_id'),
           'start':worst['start'],'finish':worst['finish_time'],'total_minutes':total(worst)/60,
           'changes':len(worst['history']),'history':worst['history'],
           'minutes_by_leg_kind':{k:v/60 for k,v in components.items()},
           'maximum_continuous_wait_minutes':max((b-a)/60 for node,a,b in merged),
           'same_uid_voluntary_decline_records':sum(x['uid']==worst['id'] for x in declines),
           'slower_predicted_eta_switch_records':len(slower),
           'slower_predicted_eta_switch_examples':[{k:x[k] for k in ['time','origin','target','reason','old_eta','new_eta','change_count_before','continuous_wait_seconds']} for x in slower[:5]],
           'physical_time_reconciles':True}},
      'not_established':['fraction of total V12 tail error causally attributable to each mechanism','which mechanism explains observed queue-count mismatch','empirical SNU parameter estimates','post-fix performance']}
    (HERE/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'source_unchanged':unchanged,'one_vs_ten_noise_opportunities':[p_switch,1-(1-p_switch)**10],
      'age_cost_drop':old-reset,'two_stage':result['two_stage_algebra'],
      'voluntary_declines':len(declines),'declines_lower_board_cost':result['old_audit']['declines_when_deterministic_board_cost_lower'],
      'decline_then_switch_10ms':len(paired),
      'worst':{k:v for k,v in result['old_audit']['worst_lineage'].items() if k not in ['history','slower_predicted_eta_switch_examples']}},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
