from pathlib import Path
import json,hashlib,shutil

ROOT=Path(__file__).resolve().parent;TASK=ROOT/'mobile_ui_261110165808'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    manifest=json.loads((TASK/'handoff_manifest.json').read_text(encoding='utf8'))
    assert manifest['status']=='FROZEN_READY_FOR_PEER_REVIEW'
    before=TASK/'root_before_apply';assert not before.exists();before.mkdir()
    latest=ROOT/'public/routing-model/latest.json';model=latest.read_bytes()
    for row in manifest['protected_data_checks']:
        assert row['unchanged'] and sha(ROOT/'public'/row['path'])==row['sha256'],row['path']
    for row in manifest['files']:
        name=Path(row['path']).name;source=TASK/'candidate'/name;target=ROOT/row['path']
        assert sha(source)==row['candidate_sha256']
        if not row['new']:
            assert sha(target)==row['baseline_sha256'];shutil.copy2(target,before/name)
        else:assert not target.exists()
    for row in manifest['files']:shutil.copy2(TASK/'candidate'/Path(row['path']).name,ROOT/row['path'])
    assert latest.read_bytes()==model
    receipt={'status':'APPLIED_LOCALLY_MODEL_UNCHANGED','files':manifest['files'],'latest_sha256':sha(latest),
        'model_id':json.loads(model)['model_id'],'prototype_model_promoted':False}
    (TASK/'root-apply-verification.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
    old=ROOT/'peak_pair_correction_2026-11-10/ui-stage.json';shutil.copy2(old,TASK/'supply-ui-stage-before-mobile.json')
    shutil.copy2(ROOT/'deployment/release.json',TASK/'release-before-mobile.json');print(receipt['status'])

if __name__=='__main__':main()
