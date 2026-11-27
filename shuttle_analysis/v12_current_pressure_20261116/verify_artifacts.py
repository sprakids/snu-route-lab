"""Check physical source preservation, receipts, modes and live public assets."""
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
import sys,json,hashlib,gzip,re,importlib.util,math
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent/'261116010854'
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    w=Path(sys.argv[1]).resolve();out=w/'artifact-verification.json';assert not out.exists()
    m=read(w/'repair_manifest.json');future=read(w/'future_evaluation_plan.json');cfg=read(w/'config.json');lock=read(w/'experiment_lock.json');count=0
    for p,h in m['protected'].items():assert sha(Path(p))==h,p;count+=1
    for p,h in m['frozen_payloads'].items():assert sha(w/p)==h and sha(BASE/p)==h,p;count+=1
    for p,h in future['frozen_sha256'].items():assert sha(w/p)==h,p;count+=1
    protocol=read(w/'protocol-reference.json');assert sha(Path(protocol['path']))==protocol['sha256']
    frozen=read(w/'frozen/prepared_capacity44_pair.json.gz');expected={day:math.fsum(p[3] for p in plans if frozen['destination_keys'][str(p[0])] in ('snu','daehak')) for day,plans in frozen['prepared']['plans'].items()}
    grid=read(w/'grid-validation.json');before=read(BASE/'grid-validation.json')['results'];profiles=[]
    for case in lock['pilot_cases']:
        folder=w/'runs'/case['case']/'attempt_01';s=read(folder/'started.json');result=read(folder/'result.json')
        assert s['case']==case and result['status']=='COMPUTED_NOT_EMPIRICALLY_VALIDATED'
        assert s['experiment_lock_sha256']==sha(w/'experiment_lock.json') and s['input_manifest_sha256']==sha(w/'input_manifest.json')
        assert len(s['code_sha256'])==17
        for name,h in s['code_sha256'].items():assert sha(w/name)==sha(folder/'source_snapshot'/name)==h;count+=2
        effective={**cfg,'seed':case['seed'],'operations':case['operations'],**case.get('config_overrides',{}),'physics':'path_local_4p8','behavior':'sequential','boarding_choice':True,'origin_choice':True}
        assert effective==s['config']
        original=next(r for r in before if (r['case']['day'],r['case']['scenario'])==(case['day'],case['scenario']))
        old=read(Path(original['source_directory'])/'result.json')['policy_report']['student_strategy'];new=result['policy_report']['student_strategy']
        assert set(new['initial_mode_weights'])==set(old['initial_mode_weights'])
        for k,v in old['initial_mode_weights'].items():assert abs(v-new['initial_mode_weights'][k])<1e-6
        samples={r['uid']:r for r in old['patience_draw_sample']}
        for r in new['patience_draw_sample']:
            x=samples[r['uid']];assert r['mode']==x['mode'] and r['patience_seconds']==x['patience_seconds']
        checks=new.get('initial_trunk_checks',{})
        if effective.get('initial_trunk_preservation'):
            assert checks.get('violation_weight',0)==0
            assert abs(checks['checked_weight']-expected[case['day']])<1e-5,(case['case'],checks,expected[case['day']])
        profiles.append({'case':case['case'],'first_mode_mass_unchanged':True,'exact_patience_profiles':len(new['patience_draw_sample']),
                         'initial_trunk_checked_weight':checks.get('checked_weight'),'eligible_trunk_source_weight':expected[case['day']],
                         'initial_trunk_coverage_passed':abs(checks.get('checked_weight',0)-expected[case['day']])<1e-5 if effective.get('initial_trunk_preservation') else None})
    assert len(list((w/'runs').glob('*/attempt_*')))==len(lock['pilot_cases'])
    assert len(grid['results'])==10 and all(r['status']=='PASS_INTERNAL_INVARIANTS' for r in grid['results'])
    assert read(w/'grid-behavior-validation.json')['status']=='PASS_STUDENT_BEHAVIOR_GATES'
    assert read(w/'export-reconciliation.json')['status']=='PASS'
    assert read(w/'loyalty-invariant-check.json')['status']=='PASS'
    for name in ['prepare.py','physics.py','capacity.py','operations.py','empirical_v12.py','time_profiles.py','hazard.py','fares.py']:
        assert sha(w/name)==sha(BASE/name),name
    # New source fields are bookkeeping; all existing numerical assumptions stay.
    oldcfg=read(BASE/'config.json');numeric={k:v for k,v in oldcfg.items() if isinstance(v,(int,float)) and not isinstance(v,bool)}
    assert all(cfg[k]==v for k,v in numeric.items())
    units={}
    for n in ['enabled-final.log','legacy-final.log']:
        content=(w/n).read_text(encoding='utf8');matches=re.findall(r'Ran (\d+) tests?',content)
        assert len(matches)==1 and re.search(r'^OK\s*$',content,re.M)
        units[n]=int(matches[0])
    assert units=={'enabled-final.log':129,'legacy-final.log':89}
    assert read(w/'static-current-pressure-proof.json')['status']=='PASS_STATIC_CURRENT_PRESSURE_SCOPE'
    links=0
    for n in ['RESULTS.md','SOURCES_AND_ASSUMPTIONS.md']:
        for href in re.findall(r'\]\(([^)]+)\)',(w/n).read_text(encoding='utf8')):
            if href.startswith(('http://','https://','#')):continue
            assert (w/href).resolve().exists(),(n,href);links+=1
    script=ROOT.parent/'261112111627/verify_production_unchanged_v2.py';spec=importlib.util.spec_from_file_location('public_readback',script);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    lab='https://snu-shuttle-simulation.vercel.app/';release=f'routing-model/releases/{mod.MODEL}.json'
    jobs=[('lab_latest',lab+'routing-model/latest.json'),('lab_payload',lab+release),('data_payload','https://snu-shuttle-v9-data.vercel.app/'+release),('route_api','https://snu-route-lab.vercel.app/api/queue-model')]
    jobs +=[(n,lab+n) for n in ['index.html','viewer-v5.js','mobile-lab.js','mobile-lab.css']]
    with ThreadPoolExecutor(max_workers=4) as pool:public=list(pool.map(mod.fetch,jobs))
    assert all(r['check']=='PASS' for r in public),public
    value={'status':'PASS','release_id':w.name,'checked_at':datetime.now(timezone.utc).isoformat(),'hash_checks':count,
           'runtime_modules':17,'frozen_inputs':len(m['frozen_payloads']),'source_hashes_before_execution':len(future['frozen_sha256']),
           'single_attempt_cases':len(lock['pilot_cases']),'main_cases':10,'unit_tests':units,'supplemental_loyalty_guard_checks':5,
           'numerical_parameters_unchanged':numeric,'initial_profile_checks':profiles,'local_links':links,'public_readback':public,
           'production_model':mod.MODEL,'new_date_accuracy':'NOT_EVALUATED','operating_adoption_recommended':False,'production_writes':False}
    out.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print('ARTIFACT_VERIFICATION_PASS',count,units,flush=True)
if __name__=='__main__':main()
