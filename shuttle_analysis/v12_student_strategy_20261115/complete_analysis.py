"""Finite postprocessing only; never start or duplicate simulation cases."""
from pathlib import Path
import argparse,subprocess,sys,json,hashlib
ROOT=Path(__file__).resolve().parent
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve()
    jobs=[('diagnose_gate_flow.py','gate-flow-diagnosis-v2.json'),('diagnose_direction_repair.py','direction-repair-diagnosis.json'),('summarize_refinement.py','grid-diagnostics.json'),('validate_behavior.py','grid-behavior-validation.json'),
          ('wait_threshold_diagnosis.py','grid-wait-threshold-diagnosis.json'),('physical_components.py','mean-physical-components.csv'),
          ('class_end_journey_metrics.py','class-end-journey-comparison.csv'),('report.py','grid-recommendation.json'),
          ('reconcile_outputs.py','export-reconciliation.json'),('verify_final.py','grid-final-verification.json')]
    for name,target in jobs:
        if name=='diagnose_direction_repair.py' and (w/target).exists():
            proof=json.loads((w/target).read_bytes())
            for r in proof['cases']:assert hashlib.sha256(Path(r['source']).read_bytes()).hexdigest()==r['source_sha256']
            print('REUSE_VERIFIED_DIRECTION_DIAGNOSTIC',flush=True);continue
        assert not (w/target).exists(),('Preserve previous postprocessor outputs',target)
        args=[sys.executable,'-X','utf8',str(ROOT/name),str(w)]
        if name=='summarize_refinement.py':args+=['--group','grid']
        if name=='validate_behavior.py':args+=['--group','grid']
        done=subprocess.run(args,cwd=ROOT.parent.parent,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert done.returncode==0,(name,done.returncode)
    print('POSTPROCESSING_COMPLETE',w.name,flush=True)
if __name__=='__main__':main()
