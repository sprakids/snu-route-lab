"""Register an isolated catalog-consistency candidate; preserve prior evidence."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import copy,hashlib,json,shutil
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent;PARENT=ANALYSIS/'261116122336'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists(),p
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def main():
    stamp=datetime.now(timezone(timedelta(hours=9))).strftime('%y%m%d%H%M%S');w=ANALYSIS/stamp;w.mkdir()
    old=read(PARENT/'repair_manifest.json')
    for p in PARENT.glob('*.py'):shutil.copy2(p,w/p.name)
    for n in ['input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md']:shutil.copy2(PARENT/n,w/n)
    for n,h in old['frozen_payloads'].items():
        assert sha(PARENT/n)==h
        dest=w/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(PARENT/n,dest)
    for p in PARENT.glob('physical_paths_*.json.gz'):shutil.copy2(p,w/p.name)
    shutil.copy2(ROOT/'direct_restoration.py',w/'direct_restoration.py')
    cfg=read(PARENT/'config.json');trace=read(ROOT/'law-snu-cohort-trace.json')
    cfg.update(release_id=stamp,version_family='V12-known-direct-policy-restoration',restore_known_snu_direct_policies=True,
        direct_restoration_interpretation='Restore only five existing SNU direct5511 policies missing from origin expansion. Separate complete direct policies, same-service continuation replacement without duplicate first matches; global catalogs, supply, demand and numeric coefficients unchanged. Initial and later unanticipated transfer waiting remain unchanged.',
        diagnostic_uids=sorted(set(cfg['diagnostic_uids'])|{int(k) for k in trace['latest_focus_uid_weights']}))
    save(w/'config.json',cfg)
    p=w/'prepare.py';t=p.read_text(encoding='utf8')
    needle="    # All candidates begin at the exact same inherited origin coordinate.\n"
    add="""    if config.get('student_strategy') and config.get('restore_known_snu_direct_policies'):
        from direct_restoration import known_direct_registry
        lookup={n['id']:i for i,n in enumerate(common['nodes'])}
        def catalog_node(e):
            key=f"{e['rid']}|{e['board']}"
            return lookup[key] if e['rid'].startswith('shuttle') else bundle['city_node_lookup'][key]
        registry,report=known_direct_registry(bundle,catalog_node)
        bundle['restored_direct_policies']=registry;bundle['catalog_repair_report']=report
"""
    assert t.count(needle)==1;t=t.replace(needle,add+needle)
    needle="        bundle['student_origin_catalog']={k:list(v.values()) for k,v in student.items()}\n"
    add="""            if destination=='snu' and config.get('restore_known_snu_direct_policies'):
                from direct_restoration import append_origin_options
                for pid,node in access_by_origin.get(origin,[]):
                    append_origin_options(target,pid,node,bundle,complete_signature)
"""
    assert t.count(needle)==1;t=t.replace(needle,add+needle);p.write_text(t,encoding='utf8')
    p=w/'behavioral_policy.py';t=p.read_text(encoding='utf8')
    needle="            # One tactical alternative per platform, rather than more random\n"
    add="""            if config.get('restore_known_snu_direct_policies'):
                from direct_restoration import same_service_direct_policy
                known={complete_signature(c['replacement_stages']) for c in same_stop_choices}
                for raw in bundle.get('restored_direct_policies',{}).get(f"{node}|{state['dest']}",[]):
                    if (raw['rid'],raw['board']) in state.get('used_services',()):continue
                    cleaned=filter_stages(state,scaled_stages([raw],state['factor']),True)
                    if not cleaned:continue
                    for entry in cleaned[0].get('pool',[cleaned[0]]):
                        expanded=same_service_direct_policy(incumbent,entry)
                        if expanded is None:continue
                        sig=complete_signature(expanded)
                        if sig in known:continue
                        known.add(sig);pred=policy.decision_predict(expanded,at,state,keep=True)
                        if pred is None:continue
                        same_stop_choices.append({'key':repr(('same-stop',sig)),
                            'cost':policy.generalized(pred,state),'prediction':pred,'option':None,
                            'replacement_stages':expanded,'same_stop_pool_update':True,
                            'taste_key':strategy_taste_key(expanded,state['dest'])})
"""
    assert t.count(needle)==1;t=t.replace(needle,add+needle)
    needle="    raw_maybe=policy.maybe_switch;raw_reschedule=policy.reschedule;raw_complete=policy.complete_same_stop\n"
    assert t.count(needle)==1;t=t.replace(needle,"    initial_policy_diagnostics=[]\n"+needle)
    needle="        changed=(plan[5][0],complete_signature(plan[6]))!=(o['walk'][0],complete_signature(chain))\n"
    add="""        if plan[0] in config.get('diagnostic_uids',()):
            initial_policy_diagnostics.append({'uid':plan[0],'time':at,'building':plan[1],
                'selected_first_node':node_for(chain[0]),'selected_primary_node':o.get('primary_node'),
                'selected_source_key':o['key'],'candidate_count':len(candidates),
                'candidates':[{'first_node':node_for(c[5][0]),'primary_node':c[4].get('primary_node'),
                    'score_seconds':c[0],'access_seconds':c[1],'operational_eta_diagnostic_only':c[7],
                    'key':c[4]['key'],'first_services':[(e['rid'],e['board'],e['alight']) for e in c[5][0].get('pool',[c[5][0]])],
                    'restored_direct':any(e.get('known_direct_policy_restored') for e in c[5][0].get('pool',[c[5][0]]))}
                    for c in candidates]})
"""
    assert t.count(needle)==1;t=t.replace(needle,add+needle)
    needle="        r=raw_report();r['student_strategy']={'initial_mode_weights':dict(initial)"
    assert t.count(needle)==1;t=t.replace(needle,"        r=raw_report();r['catalog_repair']=bundle.get('catalog_repair_report');r['initial_policy_diagnostics']=initial_policy_diagnostics;r['student_strategy']={'initial_mode_weights':dict(initial)")
    p.write_text(t,encoding='utf8')
    p=w/'run_case.py';t=p.read_text(encoding='utf8');needle="'perception.py','run_case.py'";assert needle in t
    p.write_text(t.replace(needle,"'perception.py','direct_restoration.py','run_case.py'"),encoding='utf8')
    days=[('월','mon'),('화','tue'),('수','wed'),('목','thu'),('금','fri')]
    cases=[{'case':f'direct-combined-{sc}-{eng}','mode':'combined','day':day,'scenario':sc,'seed':0,'operations':'v12_empirical'} for sc in ['regular','peak'] for day,eng in days]
    cases.append({'case':'ablation-no-direct-restoration-tue','mode':'combined','day':'화','scenario':'regular','seed':0,'operations':'v12_empirical',
        'config_overrides':{'restore_known_snu_direct_policies':False}})
    save(w/'experiment_lock.json',{'status':'REGISTERED_BEFORE_EXECUTION','release_id':stamp,'implementation_parent':str(PARENT),
        'comparison_parent':PARENT.name,'broader_reference':'261116010854','pilot_cases':cases,
        'selection_rule':'Pilot Monday/Tuesday main plus disabled Tuesday diagnostic once each. Require physical/user invariants, no unserved, exact disabled parent reproduction, five known direct policies retained, nonworsening parent-F all-recorded over20 sum, maximum wait, each-day mean journey, reused field-error sum and gate observation expected error; strict improvement in over20 or field-error. Also require decreased SNU transfer arrivals at law in15-20 and nonworsening afternoon law maximum over both nodes/days. If qualified extend8main cases only. Full-week tables compare original010854 because parentF has only Monday/Tuesday completed. No numerical fit or new-date outcomes.',
        'new_day_outcomes_opened':False,'production_replacement_allowed':False,
        'retained_user_behavior':read(PARENT/'experiment_lock.json')['retained_user_behavior']})
    protect=old['protected'].copy()
    for p in PARENT.iterdir():
        if p.is_file():protect[str(p)]=sha(p)
    save(w/'repair_manifest.json',{'parent':str(PARENT),'comparison_parent':PARENT.name,'release_id':stamp,'protected':protect,
        'frozen_payloads':old['frozen_payloads'],'config_sha256':sha(w/'config.json'),'production_writes':False})
    save(ROOT/'candidate.json',{'release_id':stamp,'path':str(w),'parent':PARENT.name})
    print(w,flush=True)
if __name__=='__main__':main()
