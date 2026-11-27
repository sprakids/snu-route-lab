"""Extend the existing same-line-downstream consideration rule across access legs."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parent;A=ROOT.parent;PARENT=A/'261116153200'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists(),p
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def main():
    stamp=datetime.now(timezone(timedelta(hours=9))).strftime('%y%m%d%H%M%S');w=A/stamp;w.mkdir()
    old=read(PARENT/'repair_manifest.json')
    for p in PARENT.glob('*.py'):shutil.copy2(p,w/p.name)
    for n in ['input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md']:shutil.copy2(PARENT/n,w/n)
    for n,h in old['frozen_payloads'].items():
        assert sha(PARENT/n)==h
        dest=w/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(PARENT/n,dest)
    for p in PARENT.glob('physical_paths_*.json.gz'):shutil.copy2(p,w/p.name)
    shutil.copy2(ROOT/'primary_opportunity.py',w/'primary_opportunity.py')
    cfg=read(PARENT/'config.json');cfg.update(release_id=stamp,version_family='V12-shared-mainline-access-recognition',
        recognize_shared_main_downstream_access=True,
        shared_main_interpretation='Existing same_line_downstream_prior0.08 is also used when a feeder precedes boarding the same already-offered primary rid farther downstream, with exact final alight and direction. Not a new weight, hard ban, extra wait/ETA or future-queue forecast. Target scope SNU. Existing direct restoration retained.')
    save(w/'config.json',cfg)
    p=w/'behavioral_policy.py';t=p.read_text(encoding='utf8')
    needle='    def alternatives(state,at,current):\n'
    extra="""    def shared_main_prior(state,chain,pred,reference_node=None):
        if not config.get('recognize_shared_main_downstream_access') or state['dest']!='snu':return 1.
        from primary_opportunity import same_main_downstream_access
        if same_main_downstream_access(chain,pred,state['dest'],config,node_for,bundle,reference_node):
            return config['same_line_downstream_prior']
        return 1.

"""
    assert t.count(needle)==1;t=t.replace(needle,extra+needle)
    # Two same-platform candidate constructors: old expansion and restored direct.
    a="'taste_key':strategy_taste_key(expanded,state['dest'])})"
    b="'taste_key':strategy_taste_key(expanded,state['dest']),'prior':shared_main_prior(state,expanded,pred,node)})"
    assert t.count(a)==2;t=t.replace(a,b)
    a="if same_stop_choices:candidates.append(min(same_stop_choices,key=lambda c:(c['cost'],c['key'])))"
    b="if same_stop_choices:candidates.append(min(same_stop_choices,key=lambda c:(c['cost']-config['choice_temperature_minutes']*math.log(c.get('prior',1.)),c['key'])))"
    assert t.count(a)==1;t=t.replace(a,b)
    a="            if chain and all(s['rid'] in old and s['board']>old[s['rid']] for s in chain[0].get('pool',[chain[0]])):\n                prior*=config['same_line_downstream_prior']"
    b="            direct_downstream=chain and all(s['rid'] in old and s['board']>old[s['rid']] for s in chain[0].get('pool',[chain[0]]))\n            if direct_downstream:prior*=config['same_line_downstream_prior']"
    assert t.count(a)==1;t=t.replace(a,b)
    a="            option={**source,'stages':chain}\n"
    b="            if chain and not direct_downstream:prior*=shared_main_prior(state,chain,pred,node)\n"+a
    assert t.count(a)==1;t=t.replace(a,b)
    a="            # Future transfer waiting must not re-enter via an ETA tie-break.\n"
    b="""            if primary_choice and config.get('recognize_shared_main_downstream_access'):
                consideration=shared_main_prior(state,chain,pred)
                if consideration<1.:
                    penalty=-60*config['choice_temperature_minutes']*math.log(consideration)
                    score+=penalty
                    info={**(info or {}),'same_main_downstream_consideration_prior':consideration,
                          'consideration_penalty_equivalent_seconds':penalty,
                          'penalty_is_physical_wait_or_eta':False}
"""+a
    assert t.count(a)==1;t=t.replace(a,b)
    a="'score_seconds':c[0],'access_seconds':c[1],'operational_eta_diagnostic_only':c[7],"
    b="'score_seconds':c[0],'access_seconds':c[1],'operational_eta_diagnostic_only':c[7],'reference':c[6],"
    assert t.count(a)==1;t=t.replace(a,b);p.write_text(t,encoding='utf8')
    p=w/'run_case.py';t=p.read_text(encoding='utf8');a="'direct_restoration.py','run_case.py'";assert a in t
    p.write_text(t.replace(a,"'direct_restoration.py','primary_opportunity.py','run_case.py'"),encoding='utf8')
    days=[('월','mon'),('화','tue'),('수','wed'),('목','thu'),('금','fri')]
    cases=[{'case':f'shared-combined-{sc}-{eng}','mode':'combined','day':day,'scenario':sc,'seed':0,'operations':'v12_empirical'} for sc in ['regular','peak'] for day,eng in days]
    cases.append({'case':'ablation-no-shared-main-tue','mode':'combined','day':'화','scenario':'regular','seed':0,'operations':'v12_empirical',
        'config_overrides':{'recognize_shared_main_downstream_access':False}})
    save(w/'experiment_lock.json',{'status':'REGISTERED_BEFORE_EXECUTION','release_id':stamp,'implementation_parent':str(PARENT),
        'comparison_parent':PARENT.name,'broader_reference':'261116010854','pilot_cases':cases,
        'selection_rule':'Match parentG Monday/Tuesday regular and disabled Tuesday diagnostic once each. Same physical/user/data gates; require nonworsening over20 sum, max wait, each mean journey, reused field-error sum, gate expected error and afternoon law maximum; strict over20 decrease plus decreased SNU law transfer arrivals. Disabled parent reproduced1e-6. Only then remaining8main cases. Existing numeric0.08 and2min temperature unchanged; topology-based shared-main consideration only, no future-transfer waiting added.',
        'new_day_outcomes_opened':False,'production_replacement_allowed':False,'retained_user_behavior':read(PARENT/'experiment_lock.json')['retained_user_behavior']})
    protect=old['protected'].copy()
    for p in PARENT.iterdir():
        if p.is_file():protect[str(p)]=sha(p)
    save(w/'repair_manifest.json',{'parent':str(PARENT),'comparison_parent':PARENT.name,'release_id':stamp,'protected':protect,
        'frozen_payloads':old['frozen_payloads'],'config_sha256':sha(w/'config.json'),'production_writes':False})
    save(ROOT/'shared-candidate.json',{'release_id':stamp,'path':str(w),'parent':PARENT.name})
    print(w,flush=True)
if __name__=='__main__':main()
