from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'261116122336';w=Path(json.loads((ROOT/'candidate.json').read_bytes())['path'])
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists(),p
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
old=ROOT.parent/'v12_current_pressure_20261116'
for name in ['run_cases.py','summarize_refinement.py','validate_behavior.py','diagnose_waits.py','stop_queue_exposure.py',
             'physical_components.py','class_end_journey_metrics.py','diagnose_gate_flow.py','gate_service_diagnosis.py',
             'check_legacy.py','check_loyalty_invariants.py']:
    p=ROOT/name;assert not p.exists();shutil.copy2(old/name,p)
p=ROOT/'check_legacy.py';t=p.read_text(encoding='utf8');assert "'test_current_pressure']" in t
p.write_text(t.replace("'test_current_pressure']","'test_current_pressure','test_direct_restoration']"),encoding='utf8')
save(ROOT/'execution-helpers-ready.json',{'created_at':datetime.now(timezone.utc).isoformat(),'release_id':w.name,'production_writes':False})
print('EXECUTION_HELPERS_READY',w.name)
