"""Read existing Monday flows to locate a queue mismatch; no refit or simulation."""
from pathlib import Path
from collections import Counter
import argparse,gzip,hashlib,json,math
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve();out=w/'gate-flow-before-after.json';assert not out.exists()
    sources=[];node=62;start=16*3600+30*60;end=17*3600+4*60;minute=17*3600+3*60
    plans=read(w/'frozen/prepared_capacity44_pair.json.gz')['prepared']['plans']['월'];origin={p[0]:('walk' if not p[6] else 'shuttle' if p[6][0]['rid'].startswith('shuttle') else 'city') for p in plans}
    for model in ['261116105704',w.name]:
        root=w.parent/model;group='grid' if (root/'grid-validation.json').exists() else 'pilot'
        r=next(r for r in read(root/f'{group}-validation.json')['results'] if r['case']['day']=='월' and r['case']['scenario']=='regular' and not r['case']['case'].startswith('ablation'))
        folder=Path(r['source_directory']);ap=folder/'audit-regular-mon.json.gz';audit=read(ap);trips={t['id']:t for t in audit['legs']}
        waits=[x for x in audit['wait_audit'] if x['node']==node];counts=Counter();cohort=Counter();initial=changed=0.
        for x in waits:
            weight=x['weight'];a0=x['arrival'];b0=x['end']
            if a0<=start<b0:counts['queue_at_start']+=weight
            if a0<=end<b0:counts['queue_at_end']+=weight
            if start<a0<=end:
                counts['arrivals']+=weight;cohort[origin[trips[x['id']]['parent_id']]]+=weight
                n=sum(h[0]<=a0+1e-7 for h in trips[x['id']]['history'])
                if n:changed+=weight
                else:initial+=weight
            if start<b0<=end:
                counts['exits']+=weight;counts['exit_'+x['outcome']]+=weight
            counts['minute_mean_from_wait_records']+=max(0.,min(b0,minute+60)-max(a0,minute))/60*weight
        # Use half-open state conventions on both boundaries.
        q0=sum(x['weight'] for x in waits if x['arrival']<=start<x['end']);q1=sum(x['weight'] for x in waits if x['arrival']<=end<x['end'])
        arr=sum(x['weight'] for x in waits if start<x['arrival']<=end);ex=sum(x['weight'] for x in waits if start<x['end']<=end)
        assert abs(q0+arr-ex-q1)<1e-6,(q0,arr,ex,q1)
        for key,value in [('queue_at_start',q0),('queue_at_end',q1),('arrivals',arr),('exits',ex)]:assert abs(counts[key]-value)<1e-6,(key,counts[key],value)
        assert abs(sum(cohort.values())-arr)<1e-6
        payload=read(folder/'regular-mon.json.gz');timeline=payload['queue_timeline'][node];mean=0.
        for i,(t,q) in enumerate(timeline):
            until=timeline[i+1][0] if i+1<len(timeline) else minute+60
            mean+=q*max(0.,min(until,minute+60)-max(t,minute))/60
        assert abs(mean-counts['minute_mean_from_wait_records'])<1e-5,(model,mean,counts['minute_mean_from_wait_records'])
        sources.append({'model':model,'audit_path':str(ap),'audit_sha256':sha(ap),'node':node,'window_seconds':[start,end],
            'minute_mean_17_03':mean,'flow':dict(counts),'arrival_original_mode_cohort':dict(cohort),
            'arrivals_without_prior_changes':initial,'arrivals_after_changes':changed,'mass_balance_error':q0+arr-ex-q1})
    result={'scope':'Post-hoc comparison of fixed-model flows; not an isolated causal ablation or empirical validation','boundary_convention':'Queue state arrival<=t<end; flows in (16:30,17:04], including zero-length visits on both sides. v1 kept: its interval used a different endpoint convention from its separate conservation check.','analysis_script_sha256':sha(Path(__file__)),'cases':sources,'parameters_changed':False,'production_writes':False}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print('GATE_FLOW_DIAGNOSED',sources,flush=True)
if __name__=='__main__':main()
