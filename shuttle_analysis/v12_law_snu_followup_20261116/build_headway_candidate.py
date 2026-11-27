"""Isolate the user's clarified normal-headway / unseen-transfer-queue behavior."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parent;A=ROOT.parent;PARENT=A/'261116153200'
OUT=A/'v12_nominal_transfer_20261116'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists(),p
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def main():
    OUT.mkdir();stamp=datetime.now(timezone(timedelta(hours=9))).strftime('%y%m%d%H%M%S');w=A/stamp;w.mkdir()
    old=read(PARENT/'repair_manifest.json')
    for p in PARENT.glob('*.py'):shutil.copy2(p,w/p.name)
    for n in ['input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md']:shutil.copy2(PARENT/n,w/n)
    for n,h in old['frozen_payloads'].items():
        assert sha(PARENT/n)==h
        dest=w/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(PARENT/n,dest)
    for p in PARENT.glob('physical_paths_*.json.gz'):shutil.copy2(p,w/p.name)
    shutil.copy2(ROOT/'nominal_transfer.py',w/'nominal_transfer.py')
    cfg=read(PARENT/'config.json');cfg.update(release_id=stamp,version_family='V12-known-transfer-headway-unseen-queues',
        anticipated_transfer_headways=True,
        initial_primary_interpretation='Primary destination-service boarding time includes physical access and normal service-headway expectation at all preceding/current mainline boardings. Future transfer queues/capacity remain unseen; initial alternatives grouped once per actual primary stop. No downstream total-ETA tie-break.',
        consistent_perception_interpretation='User clarification2026-11-16: ordinary transfer headways are anticipated, future transfer queue/full buses are not. Current queue is causal as before. Initial and review costs use same exogenous service calendar expectation; physical forecasts unchanged.',
        direct_restoration_interpretation='Five known5511 direct policies restored as in parentG; no catalog/supply changes in this child.',
        transfer_headway_interpretation='Unknown-phase waiting=sum(h²)/(2sum(h)) from compatible exogenous calendar departures by arrival hour. If no local gap, use full-calendar gaps; not exact future phase or future realized loads. Retain20s existing preparation. No fitted coefficients.')
    save(w/'config.json',cfg)
    p=w/'policy.py';t=p.read_text(encoding='utf8')
    needle="    evidence=bundle.get('empirical_evidence')\n";assert t.count(needle)==1
    t=t.replace(needle,"    from nominal_transfer import NominalTransfers\n    nominal_transfers=NominalTransfers(schedule,vehicles,node_for,config)\n"+needle)
    needle="                return perceived_without_transfer_wait(pred) if pred is not None else None\n";assert t.count(needle)==1
    t=t.replace(needle,"                if pred is None:return None\n                if config.get('anticipated_transfer_headways'):\n                    stages=args[0] if args else kwargs['stages']\n                    return nominal_transfers.outlook(pred,stages)\n                return perceived_without_transfer_wait(pred)\n")
    needle="            return self.predict(*args,**kwargs)\n";assert t.count(needle)==1
    t=t.replace(needle,needle+"        def nominal_transfer_report(self):return nominal_transfers.report()\n")
    p.write_text(t,encoding='utf8')
    p=w/'behavioral_policy.py';t=p.read_text(encoding='utf8')
    needle="    arrival_cache={};frequency_cache={};initial_stops=Counter();initial_samples=[];same_stop_updates=[];trunk_checks=Counter();primary_cache={};primary_stops=Counter()\n";assert t.count(needle)==1
    t=t.replace(needle,needle+"    from nominal_transfer import NominalTransfers\n    nominal_transfers=NominalTransfers(schedule,vehicles,node_for,config)\n")
    needle="                extension=primary_access_extension(pred,source['primary_node']);score+=extension\n                if info is not None:info={**info,'primary_access_after_first_boarding_seconds':extension,'future_transfer_wait_anticipated':False}\n";assert t.count(needle)==1
    t=t.replace(needle,"                extension=primary_access_extension(pred,source['primary_node']);nominal_details=()\n                if config.get('anticipated_transfer_headways'):\n                    extension,nominal_details=nominal_transfers.primary_extension(pred,chain,source['primary_node'],extension)\n                score+=extension\n                if info is not None:info={**info,'primary_access_after_first_boarding_seconds':extension,\n                    'future_transfer_wait_anticipated':bool(config.get('anticipated_transfer_headways')),\n                    'transfer_headway_references':nominal_details,'future_transfer_queue_anticipated':False}\n")
    t=t.replace("'restored_direct':any(e.get('known_direct_policy_restored')", "'reference':c[6],'restored_direct':any(e.get('known_direct_policy_restored')")
    needle="        r=raw_report();r['catalog_repair']=";assert t.count(needle)==1
    t=t.replace(needle,"        r=raw_report();r['nominal_transfer_initial']=nominal_transfers.report();r['nominal_transfer_review']=policy.nominal_transfer_report();r['catalog_repair']=")
    t=t.replace("'initial_primary_information':'First boarding delay and physical prefix access; no anticipation of transfer waiting. Actual queues/boarding capacity and subsequent reviews are unchanged.'", "'initial_primary_information':config['initial_primary_interpretation']")
    p.write_text(t,encoding='utf8')
    p=w/'run_case.py';t=p.read_text(encoding='utf8');needle="'direct_restoration.py','run_case.py'";assert needle in t
    p.write_text(t.replace(needle,"'direct_restoration.py','nominal_transfer.py','run_case.py'"),encoding='utf8')
    # Parent tests explicitly exercise the old zero-transfer-wait branch; new
    # independent tests cover the enabled clarified behavior.
    p=w/'test_student_strategy.py';t=p.read_text(encoding='utf8');needle="c=read(ROOT/'config.json');b=fixture([('A',1,100)],c)";assert t.count(needle)==1
    p.write_text(t.replace(needle,"c=read(ROOT/'config.json');c['anticipated_transfer_headways']=False;b=fixture([('A',1,100)],c)"),encoding='utf8')
    days=[('월','mon'),('화','tue'),('수','wed'),('목','thu'),('금','fri')]
    cases=[{'case':f'headway-combined-{sc}-{eng}','mode':'combined','day':day,'scenario':sc,'seed':0,'operations':'v12_empirical'} for sc in ['regular','peak'] for day,eng in days]
    cases.append({'case':'ablation-no-transfer-headway-tue','mode':'combined','day':'화','scenario':'regular','seed':0,'operations':'v12_empirical',
        'config_overrides':{'anticipated_transfer_headways':False}})
    save(w/'experiment_lock.json',{'status':'REGISTERED_BEFORE_EXECUTION','release_id':stamp,'implementation_parent':str(PARENT),
        'comparison_parent':PARENT.name,'broader_reference':'261116010854','pilot_cases':cases,
        'selection_rule':'MainMonday/Tuesday regular plus disabledTuesday once each. Require physical/user/data invariants, no unserved, exact disabled parent reproduction, nonworsening all-recorded over20 sum, maximum wait, each-day mean journey, reused field-error sum, gate error, and afternoon law max; strict decrease over20 and SNU prior-bus law arrivals. Only then extend remaining8 main. No numeric fit; no new-date outcome reads.',
        'user_clarification':'Normal transfer headways anticipated; transfer queue/full buses not anticipated.',
        'new_day_outcomes_opened':False,'production_replacement_allowed':False,
        'retained_user_behavior':read(PARENT/'experiment_lock.json')['retained_user_behavior']})
    protect=old['protected'].copy()
    for p in PARENT.iterdir():
        if p.is_file():protect[str(p)]=sha(p)
    save(w/'repair_manifest.json',{'parent':str(PARENT),'comparison_parent':PARENT.name,'release_id':stamp,'protected':protect,
        'frozen_payloads':old['frozen_payloads'],'config_sha256':sha(w/'config.json'),'production_writes':False})
    save(OUT/'candidate.json',{'release_id':stamp,'path':str(w),'parent':PARENT.name})
    for n in ['run_cases.py','summarize_refinement.py','validate_behavior.py','diagnose_waits.py','stop_queue_exposure.py',
              'physical_components.py','class_end_journey_metrics.py','diagnose_gate_flow.py','gate_service_diagnosis.py',
              'check_legacy.py','check_loyalty_invariants.py','law_transfer_metrics.py','check_pilot.py','advance_workflow.py']:
        shutil.copy2(ROOT/n,OUT/n)
    for n in ['law_transfer_metrics.py','check_pilot.py']:
        p=OUT/n;t=p.read_text(encoding='utf8').replace('261116122336','261116153200')
        if n=='check_pilot.py':t=t.replace("'wait_or_field_strict_improvement':o1<o0-1e-7 or e1<e0-1e-7","'over20_strict_improvement':o1<o0-1e-7")
        p.write_text(t,encoding='utf8')
    p=OUT/'check_legacy.py';t=p.read_text(encoding='utf8').replace("'test_direct_restoration']","'test_direct_restoration','test_nominal_transfer']");p.write_text(t,encoding='utf8')
    print(w,flush=True)
if __name__=='__main__':main()
