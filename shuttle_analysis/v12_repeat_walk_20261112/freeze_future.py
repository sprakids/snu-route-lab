"""Freeze prospective evaluation before any new observation outcomes are opened."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import argparse,hashlib,json
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');args=p.parse_args();work=Path(args.candidate).resolve()
    source_path=next(work/name for name in ('observations-started.json','grid-started.json') if (work/name).exists())
    source=json.loads(source_path.read_bytes())
    files=list(source['runtime_sha256'])+['config.json','experiment_lock.json','frozen/prepared_capacity44_pair.json.gz',
      'frozen/empirical_evidence.json','frozen/operations_v12_empirical.json']
    if (work/'frozen/class_release_map.json.gz').exists():
        files+=['analyze_followup.py','frozen/class_release_map.json.gz','frozen/class_endings_source_20261106.json']
    result={'release_id':work.name,'declared_at':datetime.now(timezone(timedelta(hours=9))).isoformat(),
      'new_outcome_raw_opened':False,'training_dates':['2026-11-10'],
      'training_dates_scope':'Vehicle segment, headway and categorical grade input fitting only; queue calibration use is separately declared.',
      'queue_calibration_dates':['2026-11-09','2026-11-10'] if 'cohort_release_lag_scale' in json.loads((work/'config.json').read_bytes()) else [],
      'queue_calibration_date_note':'Monday report date inferred from conversation; all reports previously reused, no pristine holdout.',
      'already_explored_dates':['2026-11-11'],
      'first_eligible_completed_date':'2026-11-12','earliest_evaluation_at':'2026-11-13T00:00:00+09:00',
      'frozen_sha256':{name:sha(work/name) for name in files},'evaluation_rules':[
        'First subsequent completed stable collector weekday, date/schema/coverage checked before labels.',
        'Report arrival detection intervals, adjacent segment times and categorical grades separately; not passenger waits or headcounts.',
        'Known queue reports may be used only as explicitly labeled retrospective calibration constraints; never pristine holdout. No further fitting after opening a new-date outcome.',
        'No selection of best minute-second, route subset, weekday or scenario after inspecting outcomes.',
        'Use same source/scope censoring for comparison; missing and unmapped records remain separate.',
        'New manual queue counts and individual waiting episodes are separate observation units.',
        'Retain whole-journey tails and every continuous wait including departures outside the display window.'],
      'no_new_scheduler_or_download_created':True,'production_replacement_allowed':False}
    target=work/'future_evaluation_plan.json';assert not target.exists()
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print('FROZEN',work.name,len(files))
if __name__=='__main__':main()
