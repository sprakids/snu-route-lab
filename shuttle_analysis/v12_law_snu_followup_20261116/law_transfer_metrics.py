"""Fixed afternoon-window law queue/arrival metrics from completed ledgers only."""
from pathlib import Path
from collections import Counter,defaultdict
import argparse,gc,gzip,hashlib,json,math
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'261116122336'
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists(),p
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def profile(visits,node,start,end):
    events=Counter()
    for v in visits:
        if v['node']==node:events[v['arrival']]+=v['weight'];events[v['end']]-=v['weight']
    changes=sorted(events.items());q=mx=at=above=run=longest=0.
    for i,(t,delta) in enumerate(changes):
        q+=delta;stop=changes[i+1][0] if i+1<len(changes) else t
        lo,hi=max(t,start),min(stop,end)
        if hi-lo<=1e-7:continue
        if q>mx:mx=q;at=lo
        if q>40+1e-7:above+=hi-lo;run+=hi-lo;longest=max(run,longest)
        else:run=0.
    return {'node':node,'maximum_queue':mx,'peak_seconds':at,'minutes_above40':above/60,'longest_spell_above40_minutes':longest/60}
def measure(row,frozen):
    case=row['case'];eng={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}[case['day']]
    path=Path(row['source_directory'])/f"audit-{case['scenario']}-{eng}.json.gz";assert sha(path)==row['audit_sha256']
    a=read(path);start,end=54000.,72000.;dest=frozen['destination_keys']
    transfers=arrivals=0.;by_route=Counter()
    for t in a['legs']:
        if dest[str(t['parent_id'])]!='snu':continue
        for i,l in enumerate(t['legs']):
            if l[0]!=1 or l[4]!=60 or not start<=l[1]<end:continue
            arrivals+=t['weight'];prior=[x for x in t['legs'][:i] if x[0]==3]
            if prior:transfers+=t['weight'];by_route[str(prior[-1][6])]+=t['weight']
    from_waits=math.fsum(v['weight'] for v in a['wait_audit'] if v['node']==60 and start<=v['arrival']<end and dest[str(v['parent_id'])]=='snu')
    assert abs(arrivals-from_waits)<1e-5,(arrivals,from_waits)
    r={'case':case,'audit_sha256':row['audit_sha256'],'window_seconds':[start,end],
        'law_profiles':[profile(a['wait_audit'],n,start,end) for n in [47,60]],
        'snu_law_arrival_weight':arrivals,'snu_law_arrival_after_prior_bus_weight':transfers,
        'source_queue_arrival_reconstruction_error':abs(arrivals-from_waits),
        'catalog_repair_report':a['policy_report'].get('catalog_repair')}
    del a;gc.collect();return r
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');p.add_argument('--group',default='grid',choices=['pilot','grid']);p.add_argument('--reference-only',action='store_true');args=p.parse_args()
    w=Path(args.candidate).resolve();frozen=read(w/'frozen/prepared_capacity44_pair.json.gz')
    ref=w/'parent-law-reference.json'
    if not ref.exists():
        rows=[r for r in read(PARENT/'pilot-validation.json')['results'] if not r['case']['case'].startswith('ablation')]
        save(ref,{'model':PARENT.name,'scope':'Parent Monday/Tuesday regular only; fixed15-20 window, not field evidence.',
                  'cases':[measure(r,frozen) for r in rows]})
    if args.reference_only:print('PARENT_LAW_REFERENCE_READY',flush=True);return
    out=w/f'{args.group}-law-transfer-metrics.json';assert not out.exists()
    rows=read(w/f'{args.group}-validation.json')['results'];measured=[]
    for r in rows:
        measured.append(measure(r,frozen));print('LAW_TRANSFER_MEASURED',r['case']['case'],flush=True)
    save(out,{'model':w.name,'scope':'All completed cases in this group; main and disabled diagnostic remain labelled.',
        'cases':measured,'production_writes':False})
if __name__=='__main__':main()
