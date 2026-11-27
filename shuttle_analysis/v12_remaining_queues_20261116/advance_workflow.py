"""Continue this authorized bounded experiment; never rerun a consumed group."""
from pathlib import Path
import json,subprocess,sys,time
ROOT=Path(__file__).resolve().parent;w=Path(sys.argv[1]).resolve()
log=w/'workflow.log';assert not log.exists()
def say(t):
    with log.open('a',encoding='utf8') as f:f.write(t+'\n')
    print(t,flush=True)
def run(name,*args):
    target=w/f'{name.removesuffix(".py")}-analysis.log'
    assert not target.exists(),target
    with target.open('x',encoding='utf8') as f:
        p=subprocess.run([sys.executable,'-X','utf8',str(ROOT/name),str(w),*args],stdout=f,stderr=subprocess.STDOUT)
    say(f'STEP {name} EXIT {p.returncode}')
    return p.returncode
deadline=time.monotonic()+2400
while not (w/'pilot-validation.json').exists():
    failures=list((w/'runs').glob('*/attempt_01/failure.json'))
    if failures:raise RuntimeError(str(failures))
    assert time.monotonic()<deadline,'Pilot wait expired; inspect existing process, do not duplicate'
    time.sleep(10)
for name,args in [('summarize_refinement.py',['--group','pilot']),('validate_behavior.py',['--group','pilot']),('check_pilot.py',[])]:
    code=run(name,*args)
    if code:
        say('STOP_PRESERVE_PILOT_RESULTS');raise SystemExit(code)
say('PILOT_QUALIFIED_START_REMAINING_MAIN_CASES')
assert run('run_cases.py','grid')==0
say('ALL_MAIN_MODEL_RUNS_COMPLETE')
for name in ['summarize_refinement.py','validate_behavior.py','diagnose_waits.py','stop_queue_exposure.py','physical_components.py','class_end_journey_metrics.py','diagnose_gate_flow.py','gate_service_diagnosis.py']:
    # The pilot and grid scripts have separate log names and separate outputs.
    path=w/f'{name.removesuffix(".py")}-analysis.log'
    if path.exists():
        target=w/f'{name.removesuffix(".py")}-grid-analysis.log';assert not target.exists()
        with target.open('x',encoding='utf8') as f:
            p=subprocess.run([sys.executable,'-X','utf8',str(ROOT/name),str(w),*(['--group','grid'] if name=='validate_behavior.py' else [])],stdout=f,stderr=subprocess.STDOUT)
        say(f'GRID_STEP {name} EXIT {p.returncode}');assert p.returncode==0
    else:assert run(name,*(['--group','grid'] if name=='validate_behavior.py' else []))==0
say('GRID_ANALYSIS_TABLES_COMPLETE')
