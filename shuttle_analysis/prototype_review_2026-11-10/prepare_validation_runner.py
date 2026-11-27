"""Freeze a fresh runner and diagnostic extension for the validated R7 parent."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parent
PARENT=ROOT.parent/'prototype_followup_261110181553'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    work=Path(read(PARENT/'weekday_validation.json')['directory'])
    target=work/'run_validation.py';assert not target.exists()
    source=ROOT.parent/'prototype_validation_261110174114/run_validation.py'
    s=source.read_text(encoding='utf8')
    s=s.replace('import analyze_followup as independent','import analyze_followup as independent\nfrom validation_metrics import diagnostics',1)
    old="    result.update(unserved_trip_weight=data['report']['unserved_trip_weight'],late_finished_weight=data['report']['late_arrival_weight'],"
    assert old in s
    s=s.replace(old,"    result['extended_diagnostics']=diagnostics(audit,START,END)\n"+old,1)
    old="    assert ref['status']=='PASS_INTERNAL_INVARIANTS' and ref['over20_weight']==0"
    assert old in s
    s=s.replace(old,old+"\n    assert ref['case']==lock['reused_case']['case']\n    assert receipt['experiment_lock_sha256']==sha(parent/'experiment_lock.json')\n    for p in (parent/'frozen').rglob('*'):\n        if p.is_file():assert sha(p)==sha(ROOT/'frozen'/p.relative_to(parent/'frozen'))",1)
    target.write_text(s,encoding='utf8');shutil.copy2(ROOT/'validation_metrics.py',work/'validation_metrics.py')
    (work/'runner_manifest.json').write_text(json.dumps({'source':str(source),'source_sha256':sha(source),
        'runner_sha256':sha(target),'metrics_sha256':sha(work/'validation_metrics.py'),
        'changes':'Read-only extra quantiles/all-recorded wait metrics and strengthened reference/frozen-file guards; no simulation code changes.',
        'production_replacement_allowed':False},ensure_ascii=False,indent=2),encoding='utf8')
    print(work)
if __name__=='__main__':main()
