"""One finite six-cell pilot; original runs and the operational release are read-only."""
from concurrent.futures import ThreadPoolExecutor
import subprocess,sys
from artifacts import ROOT,read,save,sha,check_baseline
from run_case import code_manifest

def main():
    marker=ROOT/'pilot-run-started.json';assert not marker.exists(),'Inspect preserved run ownership before restarting'
    assert read(ROOT/'preflight.json')['status']=='PASS'
    assert 'OK' in (ROOT/'boundary-tests-retry1.log').read_text(encoding='utf8')
    check_baseline();expected=code_manifest();lock=read(ROOT/'experiment_lock.json')
    save(marker,{'status':'STARTED','experiment_id':lock['experiment_id'],'cases':lock['pilot_cases'],
        'code_sha256':expected,'config_sha256':sha(ROOT/'config.json'),'lock_sha256':sha(ROOT/'experiment_lock.json'),
        'operational_replacement_forbidden_without_user_approval':True,
        'extra_pre_run_numerical_guard':'No useful action => no reconsideration timer; cubic age hazard saturates continuously at30min to avoid an unbounded event rate. No forced exit.'})
    def worker(case):
        log=ROOT/(case['case']+'.log');assert not log.exists()
        with log.open('w',encoding='utf8') as stream:
            done=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'run_case.py'),case['case']],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert done.returncode==0,(case['case'],str(log));result=read(ROOT/'runs'/case['case']/'attempt_01/result.json')
        assert result['code_sha256']==expected;print('FOLLOWUP_CELL_DONE',case['case'],result['elapsed_seconds'],flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(worker,lock['pilot_cases']))
    check_baseline();save(ROOT/'pilot-completion.json',{'status':'COMPUTED_NOT_VALIDATED','cells':len(lock['pilot_cases']),'code_sha256':expected,
        'config_sha256':sha(ROOT/'config.json'),'production_changed':False})

if __name__=='__main__':main()
