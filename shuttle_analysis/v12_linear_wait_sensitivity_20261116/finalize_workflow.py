"""Finalize completed runs only; a rejected pilot never launches another case."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,importlib.util,json,subprocess,sys,time
ROOT=Path(__file__).resolve().parent
w=ROOT.parent/'261116120358'
log=ROOT/'finalization.log'
assert not log.exists()
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def say(s):
    with log.open('a',encoding='utf8') as f:f.write(s+'\n')
    print(s,flush=True)
def run(name,*args):
    dest=ROOT/(name.removesuffix('.py')+'-finalization.log')
    assert not dest.exists()
    with dest.open('x',encoding='utf8') as f:
        result=subprocess.run([sys.executable,'-X','utf8',str(ROOT/name),*args],stdout=f,stderr=subprocess.STDOUT)
    say(f'{name} EXIT {result.returncode}')
    assert result.returncode==0,(name,result.returncode)
deadline=time.monotonic()+3600
while True:
    state=(w/'workflow.log').read_text(encoding='utf8') if (w/'workflow.log').exists() else ''
    if 'STOP_PRESERVE_PILOT_RESULTS' in state or 'GRID_ANALYSIS_TABLES_COMPLETE' in state:break
    failures=list((w/'runs').glob('*/attempt_01/failure.json'))
    assert not failures,failures
    assert time.monotonic()<deadline,'Inspect running workflow; do not relaunch a model'
    time.sleep(10)
decision=read(w/'pilot-decision.json')
if decision['status']=='PILOT_QUALIFIED':
    assert 'GRID_ANALYSIS_TABLES_COMPLETE' in state
    run('report_results.py',str(w))
    sources=(ROOT/'SOURCES_AND_ASSUMPTIONS.md').read_text(encoding='utf8')
    sources=sources.replace('[최종 비교](FINAL_REVIEW.md)','[최종 후보 상세 결과](RESULTS.md)')
    out=w/'SOURCES_AND_ASSUMPTIONS.md';assert not out.exists();out.write_text(sources,encoding='utf8')
    run('reconcile_outputs.py',str(w))
    run('verify_artifacts.py',str(w))
else:
    say('REJECTED_PILOT_PRESERVED_NO_GRID')
    v=read(w/'pilot-validation.json');assert len(v['results'])==2
    assert read(w/'pilot-behavior-validation.json')['status']=='PASS_STUDENT_BEHAVIOR_GATES'
    manifest=read(w/'repair_manifest.json')
    for p,digest in manifest['protected'].items():assert sha(Path(p))==digest,p
    for p,digest in manifest['frozen_payloads'].items():assert sha(w/p)==digest,p
    for p,digest in read(w/'future_evaluation_plan.json')['frozen_sha256'].items():assert sha(w/p)==digest,p
    protocol=read(w/'protocol-reference.json');assert sha(Path(protocol['path']))==protocol['sha256']
    previous=read(ROOT.parent/'261116105704/grid-validation.json')['results'];profiles=[]
    for row in v['results']:
        case=row['case'];folder=Path(row['source_directory']);started=read(folder/'started.json');result=read(folder/'result.json')
        assert row['status']=='PASS_INTERNAL_INVARIANTS' and row['unserved_trip_weight']<1e-7
        assert sha(folder/f"audit-{case['scenario']}-{'mon' if case['day']=='월' else 'tue'}.json.gz")==row['audit_sha256']
        assert started['experiment_lock_sha256']==sha(w/'experiment_lock.json')
        assert started['input_manifest_sha256']==sha(w/'input_manifest.json')
        assert len(started['code_sha256'])==17
        for name,digest in started['code_sha256'].items():assert sha(w/name)==sha(folder/'source_snapshot'/name)==digest
        ref=next(r for r in previous if (r['case']['day'],r['case']['scenario'])==(case['day'],case['scenario']))
        a=read(Path(ref['source_directory'])/'result.json')['policy_report']['student_strategy']
        b=result['policy_report']['student_strategy']
        assert set(a['initial_mode_weights'])==set(b['initial_mode_weights'])
        assert all(abs(value-b['initial_mode_weights'][key])<1e-6 for key,value in a['initial_mode_weights'].items())
        assert a['patience_draw_sample']==b['patience_draw_sample']
        profiles.append({'case':case['case'],'first_mode_mass_unchanged':True,'exact_patience_profiles':len(b['patience_draw_sample'])})
    assert len(list((w/'runs').glob('*/attempt_*')))==2
    assert read(w/'enabled-unit-receipt.json')['status']=='PASS'
    assert read(w/'static-sensitivity-proof.json')['status']=='PASS_STATIC_SENSITIVITY_SCOPE'
    out=w/'pilot-final-verification.json';assert not out.exists()
    out.write_text(json.dumps({'status':'PASS_RESULT_INTEGRITY_NOT_ACCEPTANCE','checked_at':datetime.now(timezone.utc).isoformat(),
        'main_cases':2,'not_executed_remaining_main_cases':8,'runtime_modules':17,'protected_files':len(manifest['protected']),
        'frozen_inputs':len(manifest['frozen_payloads']),'initial_profile_checks':profiles,
        'unit_tests':{'active':128,'legacy':89,'loyalty_guards':5},'new_date_accuracy':'NOT_EVALUATED',
        'operating_adoption_recommended':False,'production_writes':False},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    say('PILOT_RESULT_INTEGRITY_VERIFIED')
run('build_final_review.py')
names=['FINAL_REVIEW.md','SOURCES_AND_ASSUMPTIONS.md','experiment-review.json']
out=ROOT/'handoff-manifest.json';assert not out.exists()
out.write_text(json.dumps({'created_at':datetime.now(timezone.utc).isoformat(),
    'document_sha256':{n:sha(ROOT/n) for n in names},'analysis_script_sha256':{p.name:sha(p) for p in ROOT.glob('*.py')},
    'new_date_accuracy':'NOT_EVALUATED','operating_adoption_recommended':False,'production_writes':False},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
say('FINAL_REVIEW_AND_HANDOFF_COMPLETE')
