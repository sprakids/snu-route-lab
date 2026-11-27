from pathlib import Path
from collections import Counter,defaultdict
import json,gzip
ROOT=Path(__file__).resolve().parent;B=ROOT.parent/'261116010854'
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def terminal_mode(stages):
    if not stages:return 'walk'
    e=stages[0];tail=e.get('continuation_stages',stages[1:])
    return terminal_mode(tail) if tail else 'shuttle' if e['rid'].startswith('shuttle') else 'city'
f=read(B/'frozen/prepared_capacity44_pair.json.gz')
source={p[0]:p for rows in f['prepared']['plans'].values() for p in rows};dest=f['destination_keys'];output=[]
for day in ['mon','tue','wed']:
    p=B/f'runs/queuefit-combined-regular-{day}/attempt_01/audit-regular-{day}.json.gz';a=read(p)
    found=Counter();uid_status=defaultdict(set);matches=[]
    for t in a['legs']:
        parent=t['parent_id'];d=dest[str(parent)]
        if d not in ('snu','daehak') or t['history']:continue
        old=terminal_mode(source[parent][6])
        if old=='walk':continue
        rides=[l for l in t['legs'] if l[0]==3]
        if not rides:continue
        new='shuttle' if a['vehicles'][rides[-1][6]]['rid'].startswith('shuttle') else 'city'
        uid_status[t['id']].add((old,new))
        if old!=new:
            found[(d,old,new)]+=t['weight']
            if len(matches)<5:matches.append({'uid':t['id'],'weight':t['weight'],'source':source[parent],'actual':t['legs']})
    affected=Counter()
    for w in a['wait_audit']:
        states=uid_status.get(w['id'],set())
        if states and all(x!=y for x,y in states) and w['realized_change_count']==0 and w['end']-w['arrival']>1200:
            affected[w['node']]+=w['weight']
    r={'day':day,'unrecorded_initial_trunk_changes':[{'key':list(k),'weight':v} for k,v in found.items()],
       'over20_weight_with_all_terminal_branches_changed':dict(affected),'examples':matches,
       'scope':'Existing no-reroute completed branches only; not all initial decisions or a survey of actual preferred mode.'}
    output.append(r);print(day,r['unrecorded_initial_trunk_changes'],'affected20',affected,flush=True)
out=ROOT/'baseline-trunk-diagnosis.json';assert not out.exists()
out.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
