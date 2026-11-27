from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import sys,subprocess,argparse,time,json
from prepare_correction import SIM,HERE,prepare,read,base

def run(day,scenario):
    bundle=prepare();sys.path.insert(0,str(HERE))
    import engine
    engine.WORK=HERE;engine.OUT=HERE/'public_data';engine.OUT.mkdir(exist_ok=True);base.OUT=engine.OUT
    did=base.DAYS[day];start=HERE/f'started-{scenario}-{did}.json';assert not start.exists()
    sha=base.sha(HERE/'engine.py');base.save(start,{'model_sha256':sha,'prepared_sha256':base.sha(HERE/'prepared.json.gz')})
    t=time.perf_counter();result=engine.simulate(bundle,day,scenario)
    assert base.sha(HERE/'engine.py')==sha
    base.save(HERE/f'run-{scenario}-{did}.json',{'status':'PASS','model_sha256':sha,'elapsed_seconds':time.perf_counter()-t,'report':result['report']})

def all_runs():
    prepare();jobs=[(d,s) for s in ('regular','peak') for d in base.DAYS]
    # Start with Tuesday for the new field comparison, then the remaining days.
    jobs.sort(key=lambda ds:(ds[0]!='화',ds[1]!='peak'))
    def worker(case):
        d,s=case;did=base.DAYS[d];log=HERE/f'full-{s}-{did}.log';assert not log.exists()
        with log.open('w',encoding='utf8') as stream:
            r=subprocess.run([sys.executable,'-X','utf8',str(HERE/'run.py'),'--day',d,'--scenario',s],stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert r.returncode==0,(case,str(log));print('CAP44_COMPLETED',s,did,flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(worker,jobs))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--all',action='store_true');p.add_argument('--day',choices=list(base.DAYS));p.add_argument('--scenario',choices=['regular','peak']);a=p.parse_args()
    if a.all:all_runs()
    else:run(a.day,a.scenario)
