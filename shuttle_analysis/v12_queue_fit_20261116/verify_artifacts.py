"""Verify immutable cases, fixed demand/supply and live V11 without publishing."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import argparse,ast,hashlib,importlib.util,json,math,re
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent/'261115160710'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve();out=w/'artifact-verification.json';assert not out.exists();count=0
    m=read(w/'repair_manifest.json');future=read(w/'future_evaluation_plan.json');lock=read(w/'experiment_lock.json');cfg=read(w/'config.json')
    for name,digest in m['protected'].items():assert sha(Path(name))==digest,name;count+=1
    for name,digest in m['frozen_payloads'].items():assert sha(w/name)==digest==sha(BASE/name),name;count+=1
    for name,digest in future['frozen_sha256'].items():assert sha(w/name)==digest,name;count+=1
    for path in w.glob('physical_paths_*.json.gz'):assert sha(path)==sha(BASE/path.name);count+=1
    def initial_ast(folder):
        tree=ast.parse((folder/'behavioral_policy.py').read_text(encoding='utf8'))
        return ast.dump(next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='initialize'),include_attributes=False)
    assert initial_ast(w)==initial_ast(BASE) and sha(w/'prepare.py')==sha(BASE/'prepare.py')
    oldrows=read(BASE/'grid-validation.json')['results'];profiles=[]
    for case in lock['pilot_cases']:
        folder=w/'runs'/case['case']/'attempt_01';started=read(folder/'started.json');result=read(folder/'result.json');receipt=read(folder/'repair_analysis.json')
        assert receipt['status']=='PASS_INTERNAL_INVARIANTS' and receipt['case']==case and result['case']==case
        assert started['experiment_lock_sha256']==sha(w/'experiment_lock.json') and started['input_manifest_sha256']==sha(w/'input_manifest.json')
        for name,digest in started['code_sha256'].items():assert sha(w/name)==digest==sha(folder/'source_snapshot'/name);count+=1
        effective={**cfg,'seed':case['seed'],'operations':case['operations'],**case.get('config_overrides',{})}
        effective.update(physics='path_local_4p8',behavior='sequential',boarding_choice=True,origin_choice=True)
        assert started['config']==effective and effective['student_strategy'] is True
        old=next(r for r in oldrows if r['case']['day']==case['day'] and r['case']['scenario']==case['scenario'])
        original=read(Path(old['source_directory'])/'result.json')['policy_report']['student_strategy'];current=result['policy_report']['student_strategy']
        assert set(current['initial_mode_weights'])==set(original['initial_mode_weights'])
        for mode,v in current['initial_mode_weights'].items():assert abs(v-original['initial_mode_weights'][mode])<1e-6
        before={x['uid']:x for x in original['patience_draw_sample']};checked=0
        for x in current['patience_draw_sample']:
            y=before[x['uid']];assert x['mode']==y['mode']
            z0=math.log(y['patience_seconds']/1200.)/.25;z1=math.log(x['patience_seconds']/1200.)/effective['patience_log_sigma'];assert abs(z0-z1)<1e-8;checked+=1
        profiles.append({'case':case['case'],'unchanged_initial_mode_masses':True,'same_underlying_patience_draws_checked':checked})
    assert len(list((w/'runs').glob('*/attempt_*')))==len(lock['pilot_cases'])==12
    validation=read(w/'grid-validation.json');behavior=read(w/'grid-behavior-validation.json');rec=read(w/'recommendation.json');exports=read(w/'export-reconciliation.json')
    assert len(validation['results'])==10 and behavior['status']=='PASS_STUDENT_BEHAVIOR_GATES' and exports['status']=='PASS'
    assert sha(w/'RESULTS.md')==rec['report_sha256'];links=0
    for name in ['RESULTS.md','SOURCES_AND_ASSUMPTIONS.md']:
        for href in re.findall(r'\]\(([^)]+)\)',(w/name).read_text(encoding='utf8')):
            if href.startswith(('http://','https://','#')):continue
            assert (w/href).resolve().exists(),(name,href);links+=1
    units={}
    for name,label in [('enabled-final.log','enabled_behavior_and_enroute'),('legacy-final.log','legacy_components_strategy_disabled')]:
        text=(w/name).read_text(encoding='utf8');n=re.findall(r'Ran (\d+) tests?',text);assert len(n)==1 and re.search(r'^OK\s*$',text,re.M);units[label]=int(n[0])
    units['total']=sum(units.values());guard=read(w/'loyalty-invariant-check.json');assert guard['status']=='PASS'
    script=ROOT.parent/'261112111627/verify_production_unchanged_v2.py';spec=importlib.util.spec_from_file_location('readback',script);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    lab='https://snu-shuttle-simulation.vercel.app/';release=f'routing-model/releases/{old.MODEL}.json'
    jobs=[('lab_latest',lab+'routing-model/latest.json'),('lab_payload',lab+release),('data_payload','https://snu-shuttle-v9-data.vercel.app/'+release),('route_api','https://snu-route-lab.vercel.app/api/queue-model')]
    jobs +=[(name,lab+name) for name in ['index.html','viewer-v5.js','mobile-lab.js','mobile-lab.css']]
    with ThreadPoolExecutor(max_workers=4) as pool:responses=list(pool.map(old.fetch,jobs))
    status='PASS' if all(r['check']=='PASS' for r in responses) else 'PUBLIC_READBACK_FAILURE'
    output={'status':status,'scope':'Artifact, user-rule guard and production preservation verification; not independent field accuracy or deployment readiness','release_id':w.name,
        'checked_at':datetime.now(timezone.utc).isoformat(),'main_cases':10,'registered_ablation_cases':2,'single_attempts':12,'runtime_modules':len(validation['source_sha256']),
        'future_hashes':len(future['frozen_sha256']),'frozen_input_files':len(m['frozen_payloads']),'hash_checks':count,'unit_tests':units,'supplemental_loyalty_guard_checks':len(guard['checks']),
        'behavior_gate':behavior['status'],'birth_modes_and_patience_randomness':profiles,'local_links':links,'production_model':old.MODEL,'public_readback':responses,
        'private_revision_fit_improved':rec['private_revision_fit_improved'],'operating_adoption_recommended':False,'new_date_accuracy':'NOT_EVALUATED','production_writes':False}
    out.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8');assert status=='PASS';print('ARTIFACTS_VERIFIED',count,'hashes',units,flush=True)
if __name__=='__main__':main()
