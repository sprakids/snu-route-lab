"""Finish analysis of preserved runs without expanding the known clock issue."""
from pathlib import Path
import json,subprocess,sys,time
ROOT=Path(__file__).resolve().parent;w=Path(json.loads((ROOT/'candidate.json').read_bytes())['path'])
assert (w/'EXTENSION_BLOCKED.md').exists();deadline=time.monotonic()+1800
while not (w/'pilot-validation.json').exists():
    assert time.monotonic()<deadline
    assert not list((w/'runs').glob('*/attempt_01/failure.json'))
    time.sleep(5)
for name,args in [('summarize_refinement.py',['--group','pilot']),('validate_behavior.py',['--group','pilot']),
                  ('law_transfer_metrics.py',['--group','pilot']),('check_pilot.py',[])]:
    out=w/(name.removesuffix('.py')+'-analysis.log');assert not out.exists()
    with out.open('x',encoding='utf8') as f:r=subprocess.run([sys.executable,'-X','utf8',str(ROOT/name),str(w),*args],stdout=f,stderr=subprocess.STDOUT)
    assert r.returncode==0 or (name=='check_pilot.py' and r.returncode==2)
    print(name,r.returncode,flush=True)
out=w/'workflow.log';assert not out.exists();out.write_text('KNOWN_INITIAL_ANCHOR_ISSUE_EXTENSION_BLOCKED\nSTOP_PRESERVE_PILOT_RESULTS\n',encoding='utf8')
print('BLOCKED_PILOT_ANALYSIS_COMPLETE',flush=True)
