"""Reconstruct canonical admin episodes and original modal cohort of the increase."""
from pathlib import Path
from collections import Counter,defaultdict
import gzip,hashlib,json,math,gc
ROOT=Path(__file__).resolve().parent;A=ROOT.parent;G=Path(json.loads((ROOT/'candidate.json').read_bytes())['path']);F=A/'261116122336'
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
f=read(G/'frozen/prepared_capacity44_pair.json.gz');parents={p[0]:p for ps in f['prepared']['plans'].values() for p in ps}
reports=[];samples={}
for w in [F,G]:
    r=next(x for x in read(w/'pilot-validation.json')['results'] if x['case']['day']=='화' and not x['case']['case'].startswith('ablation'))
    p=Path(r['source_directory'])/'audit-regular-tue.json.gz';a=read(p);groups=Counter();uidmass=Counter();details=defaultdict(list)
    for t in a['legs']:
        pending=None;episodes=[]
        for l in t['legs']:
            if l[0]==1:
                if pending and pending[0]==l[4] and abs(pending[2]-l[1])<1e-5:pending[2]=l[2]
                else:
                    if pending:episodes.append(pending)
                    pending=[l[4],l[1],l[2]]
            elif pending:episodes.append(pending);pending=None
        if pending:episodes.append(pending)
        for node,start,end in episodes:
            if node!=1 or end-start<=1200+1e-7:continue
            source=parents[t['parent_id']];first='walk' if not source[6] else ('shuttle' if source[6][0]['rid'].startswith('shuttle') else 'city')
            prior_changes=sum(h[0]<=start for h in t['history'])
            groups[(first,prior_changes,int(start//1800)*1800)]+=t['weight'];uidmass[t['id']]+=t['weight']
            if len(details[t['id']])<4:details[t['id']].append({'weight':t['weight'],'start':start,'end':end,'wait_minutes':(end-start)/60,
                'personal_minutes':t['student_patience_seconds']/60,'source_mode':first,'source_building':source[1],
                'prior_changes':prior_changes,'history':t['history'],'legs':t['legs']})
    samples[w.name]=(uidmass,details)
    reports.append({'model':w.name,'total_admin_over20':math.fsum(uidmass.values()),
        'groups':[{'source_mode':k[0],'prior_changes':k[1],'entry_half_hour':k[2],'weight':v} for k,v in groups.most_common()]})
    del a;gc.collect()
old,old_detail=samples[F.name];new,new_detail=samples[G.name];changed=[]
for uid in set(old)|set(new):
    delta=new[uid]-old[uid]
    if abs(delta)>1e-7:changed.append({'uid':uid,'old_over20_weight':old[uid],'new_over20_weight':new[uid],'delta':delta,
        'old_examples':old_detail.get(uid,[]),'new_examples':new_detail.get(uid,[])})
changed.sort(key=lambda r:r['delta'],reverse=True)
out=ROOT/'admin-over20-regression-trace.json';assert not out.exists()
out.write_text(json.dumps({'scope':'Completed canonical episodes at Tuesday admin; a UID may have split fragments, not a matched real person.',
    'models':reports,'changed_uid_examples':changed[:25],'production_writes':False},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('ADMIN_OVER20',json.dumps(reports,ensure_ascii=False)[:6000],flush=True)
print('INCREASE_EXAMPLES',json.dumps([{k:v for k,v in r.items() if k not in ('old_examples','new_examples')} for r in changed[:10]],ensure_ascii=False),flush=True)
