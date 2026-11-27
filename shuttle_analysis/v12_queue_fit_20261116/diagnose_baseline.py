"""Account for every >20min continuous episode using immutable trip/queue records."""
from pathlib import Path
from collections import Counter,defaultdict
import gzip,json,hashlib,math
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent/'261115160710'
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    out=ROOT/'baseline-cause-ledger.json';assert not out.exists();validation=read(BASE/'grid-validation.json');rows=[]
    common=read(BASE/'frozen/prepared_capacity44_pair.json.gz')['prepared']['common']
    for r in validation['results']:
        c=r['case'];day={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}[c['day']]
        path=Path(r['source_directory'])/f"audit-{c['scenario']}-{day}.json.gz";a=read(path);raw=defaultdict(list)
        for x in a['wait_audit']:raw[x['id'],x['node']].append(x)
        categories=Counter();byhour=Counter();bymode=Counter();bychanges=Counter();maximum=0.;long=[];patience=Counter()
        for t in a['legs']:
            w=t['weight'];p=t['student_patience_seconds'];patience['mass']+=w
            for limit in [1200,1500,1800,2100]:patience['above_'+str(limit)]+=w if p>limit else 0.
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
                if t['unserved']:end=min(end,83400)
                age=end-start;maximum=max(maximum,age/60)
                if age<=1200+1e-5:continue
                visits=[x for x in raw[t['id'],node] if x['arrival']>=start-1e-5 and x['end']<=end+1e-5]
                eligible=sorted({tuple(z) for x in visits for z in x['eligibility']})
                mode='shuttle' if eligible and all(x[0].startswith('shuttle') for x in eligible) else 'city' if eligible and all(not x[0].startswith('shuttle') for x in eligible) else 'mixed_or_missing'
                label='within_declared_patience' if age<=p+1e-5 else 'gate_final_past_patience' if node==62 else 'other_past_patience'
                changes=sum(h[0]<=start+1e-5 for h in t['history'])
                categories[label]+=w;byhour[str(int(start//3600))]+=w;bymode[mode]+=w;bychanges[str(changes)]+=w
                long.append({'uid':t['id'],'node':node,'stop':common['nodes'][node]['name'],'arrival':start,'end':end,'wait_min':age/60,'patience_min':p/60,
                    'weight':w,'reason_class':label,'mode':mode,'prior_changes':changes,'eligible':eligible,
                    'full_passes_seen':max((x['full_passes_seen'] for x in visits),default=None),
                    'outcomes':sorted({x['outcome'] for x in visits})})
        assert abs(maximum-r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min'])<1e-6
        assert abs(sum(categories.values())-r['extended_diagnostics']['all_recorded_time_over20_episode_weight'])<1e-6
        maxids={x['uid'] for x in sorted(long,key=lambda x:-x['wait_min'])[:8]}
        reviews=[x for x in a['review_diagnostics'] if x['uid'] in maxids]
        row={'case':c,'source':str(path),'sha256':sha(path),'over20_categories':dict(categories),'over20_by_entry_hour':dict(sorted(byhour.items())),
            'over20_by_mode':dict(bymode),'over20_by_prior_changes':dict(bychanges),'patience_population':dict(patience),
            'longest_visits':sorted(long,key=lambda x:-x['wait_min'])[:8],'reviews_for_longest_recorded':reviews,
            'review_capture_count':len(a['review_diagnostics']),'review_capture_is_capped_at':20000}
        rows.append(row);print('BASE_CAUSES',c['day'],c['scenario'],dict(categories),dict(bymode),dict(sorted(byhour.items())),flush=True)
    out.write_text(json.dumps({'source_model':BASE.name,'cases':rows,'scope':'Synthetic continuous episodes, not measured persons. Personal patience was an unmeasured model assumption. Missing capped review rows do not prove no review.'},ensure_ascii=False,indent=2),encoding='utf8')
if __name__=='__main__':main()
