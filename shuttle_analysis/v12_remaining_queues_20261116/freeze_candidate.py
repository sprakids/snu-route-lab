from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,sys
ROOT=Path(__file__).resolve().parent
work=Path(sys.argv[1]).resolve();parent=ROOT.parent/'261116010854'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
 assert not p.exists(),p
 p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
future=read(parent/'future_evaluation_plan.json')
future.update(release_id=work.name,declared_at=datetime.now(timezone.utc).isoformat(),
 scope='Mechanism-only same-platform reconsideration. No numerical patience, demand, clock or capacity fit. Reused queues are not independent validation.')
extra=['test_same_stop_release.py']+[n for n in ['test_trunk_preservation.py','test_primary_stop.py'] if (work/n).exists()]
future['frozen_sha256']={n:sha(work/n) for n in [*future['frozen_sha256'],*extra]}
save(work/'future_evaluation_plan.json',future)
protocol=ROOT/(sys.argv[2] if len(sys.argv)>2 else 'PROTOCOL.md')
save(work/'protocol-reference.json',{'path':str(protocol),'sha256':sha(protocol),'registered_before_model_run':True,'production_writes':False})
print('FROZEN_RUNTIME_AND_PROTOCOL',work.name,len(future['frozen_sha256']))
