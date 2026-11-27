"""Private artifacts only: this package has no publisher or production writer."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import gzip,hashlib,json

ROOT=Path(__file__).resolve().parent
SIM=ROOT.parent/'simulation_viewer_2026-11-07'
SOURCE=SIM/'crowding_walk_choices_2026-11-10/initial_refit_H'
DAYS={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}
START,END,EPS=680*60,1390*60,1e-7
def read(p):
    p=Path(p);raw=p.read_bytes()
    return json.loads(gzip.decompress(raw) if p.suffix=='.gz' else raw)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
def packed(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(gzip.compress(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode(),mtime=0))
def model_id():return datetime.now(ZoneInfo('Asia/Seoul')).strftime('%y%m%d%H%M%S')
def check_baseline():
    manifest=read(ROOT/'input_manifest.json')
    amendment=read(ROOT/'capacity44_amendment.json') if (ROOT/'capacity44_amendment.json').exists() else {}
    for row in manifest['protected']:
        if row['path'] in amendment.get('separate_authorized_correction_mutable_paths',[]):continue
        p=SIM/row['path'];assert sha(p)==row['sha256'],f'Protected source changed: {p}'
    for row in manifest['frozen']+amendment.get('additional_frozen',[]):
        assert sha(ROOT/row['path'])==row['sha256'],row['path']
    return manifest
