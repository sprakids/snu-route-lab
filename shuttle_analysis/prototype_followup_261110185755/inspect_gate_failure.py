"""Read-only long-wait reconstruction. Never changes or reruns a case."""
from pathlib import Path
import gzip,json
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
folder=ROOT/'runs/gate_reference-combined-regular-mon/attempt_01'
audit=read(folder/'audit-regular-mon.json.gz')
bundle=read(ROOT/'frozen/prepared_capacity44_pair.json.gz')
nodes=bundle['prepared']['common']['nodes']
out=[]
for trip in audit['legs']:
    for leg in trip['legs']:
        if leg[0]!=1 or min(83400,leg[2])-leg[1]<=1200.000001:continue
        uid=trip['id'];n=leg[4];a,b=leg[1:3]
        item={'trip':trip,'long_leg':leg,'stop':nodes[n],
              'wait_audit':[m for m in audit['wait_audit'] if m['id']==uid and m['node']==n and a-1e-5<=m['arrival']<=b],
              'reviews':[r for r in audit['review_diagnostics'] if r['uid']==uid and a<=r['time']<=b],
              'declines':[r for r in audit['boarding_choices'] if r['uid']==uid and a<=r['time']<=b]}
        services={tuple(s) for m in item['wait_audit'] for s in m['eligibility']}
        item['services']=[e for e in audit['events'] if e[1]==n and (e[11],e[12]) in services and a<=e[0]<=b]
        out.append(item)
target=ROOT/'gate_reference_long_wait_reconstruction.json'
assert not target.exists()
target.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
for item in out:
    t=item['trip'];print(json.dumps({'uid':t['id'],'weight':t['weight'],'history':t['history'],'long_leg':item['long_leg'],'stop':item['stop'],'reviews':item['reviews'][:3]+item['reviews'][-2:],'wait_audit':item['wait_audit'],'declines':item['declines'],'services':item['services']},ensure_ascii=False))
