from concurrent.futures import ThreadPoolExecutor
import subprocess,sys
from artifacts import ROOT,read,save,sha
from run_case import code_manifest

def main():
    first=read(ROOT/'runs/baseline-combined-regular-mon/attempt_01/independent_analysis.json')
    assert first['status']=='PASS_INTERNAL_INVARIANTS' and first['over20_weight']==0
    assert not (ROOT/'operations-run-started.json').exists()
    jobs=read(ROOT/'experiment_lock.json')['pilot_cases'][1:];expected=code_manifest()
    save(ROOT/'operations-run-started.json',{'status':'STARTED','cases':jobs,'source_sha256':expected,'production_change_permitted':False})
    def worker(c):
        with (ROOT/(c['case']+'.log')).open('x',encoding='utf8') as stream:
            r=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'run_case.py'),c['case']],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert r.returncode==0,c['case'];assert read(ROOT/'runs'/c['case']/'attempt_01/result.json')['code_sha256']==expected
        print('OPERATIONS_CELL_DONE',c['case'],flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(worker,jobs))

if __name__=='__main__':main()
