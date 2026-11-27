"""Complete all H cases using the same frozen behavior engine, then reconcile."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess,sys
import capacity_model as base
import walk_choice_model as model
import refit_walk_choice_gate as trial
import analyze_walk_choices as analysis
import verify_walk_choice_core as core
import finish_walk_choices as finish

def verify(bundle):
    analysis.WORK=trial.WORK;analysis.prepare=lambda:bundle
    core.WORK=trial.WORK;core.OUT=trial.WORK/'public_data'
    finish.WORK=trial.WORK
    finish.RULE={**finish.RULE,'initial_gate_refit':bundle['initial_gate_refit']}
    finish.verify_all(bundle,base.sha(Path(model.__file__)),field_tolerance=.5)

def main():
    bundle=trial.prepare();expected=base.sha(Path(model.__file__))
    jobs=[(s,d,code) for s in ('peak','regular') for d,code in base.DAYS.items()]
    def worker(case):
        scenario,day,did=case;receipt=trial.WORK/f'run-{scenario}-{did}.json'
        if receipt.exists():
            assert trial.read(receipt)['status']=='PASS' and trial.read(receipt)['model_sha256']==expected
            print('REUSED',scenario,did,flush=True);return
        log=trial.WORK/f'full-{scenario}-{did}.log';assert not log.exists(),f'Inspect incomplete run: {log}'
        with log.open('w',encoding='utf8') as stream:
            run=subprocess.run([sys.executable,'-X','utf8',str(trial.ROOT/'refit_walk_choice_gate.py'),'--day',day,'--scenario',scenario],stdout=stream,stderr=subprocess.STDOUT,
                               creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert run.returncode==0,(case,str(log));assert trial.read(receipt)['model_sha256']==expected
        print('COMPLETED',scenario,did,flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(worker,jobs))
    verify(bundle)

if __name__=='__main__':main()
