"""Compare legal direct policies across existing frozen catalogs and plans."""
from pathlib import Path
from collections import defaultdict,Counter
import gzip,json,hashlib
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'261116122336'
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
f=read(PARENT/'frozen/prepared_capacity44_pair.json.gz');nodes=f['prepared']['common']['nodes'];look={n['id']:i for i,n in enumerate(nodes)}
def nf(e):
    k=f"{e['rid']}|{e['board']}"
    return look[k] if e['rid'].startswith('shuttle') else f['city_node_lookup'][k]
def sig(e):return (e['rid'],e['board'],e['alight'],e['next_walk'][0])
all_direct=defaultdict(dict);provenance=defaultdict(set);all_entries=defaultdict(dict)
def visit(chain,dest,where):
    if not chain:return
    for e in chain[0].get('pool',[chain[0]]):
        tail=e.get('continuation_stages',chain[1:]);node=nf(e);key=f'{node}|{dest}'
        if not tail:
            all_direct[key].setdefault(sig(e),{k:v for k,v in e.items() if k not in ('pool','continuation_stages')})
            provenance[(key,sig(e))].add(where)
        visit(tail,dest,where)
for day,plans in f['prepared']['plans'].items():
    for p in plans:visit(p[6],f['destination_keys'][str(p[0])],'plans:'+day)
for key,options in f['alternatives'].items():
    dest=key.split('|',1)[1]
    for o in options:visit(o['stages'],dest,'alternatives')
for catalog in ('compatible_route_policies','compatible_single_stage_pools'):
    for key,es in f.get(catalog,{}).items():
        dest=key.split('|',1)[1]
        for e in es:visit([e],dest,catalog)
rows=[]
for key,entries in sorted(all_direct.items()):
    existing=set()
    for e in f.get('compatible_route_policies',{}).get(key,[]):
        if not e.get('continuation_stages'):existing.add(sig(e))
    missing=[{'signature':list(s),'entry':e,'sources':sorted(provenance[(key,s)])} for s,e in entries.items() if s not in existing]
    if missing:rows.append({'key':key,'node_name':nodes[int(key.split('|')[0])]['name'],'missing_direct':missing})
out=ROOT/'direct-policy-inventory.json';assert not out.exists()
out.write_text(json.dumps({'scope':'Known legal direct suffixes only; no new geometry, times, demand or field outcomes.',
    'affected_stop_destinations':len(rows),'missing_direct_policy_count':sum(len(r['missing_direct']) for r in rows),
    'missing_snu_policy_count':sum(len(r['missing_direct']) for r in rows if r['key'].endswith('|snu')),
    'rows':rows,'production_writes':False},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('MISSING_DIRECT',len(rows),sum(len(r['missing_direct']) for r in rows),'SNU',sum(len(r['missing_direct']) for r in rows if r['key'].endswith('|snu')),flush=True)
print(json.dumps([r for r in rows if r['key'].endswith('|snu')],ensure_ascii=False)[:5500],flush=True)
