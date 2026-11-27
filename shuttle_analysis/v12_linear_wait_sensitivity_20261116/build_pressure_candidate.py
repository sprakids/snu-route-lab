"""Separate persistent mode freedom from current-stop reconsideration pressure."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,shutil
HERE=Path(__file__).resolve().parent
ANALYSIS=HERE.parent
PARENT=ANALYSIS/'261116112731'
COMMON=ANALYSIS/'v12_current_pressure_20261116'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists(),p
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def main():
    assert not COMMON.exists();COMMON.mkdir()
    for p in HERE.glob('*.py'):
        if not p.name.startswith(('build_','finalize_','record_')):shutil.copy2(p,COMMON/p.name)
    stamp=datetime.now(timezone(timedelta(hours=9))).strftime('%y%m%d%H%M%S')
    work=ANALYSIS/stamp;work.mkdir()
    old=read(PARENT/'repair_manifest.json')
    for p in PARENT.glob('*.py'):shutil.copy2(p,work/p.name)
    for n in ['input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md']:shutil.copy2(PARENT/n,work/n)
    for n,h in old['frozen_payloads'].items():
        assert sha(PARENT/n)==h
        dest=work/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(PARENT/n,dest)
    for p in PARENT.glob('physical_paths_*.json.gz'):shutil.copy2(p,work/p.name)
    p=work/'behavioral_policy.py';t=p.read_text(encoding='utf8')
    a="        if config.get('retain_released_mode_flexibility') and state.get('student_flexible'):\n            stressed=True\n"
    b="        if config.get('retain_released_mode_flexibility') and state.get('student_flexible') and not config.get('review_requires_current_queue_pressure'):\n            stressed=True\n"
    assert t.count(a)==1;t=t.replace(a,b)
    t=t.replace("'retains_released_flexibility':bool(config.get('retain_released_mode_flexibility')),", "'retains_released_flexibility':bool(config.get('retain_released_mode_flexibility')),\n          'review_requires_current_queue_pressure':bool(config.get('review_requires_current_queue_pressure')),")
    p.write_text(t,encoding='utf8')
    p=work/'test_student_strategy.py';t=p.read_text(encoding='utf8')
    a="        self.assertTrue(p.student_review_context(s,50.,pred)[0])\n"
    b="        self.assertEqual(p.student_review_context(s,50.,pred)[0],not c.get('review_requires_current_queue_pressure',False))\n        self.assertTrue(s['student_flexible'])\n"
    assert t.count(a)==1;p.write_text(t.replace(a,b),encoding='utf8')
    # Test the post-gate same-platform selector in isolation; the full-engine
    # tests still use P=1s and exercise an actual current-queue pressure trigger.
    p=work/'test_same_stop_release.py';t=p.read_text(encoding='utf8')
    a="        s.update(arrival=0.,entry_eligibility=[('A',0)],queue_ticket=7,used_services=set())"
    b="        c['review_requires_current_queue_pressure']=False  # Isolated post-gate tactical selector.\n"+a
    assert t.count(a)==1;p.write_text(t.replace(a,b),encoding='utf8')
    cfg=read(PARENT/'config.json');cfg.update(release_id=stamp,version_family='V12-mode-freedom-current-pressure-separated',
        review_requires_current_queue_pressure=True,
        review_pressure_interpretation='Persistent freedom to choose city/shuttle is not perpetual dissatisfaction. At every new stop, physical rerouting still requires current expected total queue wait over the same personal P, or inherited actual-denial/additional-pass/no-service conditions. Existing clock, P, full events, unlimited changes and walk rule remain. No new patience draw, cooldown, queue cap or coefficient.')
    save(work/'config.json',cfg)
    days=[('월','mon'),('화','tue'),('수','wed'),('목','thu'),('금','fri')]
    cases=[{'case':f'pressure-combined-{sc}-{eng}','mode':'combined','day':day,'scenario':sc,'seed':0,'operations':'v12_empirical'} for sc in ['regular','peak'] for day,eng in days]
    cases.append({'case':'ablation-sticky-review-mon','mode':'combined','day':'월','scenario':'regular','seed':0,
        'operations':'v12_empirical','config_overrides':{'review_requires_current_queue_pressure':False}})
    rule=('Monday/Tuesday regular main plus Monday pressure-separation-disabled diagnostic, once each. '
          'Compare the request baseline261116010854: physical/user behavior pass, zero unserved, '
          'nonworsening all-recorded over20 sum, four-reused-observation error sum, maximum wait, and each weekday mean journey; '
          'at least one strict improvement. Only then execute remaining eight main cases. Direct parent D and intermediate C reported separately. '
          'No demand/capacity/clock/patience/taste fit. All failures retained. No operating replacement.')
    save(work/'experiment_lock.json',{'status':'REGISTERED_BEFORE_EXECUTION','release_id':stamp,'implementation_parent':str(PARENT),
        'comparison_parent':'261116010854','pilot_cases':cases,'selection_rule':rule,'new_day_outcomes_opened':False,
        'production_replacement_allowed':False,'retained_user_behavior':read(PARENT/'experiment_lock.json')['retained_user_behavior']})
    protect=old['protected'].copy()
    for folder in [PARENT,ANALYSIS/'261116105704',ANALYSIS/'261116120358']:
        for p in folder.iterdir():
            if p.is_file():protect[str(p)]=sha(p)
    save(work/'repair_manifest.json',{'parent':str(PARENT),'comparison_parent':'261116010854','release_id':stamp,
        'protected':protect,'frozen_payloads':old['frozen_payloads'],'config_sha256':sha(work/'config.json'),'production_writes':False})
    (COMMON/'PROTOCOL.md').write_text('''# 수단 자유와 현재 정류장의 변경 사유 분리

112731의 재검토 인지 일치와 기존 비선형 대기 효용을 유지한다.120358의 비용함수 민감도는월화평균+6.34/+5.03분으로실패해종료했으며이를수치조정으로구제하지않는다. 새로 확인한 것은 retain_released_mode_flexibility가한번true면현재 줄이짧아도stressed=True로만드는별개 상태 가정이다. 기존 단위시험에도 의도적으로 고정되어 있었으므로 우연한 코딩오류라고 단정하지 않는다.

사용자의 ‘기다리는데 만차가 반복되고 줄이 길면 다시 변경’과 수단을 자유롭게 고르는 상태를 분리한다. student_flexible는초기수단충성을다시걸지않는영구자유상태로유지한다. 새정류장에서는현재예상총대기·실제만차/추가통과·운행부재중기존기준으로변경사유가있을때만물리경로를재검토한다. 현재줄의시계·P·만차는원래대로이고현재줄이문제인동안에는재검토를계속한다. 제한/쿨다운/새숫자는없다. 초기·이후 모두 후속환승대기를미예견한다.

'''+rule+'\n\n모형선택과내부결과는새날짜실측정확도검증이아니다. 공개V11은유지한다.\n',encoding='utf8')
    for name in ['summarize_refinement.py','check_pilot.py','reconcile_outputs.py']:
        p=COMMON/name;t=p.read_text(encoding='utf8');p.write_text(t.replace('261116105704','261116010854'),encoding='utf8')
    p=COMMON/'check_legacy.py';t=p.read_text(encoding='utf8');p.write_text(t.replace("'test_linear_wait_sensitivity']","'test_linear_wait_sensitivity','test_current_pressure']"),encoding='utf8')
    p=COMMON/'freeze_candidate.py';t=p.read_text(encoding='utf8');t=t.replace("'test_linear_wait_sensitivity.py'","'test_current_pressure.py'")
    p.write_text(t.replace('Bounded student linear-future-wait sensitivity with literal unanticipated transfer waits.','Separate persistent mode freedom from current-stop pressure with literal unanticipated transfer waits.'),encoding='utf8')
    p=COMMON/'check_loyalty_invariants.py';t=p.read_text(encoding='utf8')
    t=t.replace("assert policy.student_review_context(s,50.,pred)[0];checks.append('released_eligibility_survives_lower_wait_forecast')",
        "assert policy.student_review_context(s,50.,pred)[0]==(not c.get('review_requires_current_queue_pressure',False)) and s['student_flexible'];checks.append('mode_freedom_survives_while_short_queue_pressure_does_not')")
    p.write_text(t,encoding='utf8')
    save(COMMON/'candidate.json',{'release_id':stamp,'path':str(work),'parent':str(PARENT)})
    print(work,flush=True)
if __name__=='__main__':main()
