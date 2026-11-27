"""Wait for the owned pilot, apply predeclared gates, and preserve every result."""
from pathlib import Path
import subprocess,sys,time
ROOT=Path(__file__).resolve().parent;w=Path(sys.argv[1]).resolve();log=w/'workflow.log';assert not log.exists()
def say(s):
    with log.open('a',encoding='utf8') as f:f.write(s+'\n')
    print(s,flush=True)
def run(name,*args,grid=False):
    suffix='-grid-analysis.log' if grid else '-analysis.log';p=w/(name.removesuffix('.py')+suffix);assert not p.exists()
    with p.open('x',encoding='utf8') as f:
        r=subprocess.run([sys.executable,'-X','utf8',str(ROOT/name),str(w),*args],stdout=f,stderr=subprocess.STDOUT)
    say(f'{name} EXIT {r.returncode}');return r.returncode
deadline=time.monotonic()+2400
while not (w/'pilot-validation.json').exists():
    assert not list((w/'runs').glob('*/attempt_01/failure.json')),'Inspect failure; preserve consumed condition'
    assert time.monotonic()<deadline
    time.sleep(10)
for name,args in [('summarize_refinement.py',['--group','pilot']),('validate_behavior.py',['--group','pilot']),
                  ('law_transfer_metrics.py',['--group','pilot']),('check_pilot.py',[])]:
    if run(name,*args):say('STOP_PRESERVE_PILOT_RESULTS');raise SystemExit(2)
say('PILOT_QUALIFIED_START_REMAINING_MAIN_CASES')
assert run('run_cases.py','grid')==0
for name in ['summarize_refinement.py','validate_behavior.py','diagnose_waits.py','stop_queue_exposure.py',
             'physical_components.py','class_end_journey_metrics.py','diagnose_gate_flow.py','gate_service_diagnosis.py','law_transfer_metrics.py']:
    args=['--group','grid'] if name in ('validate_behavior.py','law_transfer_metrics.py') else []
    assert run(name,*args,grid=True)==0
say('GRID_ANALYSIS_TABLES_COMPLETE')
