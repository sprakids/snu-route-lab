"""Apply only the reviewed app source files, after preserving originals."""
import hashlib
import json
import shutil
from datetime import datetime,timezone,timedelta
from pathlib import Path

WORK=Path(__file__).resolve().parent
APP=WORK.parent/'app'
FILES=('city_operations.py','queue_release.py','automatic_queue.py','city_wait.py','travel_time.py',
    'server.py','continuity.py','gate_service.py','prepare_city_queue.py','prepare_latest_queue.py',
    'test_city_operations.py','test_shuttle_timetable.py','test_fixtures/queue_release_v3_contract.py')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    # This intentionally refuses repeated application and unexpected source edits.
    backup=WORK/'before_apply'
    assert not backup.exists(),'already applied or preserved; do not overwrite'
    baseline=json.loads((WORK/'source-preservation.json').read_bytes())
    changed=[name for name,digest in baseline.items() if not (APP/name).is_file() or sha(APP/name)!=digest]
    assert not changed,('unexpected original modifications',changed)
    test_result=(WORK/'candidate-all-tests.txt').read_text(encoding='utf-8',errors='replace')
    assert '\nOK\n' in test_result.replace('\r\n','\n'),'full regression not yet passed'
    for name in FILES:
        if name not in baseline:assert not (APP/name).exists(),('unexpected existing file',name)
    backup.mkdir()
    records=[]
    for name in FILES:
        target=APP/name;source=WORK/'app_candidate'/name
        before=sha(target) if target.exists() else None
        if target.exists():
            saved=backup/name;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,saved)
        target.parent.mkdir(parents=True,exist_ok=True)
        pending=target.with_name(target.name+'.operations-pending')
        assert not pending.exists(),('pending artifact exists',name)
        shutil.copy2(source,pending);pending.replace(target)
        records.append({'path':name,'before_sha256':before,'after_sha256':sha(target)})
    untouched=[name for name in baseline if name not in FILES]
    assert all(sha(APP/name)==baseline[name] for name in untouched)
    receipt={'applied_at':datetime.now(timezone(timedelta(hours=9))).isoformat(),'files':records,
        'untouched_existing_files':len(untouched),'data_files_changed':0,'ui_files_changed':0,
        'environment_files_changed':0,'production_deployed':False,'latest_pointer_changed':False,
        'source_preserved_in':'before_apply','regression_log':'candidate-all-tests.txt'}
    (WORK/'source-apply-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if k!='files'}))

if __name__=='__main__':main()
