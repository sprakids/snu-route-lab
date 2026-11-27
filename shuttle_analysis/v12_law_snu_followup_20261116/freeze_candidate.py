from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
ROOT=Path(__file__).resolve().parent;w=Path(json.loads((ROOT/'candidate.json').read_bytes())['path']);parent=w.parent/'261116122336'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists(),p
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
assert not (w/'pilot-started.json').exists()
future=read(parent/'future_evaluation_plan.json')
names=list(dict.fromkeys([*future['frozen_sha256'],'direct_restoration.py','test_direct_restoration.py']))
future.update(release_id=w.name,declared_at=datetime.now(timezone.utc).isoformat(),
    scope='Five known SNU direct-policy restorations. No numeric fit or new-date outcome reads.',frozen_sha256={n:sha(w/n) for n in names})
save(w/'future_evaluation_plan.json',future)
save(w/'protocol-reference.json',{'path':str(ROOT/'PROTOCOL.md'),'sha256':sha(ROOT/'PROTOCOL.md'),'registered_before_model_run':True,'production_writes':False})
print('FROZEN_SOURCE_AND_PROTOCOL',w.name,len(names))
