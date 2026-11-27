from pathlib import Path
from collections import Counter
import json,gzip,hashlib,sys
w=Path(sys.argv[1]).resolve();path=w/'runs/primaryfix-combined-regular-tue/attempt_01/audit-regular-tue.json.gz'
a=json.loads(gzip.decompress(path.read_bytes()))
worst=max(a['wait_audit'],key=lambda r:r['end']-r['arrival']);uid=worst['id'];node=worst['node']
legs=[r for r in a['legs'] if r['id']==uid]
reviews=[r for r in a['review_diagnostics'] if r['uid']==uid and r['node']==node and worst['arrival']<=r['time']<=worst['end']]
switches=[r for r in a['behavior_decisions'] if r['uid']==uid]
out={'source':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'worst':worst,'finished_branches':legs,
     'reconsiderations':reviews,'switches':switches,'scope':'Existing completed candidate trajectory; not new simulation or observed student tracking.'}
target=w/'new-tail-diagnosis.json';assert not target.exists()
target.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('WORST',json.dumps(worst,ensure_ascii=False),flush=True)
for r in legs[:2]:print('BRANCH',r['weight'],r['student_patience_seconds'],r['student_preferred_mode'],r['history'],flush=True)
print('REVIEWS',len(reviews),flush=True)
for r in reviews[:2]+reviews[-2:]:print(json.dumps(r,ensure_ascii=False),flush=True)
