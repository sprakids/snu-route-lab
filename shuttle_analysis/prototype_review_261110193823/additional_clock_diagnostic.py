"""Record the extra gate-reference outcome, including every overlapping long wait."""
from pathlib import Path
from collections import defaultdict
import gzip,hashlib,json,math
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    target=ROOT/'additional_clock_diagnostic.json';assert not target.exists()
    parent=Path(read(ROOT/'creation_manifest.json')['candidate']);folder=parent/'runs/gate_reference-combined-regular-mon/attempt_01'
    report=read(folder/'independent_analysis.json');assert report['status']=='PASS_INTERNAL_INVARIANTS'
    source=folder/'audit-regular-mon.json.gz';assert sha(source)==report['audit_sha256'];rows=[]
    if report['over20_weight']>1e-7:
        audit=read(source);nodes=read(parent/'frozen/prepared_capacity44_pair.json.gz')['prepared']['common']['nodes'];meta=defaultdict(list)
        for m in audit['wait_audit']:meta[m['id']].append(m)
        for trip in audit['legs']:
            pending=None;episodes=[]
            for l in trip['legs']:
                if l[0]==1:
                    if pending and pending[0]==l[4] and abs(pending[2]-l[1])<1e-5:pending[2]=l[2]
                    else:
                        if pending:episodes.append(pending)
                        pending=[l[4],l[1],l[2]]
                else:
                    if pending:episodes.append(pending);pending=None
            if pending:episodes.append(pending)
            for n,a,b in episodes:
                b=min(b,83400.)
                if a>=83400 or b<=40800 or b-a<=1200.000006:continue
                matched=[m for m in meta[trip['id']] if m['node']==n and m['arrival']>=a-1e-5 and m['end']<=b+1e-5]
                rows.append({'uid':trip['id'],'weight':trip['weight'],'node':n,'stop':nodes[n]['name'],'ars':nodes[n].get('ars'),
                    'arrival_second':a,'leave_second':b,'continuous_wait_min':(b-a)/60,
                    'previous_changes':sum(h[0]<=a for h in trip['history']),
                    'full_passes':max((m['full_passes_seen'] for m in matched),default=None)})
        assert abs(math.fsum(r['weight'] for r in rows)-report['over20_weight'])<1e-6
    target.write_text(json.dumps({'status':'PASS20_ADDITIONAL_GATE_REFERENCE' if report['over20_weight']<1e-7 else 'FAIL20_IN_ADDITIONAL_GATE_REFERENCE_CLOCK_SCENARIO',
        'maximum_continuous_wait_min':report['maximum_continuous_wait_min'],'over20_weight':report['over20_weight'],'rows':rows,
        'primary_clock_registered_before_these_outcomes':True,'source':str(source),'source_sha256':sha(source),
        'not_a_user_observed20minute_wait':True,'not_a_universal20minute_guarantee':True,
        'no_clipping_or_forced_late_walk':True},ensure_ascii=False,indent=2),encoding='utf8')
    print('ADDITIONAL_CLOCK_RECORDED',report['maximum_continuous_wait_min'],report['over20_weight'])
if __name__=='__main__':main()
