"""Independent full-audit validation and parent-cohort comparisons.

This does not run, fit, export, or promote the behavioral engine.
"""
from pathlib import Path
from collections import Counter,defaultdict
import bisect,csv,gzip,hashlib,json,math,sys

ROOT=Path(__file__).resolve().parent
SIM=ROOT.parent/'simulation_viewer_2026-11-07'
sys.path.insert(0,str(SIM))
import capacity_model as base
from verify_capacity_corrections import expected_roster
from preferences import traits

def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def close(a,b,tol=2e-5):assert abs(a-b)<tol,(a,b)
def quantile(rows,q):
    total=math.fsum(w for x,w in rows);s=0.
    for x,w in sorted(rows):
        s+=w
        if s>=q*total:return x
    return None

def cohorts(audit):
    out=defaultdict(Counter)
    for trip in audit['legs']:
        row=out[trip.get('parent_id',trip['id'])];w=trip['weight'];row['weight']+=w
        row['finished_weight']+=0 if trip['unserved'] else w
        for name,kind in [('walk_seconds',0),('wait_seconds',1),('ride_seconds',3)]:
            row[name]+=w*math.fsum(min(l[2],base.END if trip['unserved'] else float('inf'))-l[1] for l in trip['legs'] if l[0]==kind)
        row['total_seconds']+=w*((base.END if trip['unserved'] else trip['legs'][-1][2])-trip['start'])
        row['changes']+=w*len(trip['history']);row['fare_won']+=w*trip.get('fare_paid',0.)
    return out

def continuous(audit,nodes):
    rows=defaultdict(list)
    for trip in audit['legs']:
        pending=None
        def record(p):
            if p is None:return
            node,a,b=p
            if a<base.END and b>base.START and b-a>1e-7:
                # Clip only the end-of-window display sentinel/censoring.
                rows[node].append((max(0.,min(b,base.END)-a)/60,trip['weight'],a,trip['id']))
        for leg in trip['legs']:
            if leg[0]==1:
                if pending and pending[0]==leg[4] and abs(pending[2]-leg[1])<1e-5:pending[2]=leg[2]
                else:record(pending);pending=[leg[4],leg[1],leg[2]]
            else:record(pending);pending=None
        record(pending)
    result=[]
    for n,node in enumerate(nodes):
        a=rows[n];weight=math.fsum(r[1] for r in a)
        result.append({'node':n,'stop':node['name'],'ars':node.get('ars',''),'episode_weight':weight,
            'mean_wait_min':math.fsum(t*w for t,w,*_ in a)/weight if weight else None,
            'p90_wait_min':quantile([(t,w) for t,w,*_ in a],.9),
            'max_wait_min':max((r[0] for r in a),default=0.),'over20_weight':math.fsum(w for t,w,*_ in a if t>20+1e-7)})
    return result

def verify(case,work,frozen):
    did=base.DAYS[case['day']];s=case['scenario'];receipt=read(work/'result.json');audit=read(work/f'audit-{s}-{did}.json.gz');data=read(work/f'{s}-{did}.json.gz')
    assert receipt['status']=='COMPUTED_NOT_EMPIRICALLY_VALIDATED'
    for name,digest in receipt['code_sha256'].items():assert sha(work/'source_snapshot'/name)==digest==sha(ROOT/name),name
    assert receipt['experiment_lock_sha256']==sha(ROOT/'experiment_lock.json')
    common=frozen['prepared']['common'];plans=frozen['prepared']['plans'][case['day']];source={p[0]:p for p in plans}
    expected=expected_roster(frozen,s,True);assert len(expected)==len(audit['vehicles'])
    for v,(rid,start,cap,clock) in zip(audit['vehicles'],expected):
        assert v['id']<len(expected) and v['rid']==rid and v['cap']==cap;close(v['t0'],start)
    actual=Counter();board=Counter();off=Counter();changes=defaultdict(lambda:defaultdict(float));seen_traits={};checks=Counter()
    paths=None
    if receipt['config']['physics']!='v9_frozen':
        cfg=receipt['config'];spec={k:cfg[k] for k in ('walking_kmh','stairs_time_factor','slope_time_model')};spec['prepared']=read(ROOT/'pair_amendment.json')['prepared_sha256']
        key=hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()[:12];paths=read(ROOT/f'physical_paths_{key}.json.gz')
    for trip in audit['legs']:
        parent=trip['parent_id'];assert parent in source
        assert audit['parent_ids'][str(trip['id'])]==parent
        actual[parent]+=trip['weight'];close(trip['start'],source[parent][4]);w=trip['weight']
        close(trip['legs'][0][1],trip['start']);close(trip['legs'][-1][2],base.END+1 if trip['unserved'] else trip['finish_time'])
        expected_trait=traits(trip['id'],receipt['config']).record();assert trip['traits']==expected_trait
        if trip['id'] in seen_traits:assert trip['traits']==seen_traits[trip['id']]
        seen_traits[trip['id']]=trip['traits']
        for a,b in zip(trip['legs'],trip['legs'][1:]):close(a[2],b[1])
        assert all(a[0]<=b[0] for a,b in zip(trip['history'],trip['history'][1:]))
        physical_sum=0.
        for leg in trip['legs']:
            kind,a,b,pid,node,denied,vid,*_=leg
            assert math.isfinite(a+b) and b>=a and 0<=pid<len(common['paths'])
            physical_sum+=b-a;checks['passenger_legs']+=1
            if kind==0 and paths is not None:close(b-a,paths[pid]['seconds'])
            if kind==3:
                board[node,vid,a]+=w;off[vid,b]+=w;changes[vid][a]+=w;changes[vid][b]-=w
        close(physical_sum,trip['legs'][-1][2]-trip['start'])
    assert set(actual)==set(source);mass_error=max(abs(actual[k]-source[k][3]) for k in source);assert mass_error<1e-6
    occupancy={}
    for vid,delta in changes.items():
        running=0.;ts=[];values=[]
        for t,x in sorted(delta.items()):running+=x;ts.append(t);values.append(running)
        close(running,0.);occupancy[vid]=(ts,values)
    for v in audit['vehicles']:
        for a,b,pid,load in v['legs']:
            ts,vs=occupancy.get(v['id'],([],[]));idx=bisect.bisect_right(ts,a+1e-7)-1;want=vs[idx] if idx>=0 else 0.
            close(load,want);assert -1e-6<=load<=v['cap']+1e-6
            assert b-a>=common['motion_profiles'][str(pid)]['duration']-1e-5
            checks['vehicle_segments']+=1
    by_elig=defaultdict(list);board_tickets=defaultdict(list);cancelled=0.
    assert len(audit['waits'])==len(audit['wait_audit'])
    for row,m in zip(audit['waits'],audit['wait_audit']):
        n,a,b,w,denied,unserved,uid,outcome=row
        close(a,m['arrival']);close(b,m['end']);close(w,m['weight']);assert outcome==m['outcome'] and b>=a
        assert m['stop_arrival_at']==a and m['ready_at']==m['ready'] and m['leave_at']==b
        if b<m['ready']-1e-7:
            assert outcome=='switched' and m['ticket'] is None and m['vehicle'] is None;cancelled+=w
        if outcome=='boarded':
            assert m['boarding_at']==b and b>=m['ready']-1e-7
            board_tickets[n,m['vehicle'],b].append(m['ticket'])
        else:assert m['boarding_at'] is None
        for rid,k in m['eligibility']:by_elig[n,rid,k].append(m)
        checks['wait_visits']+=1
    voluntary=defaultdict(set)
    for r in audit['boarding_choices']:
        assert r['action']=='voluntary_continue_waiting' and r['seats_available']>0
        voluntary[r['node'],r['vehicle'],r['time']].add(r['ticket'])
    for e in audit['events']:
        t,n,vid,cap,before,alight,on,after,left,new,physical,rid,k=e
        assert -1e-6<=after<=cap+1e-6;close(before-alight+on,after)
        close(on,board[n,vid,t]);close(alight,off[vid,t])
        assert physical+1e-6>=left and (left<=1e-6 or abs(after-cap)<1e-5)
        v=audit['vehicles'][vid];assert cap==v['cap'] and rid==v['rid'];close(t,v['t0']+common['route_info'][rid]['offsets'][k])
        taken=board_tickets[n,vid,t]
        if taken:
            declined=voluntary[n,vid,t]
            remain=[m['ticket'] for m in by_elig[n,rid,k] if m['ticket'] is not None and m['ready']<=t+1e-7 and m['end']>t+1e-7 and m['ticket'] not in declined]
            if remain:assert max(taken)<=min(remain),(case['case'],vid,t,max(taken),min(remain),'willing eligible FIFO')
            checks['willing_fifo_events']+=1
        checks['capacity_events']+=1
    for d in audit['behavior_decisions']:
        assert not d['forced']
        if 'generalized_cost_minutes' in d:assert math.isfinite(d['generalized_cost_minutes'])
    # Independently rebuild queues from visits; map playback has no causal role.
    delta=defaultdict(lambda:defaultdict(float))
    for n,a,b,w,*rest in audit['waits']:
        if rest[1] and abs(b-base.END)<1e-7:b+=1
        delta[n][a]+=w;delta[n][b]-=w
    for n,timeline in enumerate(data['queue_timeline']):
        running=0.;ts=[];vs=[]
        for t,d in sorted(delta[n].items()):running+=d;ts.append(t);vs.append(running)
        close(running,0.)
        for t,q,*_ in timeline:
            idx=bisect.bisect_right(ts,t)-1;close(q,vs[idx] if idx>=0 else 0.)
            checks['queue_timeline_points']+=1
    stoprows=continuous(audit,common['nodes']);counts=Counter()
    for trip in audit['legs']:counts[len(trip['history'])]+=trip['weight']
    c=cohorts(audit);old=read(SIM/'peak_pair_correction_2026-11-10'/f'audit-{s}-{did}.json.gz');before=cohorts(old)
    assert set(c)==set(before) and all(abs(c[k]['weight']-before[k]['weight'])<1e-6 for k in c)
    scope={}
    for name in ('all','snu','engineering_snu'):
        ids=[k for k,p in source.items() if name=='all' or p[2]=='snu' and (name!='engineering_snu' or p[1] in ('301','302'))]
        weight=math.fsum(c[k]['weight'] for k in ids)
        scope[name]={'weight':weight,'metrics':{field:{'baseline':math.fsum(before[k][field] for k in ids)/weight/divisor if weight else None,
            'prototype':math.fsum(c[k][field] for k in ids)/weight/divisor if weight else None} for field,divisor in
            [('walk_seconds',60),('wait_seconds',60),('ride_seconds',60),('total_seconds',60),('changes',1),('fare_won',1)]}}
    parity=None
    if case['mode']=='control':
        assert audit['events']==old['events'] and audit['waits']==old['waits']
        fields=('id','weight','unserved','history','start','legs')
        assert [{k:r[k] for k in fields} for r in audit['legs']]==[{k:r[k] for k in fields} for r in old['legs']]
        parity={'status':'EXACT','capacity_events':len(audit['events']),'wait_visits':len(audit['waits']),'trajectories':len(audit['legs'])}
    result={'status':'PASS_INTERNAL_INVARIANTS','case':case,'source_code_sha256':receipt['code_sha256'],'audit_sha256':sha(work/f'audit-{s}-{did}.json.gz'),
        'parent_mass_max_error':mass_error,'checks':dict(checks),'cancelled_before_ready_weight':cancelled,'control_parity':parity,
        'scope':scope,'stop_waits':stoprows,'change_distribution':dict(sorted(counts.items())),
        'maximum_continuous_wait_min':max(r['max_wait_min'] for r in stoprows),'over20_weight':math.fsum(r['over20_weight'] for r in stoprows),
        'max_queue':data['report']['max_queue'],'elapsed_seconds':receipt['elapsed_seconds'],'policy_report':receipt['policy_report'],
        'independent_empirical_validation':False,'empirical_decision':'NOT_EVALUABLE'}
    save(work/'independent_analysis.json',result);return result

def main(resume=False):
    frozen=read(ROOT/'frozen/prepared_capacity44_pair.json.gz');lock=read(ROOT/'experiment_lock.json');results=[]
    for case in lock['pilot_cases']:
        work=ROOT/'runs'/case['case']/'attempt_04'
        assert (work/'result.json').exists(),f'Pending finite run: {case["case"]}'
        prior=work/'independent_analysis.json'
        if resume and prior.exists():
            result=read(prior);assert result['status']=='PASS_INTERNAL_INVARIANTS' and result['case']==case
            assert result['audit_sha256']==sha(work/f'audit-{case["scenario"]}-{base.DAYS[case["day"]]}.json.gz')
            for name,digest in result['source_code_sha256'].items():assert digest==sha(ROOT/name)==sha(work/'source_snapshot'/name)
        else:result=verify(case,work,frozen)
        results.append(result)
        print('INDEPENDENT_PROTOTYPE_CHECK',case['case'],result['maximum_continuous_wait_min'],result['over20_weight'],flush=True)
    rows=[];stops=[]
    for r in results:
        for name,scope in r['scope'].items():
            row={'case':r['case']['case'],'scope':name,'weight':scope['weight'],'max_continuous_wait_min':r['maximum_continuous_wait_min'],
                 'over20_episode_weight':r['over20_weight'],'max_queue':r['max_queue'],'runtime_seconds':r['elapsed_seconds']}
            for field,pair in scope['metrics'].items():
                for mode,value in pair.items():row[mode+'_'+field]=value
            rows.append(row)
        stops.extend({'case':r['case']['case'],**s} for s in r['stop_waits'])
    for name,values in [('comparison.csv',rows),('all_stops_waits.csv',stops)]:
        with (ROOT/name).open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,list(values[0]));writer.writeheader();writer.writerows(values)
    summary={'status':'NOT_EVALUABLE','operational_action':'KEEP_PREVIOUS_BEHAVIOR_ALGORITHM','new_algorithm_promoted':False,
        'internal_invariants':'PASS','cases':len(results),'results':results,'source_supply':'capacity_v11 identical 44-person/pair inputs',
        'independent_heldout_dates':[],'reason':'No aligned unused personal-wait/boarding truth. Existing three reports were used for old selection; Nov10 is a single supply-correction diagnostic event.',
        'new_algorithm_operationally_ready':all(r['over20_weight']<1e-7 for r in results),
        'no_clipping_or_forced_abandonment':True,'experiment_lock_sha256':sha(ROOT/'experiment_lock.json'),
        'reused_independent_analyses_after_audit_and_source_hash_checks':resume,
        'validator_numeric_core_source':'analyze_before_resume.py' if resume else 'analyze.py'}
    save(ROOT/'comparison.json',summary);print('NINE_CASES_COMPLETE',summary['status'],summary['new_algorithm_operationally_ready'],flush=True)

if __name__=='__main__':main('--resume' in sys.argv)
