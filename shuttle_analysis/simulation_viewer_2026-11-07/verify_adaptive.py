"""Independent mass, queue, outcome, timing and unchanged-baseline checks."""
from collections import Counter,defaultdict
from pathlib import Path
import gzip,json,math
import numpy as np
import capacity_model as base
import adaptive_capacity_model as model
from prepare_adaptive import prepare,WORK,ROOT

def main():
    bundle=prepare();common=bundle['prepared']['common'];source=ROOT/'public/data/capacity_v4'
    baseline=base.read(ROOT/'public/data/capacity_v3/regular-mon.json')
    nochange=model.simulate(bundle,'월','regular',export=False,settings={'max_switches':0})
    assert len(nochange['events'])==len(baseline['events'])
    assert np.max(np.abs(np.array(nochange['events'])-np.array(baseline['events'])))<1e-7
    assert np.max(np.abs(np.array(nochange['queues'])-np.array(baseline['queues'])))<1e-7
    runs=[];event_checks=queue_checks=leg_checks=hour_checks=0;submillisecond_boundary_samples=0
    profile_checks=0;max_jump=0.
    for p in common['motion_profiles'].values():
        for k,cap in enumerate(p['cap']):
            assert max(p['v'][k],p['v'][k+1])*3.6<=cap+1e-4
            assert p['d'][k+1]>=p['d'][k] and p['t'][k+1]>p['t'][k]
            profile_checks+=1
    for scenario in base.SCENARIOS:
        for day,did in base.DAYS.items():
            d=base.read(source/f'{scenario}-{did}.json')
            a=json.loads(gzip.decompress((WORK/f'audit-{scenario}-{did}.json.gz').read_bytes()))
            expected={p[0]:p[3] for p in bundle['prepared']['plans'][day]};actual=Counter()
            boarded=Counter();gateids={r['route_id'] for r in bundle['gate_routes']}
            for s in a['legs']:
                actual[s['id']]+=s['weight'];assert len(s['history'])<=2
                for left,right in zip(s['legs'],s['legs'][1:]):
                    assert abs(left[2]-right[1])<1e-5
                for l in s['legs']:
                    assert l[2]>=l[1] and 0<=l[3]<len(common['paths'])
                    if l[0]==3:boarded[l[4],l[6],l[1]]+=s['weight']
                    leg_checks+=1
            assert set(actual)==set(expected)
            assert max(abs(actual[k]-v) for k,v in expected.items())<1e-6
            waits=a['waits'];by_node=defaultdict(list)
            for w in waits:
                assert w[7] in ('boarded','switched','unserved') and w[2]>=w[1]
                assert w[5]==(w[7]=='unserved');by_node[w[0]].append(w)
            for e in a['events']:
                t,node,vid,cap,before,off,on,after,left,new=e
                assert abs(before-off+on-after)<1e-7 and -1e-7<=after<=cap+1e-7
                assert abs(boarded[node,vid,t]-on)<1e-6
                # Queue mass at the event includes only passengers already ready.
                ready=sum(w[3] for w in by_node[node] if w[1]+20<=t+1e-7 and w[2]>t+1e-7)
                assert abs(ready-left)<1e-5,(scenario,day,node,t,ready,left)
                event_checks+=1
            for x in a['switches']:
                assert x[7] is None or x[8]+120<=x[7]+1e-6
            assert all(x[1] in gateids for x in a['gate_boardings'])
            for node,rows in by_node.items():
                for h in range(11,24):
                    rows_h=[w for w in rows if max(base.START,h*3600)<=w[1]<min(base.END,(h+1)*3600)]
                    stat=d['hourly'][str(node)][str(h)];served=[w for w in rows_h if w[7]=='boarded'];sw=sum(w[3] for w in served)
                    assert abs(sum(w[3] for w in rows_h)-stat['arrival_weight'])<1e-6
                    assert abs(stat['arrival_weight']-stat['served_weight']-stat['switched_weight']-stat['unserved_weight'])<1e-6
                    if sw:assert abs(sum((w[2]-w[1])*w[3] for w in served)/sw/60-stat['mean_wait_min'])<1e-7
                    else:assert stat['mean_wait_min'] is None
                    hour_checks+=1
                # Exact event timeline checked at independent 73-second samples.
                times=np.array([r[0] for r in d['queue_timeline'][node]])
                vals=np.array([r[1] for r in d['queue_timeline'][node]])
                for t in range(base.START,base.END,73):
                    j=np.searchsorted(times,t,side='right')-1;v=vals[j] if j>=0 else 0.
                    independently=sum(w[3] for w in rows if round(w[1],3)<=t<round(w[2],3))
                    assert abs(v-independently)<2e-5,(scenario,day,node,t,float(v),independently)
                    # Public event times are serialized to milliseconds. A sample
                    # within half a millisecond of a raw boundary can see that
                    # transition early/late; separately check unrounded times
                    # everywhere else rather than inflating a mass tolerance.
                    if any(min(abs(w[1]-t),abs(w[2]-t))<.000501 for w in rows):submillisecond_boundary_samples+=1
                    else:assert abs(v-sum(w[3] for w in rows if w[1]<=t<w[2]))<2e-5
                    queue_checks+=1
            runs.append(d['report'])
    result={'status':'PASS','runs':len(runs),'mass_by_original_particle':True,
        'disabled_rerouting_matches_original_v3_events_and_queues':True,
        'capacity_boarding_queue_events_checked':event_checks,'exact_queue_samples':queue_checks,
        'hourly_outcome_checks':hour_checks,'leg_checks':leg_checks,'speed_phases_checked':profile_checks,
        'serialized_millisecond_boundary_samples':submillisecond_boundary_samples,
        'switch_gain_min_seconds':120,'max_changes_per_flow':2,'runs_report':runs,
        'meaning':'Implementation consistency, not validation of actual student behavior or actual bus operations.'}
    base.save(WORK/'independent_verification.json',result);print(json.dumps({k:v for k,v in result.items() if k!='runs_report'},ensure_ascii=False))

if __name__=='__main__':main()
