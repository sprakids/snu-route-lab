"""Finite read-only analysis of completed cases; no simulations or publication."""
from pathlib import Path
import argparse,subprocess,sys
ROOT=Path(__file__).resolve().parent
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve()
    jobs=[('summarize_refinement.py','grid-diagnostics.json',['--group','grid']),
        ('validate_behavior.py','grid-behavior-validation.json',['--group','grid']),
        ('diagnose_waits.py','grid-wait-cause-ledger.json',[]),('physical_components.py','mean-physical-components.csv',[]),
        ('class_end_journey_metrics.py','class-end-journey-comparison.csv',[]),('report_results.py','recommendation.json',[]),
        ('reconcile_outputs.py','export-reconciliation.json',[]),('verify_artifacts.py','artifact-verification.json',[]),
        ('write_handoff.py','START_HERE.md',[])]
    for name,target,extra in jobs:
        assert not (w/target).exists(),('Keep existing outputs',target)
        with (w/(name.replace('.py','')+'-analysis.log')).open('x',encoding='utf8') as output:
            done=subprocess.run([sys.executable,'-X','utf8',str(ROOT/name),str(w),*extra],stdout=output,stderr=subprocess.STDOUT,cwd=ROOT.parent.parent,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert done.returncode==0,(name,done.returncode)
        print('ANALYSIS_STEP_DONE',name,flush=True)
    print('ALL_ANALYSIS_COMPLETE',w.name,flush=True)
if __name__=='__main__':main()
