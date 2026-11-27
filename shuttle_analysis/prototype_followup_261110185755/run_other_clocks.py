"""Complete the two pre-registered remaining Monday clock comparisons once."""
import subprocess,sys
import analyze_followup as independent
from artifacts import ROOT,read,check_baseline,save
from run_case import code_manifest
def main():
    marker=ROOT/'other-clocks-started.json';assert not marker.exists()
    cases=[c for c in read(ROOT/'experiment_lock.json')['pilot_cases'] if c['operations']!='distribution_v8']
    assert len(cases)==2
    save(marker,{'cases':cases,'runtime_sha256':code_manifest(),'production_allowed':False})
    frozen=read(ROOT/'frozen/prepared_capacity44_pair.json.gz')
    for c in cases:
        work=ROOT/'runs'/c['case']/'attempt_01';assert not work.exists()
        with (ROOT/(c['case']+'.log')).open('x',encoding='utf8') as f:
            done=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'run_case.py'),c['case']],cwd=ROOT,
                stdout=f,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert done.returncode==0,(c,done.returncode)
        r=independent.verify(c,work,frozen);check_baseline()
        print('CLOCK_CELL_COMPLETE',c['case'],r['maximum_continuous_wait_min'],r['over20_weight'],flush=True)
    independent.main(resume=True)
if __name__=='__main__':main()
