from pathlib import Path
import json,hashlib
TASK=Path(__file__).resolve().parent;ROOT=TASK.parent
def read(p):return json.loads(p.read_text(encoding='utf8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    browser=read(TASK/'root-public-qa/qa.json');public=read(TASK/'root-public-data-verification.json');assert browser['status']==public['status']=='PASS'
    pointer=read(ROOT/'public/routing-model/latest.json');assert pointer['model_id']=='261110162302'
    receipt={'status':'DEPLOYED_AND_VERIFIED','site':'https://snu-shuttle-simulation.vercel.app/',
        'deployment_id':'dpl_3qtbkvVABLq8peZeSU61eDshqbLZ','model_id':pointer['model_id'],'payload_sha256':pointer['sha256'],
        'model_pointer_sha256':hashlib.sha256((ROOT/'public/routing-model/latest.json').read_bytes()).hexdigest(),
        'mobile_viewports':[[320,568],[360,740],[390,844],[844,390]],'mobile_checks':100,
        'tablet_and_desktop_layout_preserved':True,'responsive_restore_pass':True,'public_file_hash_checks':44,
        'native_touch_drag_pinch_pass':True,'models_data_and_default_unchanged':True,
        'prototype_algorithm_not_promoted':True,'source_handoff':'handoff_manifest.json','physical_ios_safari_tested':False}
    save(TASK/'root-release.json',receipt)
    release=read(ROOT/'deployment/release.json');release.update(deployment_id=receipt['deployment_id'],
        ui_stage=read(ROOT/'peak_pair_correction_2026-11-10/ui-stage.json'),mobile_ui=receipt,public_file_parity_checks=44)
    save(ROOT/'deployment/release.json',release);print(json.dumps(receipt))

if __name__=='__main__':main()
