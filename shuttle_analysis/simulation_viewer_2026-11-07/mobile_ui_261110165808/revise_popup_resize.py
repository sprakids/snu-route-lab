from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json,hashlib,shutil
TASK=Path(__file__).resolve().parent;ROOT=TASK.parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    before=TASK/'before_popup_resize';assert not before.exists();before.mkdir()
    stamp=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%y%m%d%H%M%S')
    names=('mobile-lab.js','viewer-v5.js','index.html')
    latest=ROOT/'public/routing-model/latest.json';frozen=sha(latest)
    for name in names:shutil.copy2(ROOT/'public'/name,before/name)
    module=ROOT/'public/mobile-lab.js';s=module.read_text(encoding='utf8')
    marker="  document.addEventListener('lab:panechange',paneChanged);";assert marker in s
    s=s.replace(marker,"  map.on('resize',()=>{if(active)map.closePopup();});\n"+marker,1);module.write_text(s,encoding='utf8')
    viewer=ROOT/'public/viewer-v5.js';s=viewer.read_text(encoding='utf8');a="'./mobile-lab.js?v=261110165808'";assert a in s
    viewer.write_text(s.replace(a,f"'./mobile-lab.js?v={stamp}'",1),encoding='utf8')
    html=ROOT/'public/index.html';s=html.read_text(encoding='utf8');a='viewer-v5.js?v=mobile-261110165808';assert a in s
    html.write_text(s.replace(a,'viewer-v5.js?v=mobile-'+stamp,1),encoding='utf8')
    assert sha(latest)==frozen
    receipt={'status':'APPLIED_LOCAL_TARGETED_FIX','revision_id':stamp,'reason':'Existing Leaflet popup can cover the compact header after phone resize. Close only the old popup on mobile map resize; preserve selected stop/time/model and bottom-panel access.',
        'model_pointer_sha256':frozen,'files':{n:sha(ROOT/'public'/n) for n in names},'production_model_changed':False}
    (TASK/'popup_resize_revision.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8');print(stamp)

if __name__=='__main__':main()
