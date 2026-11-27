"""Read plain, unencrypted public HWP attachments; preserve source bytes."""
from pathlib import Path
import sys,importlib.util,json,hashlib,struct
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'traffic_results_2026-11-06'
spec=importlib.util.spec_from_file_location('read_public_hwp',OLD/'extract_meetings.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
OUT=ROOT/'contracts/text';OUT.mkdir(parents=True,exist_ok=True)
result=[]
for path in sorted((ROOT/'contracts/sources').glob('*.hwp')):
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    text=module.hwp_text(path)
    dest=OUT/(path.stem+'.txt');assert not dest.exists()
    dest.write_text(text,encoding='utf-8')
    with module.olefile.OleFileIO(path) as ole:
        header=ole.openstream('FileHeader').read()
        preview=ole.openstream('PrvText').read().decode('utf-16-le','replace') if ole.exists('PrvText') else ''
    if preview:(OUT/(path.stem+'_미리보기.txt')).write_text(preview,encoding='utf-8')
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
    result.append({'source':str(path.relative_to(ROOT)),'sha256':before,'text_file':str(dest.relative_to(ROOT)),
        'body_characters':len(text),'preview_characters':len(preview),'flags':struct.unpack_from('<I',header,36)[0],
        'source_unchanged':True,'table_layout_visually_verified':False})
(ROOT/'contracts/extraction_manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
