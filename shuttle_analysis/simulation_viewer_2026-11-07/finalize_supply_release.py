"""Record already verified public promotions and align local mutable pointers."""
from pathlib import Path
from datetime import datetime
import json,hashlib,shutil

ROOT=Path(__file__).resolve().parent;WORK=ROOT/'peak_pair_correction_2026-11-10'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    m=read(WORK/'pending_release.json');pending=ROOT/m['directory']
    for name in ('data-public-verification.json','ui-public-verification.json','app-public-new-verification.json'):
        v=read(WORK/name);assert v['status']=='PASS' and v.get('routing_model_id',v.get('model_id'))==m['model_id']
    assert read(WORK/'independent_verification.json')['status']=='PASS'
    backup=ROOT/'deployment/releases/pre_supply_v11_20261110';assert not backup.exists();backup.mkdir()
    for source in (ROOT/'deployment/release.json',ROOT/'deployment/queue_source.json',ROOT/'public/routing-model/latest.json'):
        shutil.copy2(source,backup/source.name)
    target=ROOT/'public'/m['payload_path'].lstrip('/');target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():assert sha(target)==m['sha256']
    else:shutil.copy2(pending/'payload.json',target)
    assert sha(target)==m['sha256']
    temp=ROOT/'public/routing-model/latest.supply-verified.tmp';shutil.copy2(pending/'latest.json',temp);temp.replace(ROOT/'public/routing-model/latest.json')
    save(ROOT/'deployment/queue_source.json',{'model_directory':'peak_pair_correction_2026-11-10','simulation_version':'capacity_v11','adapter':'audited_v5_fifo'})
    scientific=read(WORK/'independent_verification.json');app=read(WORK/'app-public-new-verification.json')
    result={'status':'DEPLOYED_AND_VERIFIED','release_model_id':m['model_id'],'source_simulation':'capacity_v11',
        'site':'https://snu-shuttle-simulation.vercel.app/','methodology':'https://snu-shuttle-simulation.vercel.app/capacity-correction.html',
        'deployment_id':'dpl_9LoRQhFDGJikC6NNxEGRGb6L9RnR','data_deployment_id':'dpl_21reSLbatDSWc1ZQ84XC1wznoKnG',
        'app_deployment_id':'dpl_ETo1p8ipPum7PKCtnqf4EPNYfeQi','payload_sha256':m['sha256'],'compatibility_sha256':m['compatibility_sha256'],
        'content_sha256':m['content_sha256'],'behavior_parent':'capacity_v9','only_declared_supply_corrections_applied':True,
        'new_prototype_algorithm_applied':False,'data_stage':read(WORK/'data-stage.json'),'ui_stage':read(WORK/'ui-stage.json'),
        'scenario_runs':10,'capacity_only_comparison_runs':10,'stop_scenario_day_rows':990,
        **scientific['all_stop_review'],'no_count_limit':True,'no_forced_wait_or_queue_clipping':True,
        'public_file_parity_checks':42,'data_file_parity_checks':32,'desktop_and_mobile_checks':78,
        'browser_qa':'C:/Users/김예준/AppData/Local/Temp/snu-walk-choice-20261110/supply-public/checks.json',
        'route_application_active_model':app['model_id'],'route_application_capacity':app['average_capacity_assumption'],
        'route_manual_scenario_two_separate_vehicles':True,'independent_empirical_validation':False,
        'weighted_trip_events_not_unique_students':True,'field_1523_pair_fit_improved':False,
        'capacity44_source':'user correction, registration not independently verified',
        'pair_source':'reported repeated experience and common testimony; exact headway and peak boundaries unverified',
        'peak_window_seconds':[54000,68400],'window_is_assumed':True,'night60_is_legacy_unverified_assumption':True,
        'implementation_agent_notified':True,'recorded_local_time':datetime.now().isoformat()}
    save(ROOT/'deployment/release.json',result);save(WORK/'release.json',result)
    print(json.dumps({'status':result['status'],'model_id':m['model_id'],'local_and_public_pointer_aligned':True}))

if __name__=='__main__':main()
