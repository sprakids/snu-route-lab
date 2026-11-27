from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,sys
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve();sys.path.insert(0,str(w))
    from run_case import code_manifest
    from artifacts import check_baseline
    check_baseline();runtime=code_manifest();names=list(runtime)+['config.json','experiment_lock.json','analyze_followup.py',
      'frozen/prepared_capacity44_pair.json.gz','frozen/empirical_evidence.json','frozen/operations_v12_empirical.json',
      'frozen/class_release_map.json.gz','frozen/class_endings_source_20261106.json']
    result={'release_id':w.name,'declared_at':datetime.now(timezone.utc).isoformat(),'new_outcome_raw_opened':False,
      'training_dates':['2026-11-10'],'already_explored_dates':['2026-11-11'],'queue_calibration_dates':['2026-11-09','2026-11-10'],
      'scope':'User-shaped behavioral scenario; no new numerical fit. All old queue observations reused, not holdout. New completed dates remain unopened.',
      'frozen_sha256':{n:sha(w/n) for n in names},'twenty_minutes_role':'Retained diagnostic; individual patience permits exceedances. Never force exit or delete mass.',
      'production_replacement_allowed':False}
    out=w/'future_evaluation_plan.json';assert not out.exists();out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print('FROZEN',len(names),len(runtime),'runtime modules')
if __name__=='__main__':main()
