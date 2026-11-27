"""Finish the fixed pilot table with two workers; do not duplicate owned runs."""
from concurrent.futures import ThreadPoolExecutor
import subprocess,sys
from artifacts import ROOT,read
from run_case import code_manifest

def main():
    jobs=read(ROOT/'experiment_lock.json')['pilot_cases'];expected=code_manifest()
    def worker(case):
        work=ROOT/'runs'/case['case']/'attempt_04';result=work/'result.json'
        if result.exists():
            receipt=read(result);assert receipt['code_sha256']==expected
            print('REUSED',case['case'],flush=True);return
        if (work/'started.json').exists():
            assert not (work/'failure.json').exists(),str(work)
            print('EXISTING_OWNED_RUN',case['case'],flush=True);return
        log=ROOT/('final-'+case['case']+'.log');assert not log.exists()
        with log.open('w',encoding='utf8') as stream:
            r=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'run_case.py'),case['case'],'--attempt','4'],stdout=stream,stderr=subprocess.STDOUT,
                             creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert r.returncode==0,(case['case'],str(log));assert read(result)['code_sha256']==expected
        print('COMPLETED',case['case'],flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(worker,jobs))

if __name__=='__main__':main()
