"""Reconcile all continuous stop waits and paired original demand cohorts."""
from collections import Counter,defaultdict
import argparse,csv,math,json
import capacity_model as base
from prepare_walk_choices import prepare,read,WORK,ROOT,RULE
import verify_walk_choice_core as independent

OLD=ROOT/'gate_access_calibration_2026-11-09/candidates/alpha_075'
def physical_waits(audit):
    rows=[]
    for trip in audit['legs']:
        pending=None
        for leg in trip['legs']:
            if leg[0]==1:
                if pending and pending[0]==leg[4] and abs(pending[2]-leg[1])<1e-5:pending[2]=leg[2]
                else:
                    if pending:rows.append((*pending,trip['weight'],trip['id']))
                    pending=[leg[4],leg[1],leg[2]]
            else:
                if pending:rows.append((*pending,trip['weight'],trip['id']));pending=None
        if pending:rows.append((*pending,trip['weight'],trip['id']))
    return [(n,a,min(b,base.END),w,uid) for n,a,b,w,uid in rows if a<base.END and b>=base.START and b-a>1e-7]

def distribution(rows):
    by=defaultdict(list)
    for n,a,b,w,uid in rows:by[n].append((max(0.,b-a)/60,w))
    result={}
    for n,values in by.items():
        values.sort();total=math.fsum(w for _,w in values);running=0.;p90=None
        for t,w in values:
            running+=w
            if running>=.9*total:p90=t;break
        result[str(n)]={'waiting_episode_weight':total,'mean_continuous_wait_min':math.fsum(t*w for t,w in values)/total,
                        'p90_continuous_wait_min':p90,'max_continuous_wait_min':max(t for t,w in values),
                        'over_20_minute_weight':math.fsum(w for t,w in values if t>20+1e-7),
                        'over_20_minute_partition_rows':sum(t>20+1e-7 for t,w in values)}
    return result

def cohort(audit):
    result=defaultdict(lambda:Counter())
    for s in audit['legs']:
        row=result[s['id']];w=s['weight'];row['weight']+=w
        row['complete_weight']+=0 if s['unserved'] else w
        row['wait_seconds']+=w*sum(max(0.,min(l[2],base.END)-l[1]) for l in s['legs'] if l[0]==1)
        row['walking_seconds']+=w*sum(l[2]-l[1] for l in s['legs'] if l[0]==0)
        row['route_changes']+=w*len(s['history'])
        if not s['unserved']:row['total_seconds']+=w*(s['legs'][-1][2]-s['start'])
    return result

def analyze(day,scenario,verify=True):
    bundle=prepare();did=base.DAYS[day];common=bundle['prepared']['common'];out=WORK/'public_data'
    data=read(out/f'{scenario}-{did}.json');old_data=read(OLD/'public_data'/f'{scenario}-{did}.json')
    audit=read(WORK/f'audit-{scenario}-{did}.json.gz');old=read(OLD/f'audit-{scenario}-{did}.json.gz')
    core=independent.check(bundle,scenario,day,did) if verify else {'status':'NOT_RUN'}
    now=distribution(physical_waits(audit));before=distribution(physical_waits(old))
    targets={str(i):{'name':n['name'],'ars':n.get('ars'),'before_max_queue':max(r[1] for r in old_data['queue_timeline'][i]),
                     'after_max_queue':max(r[1] for r in data['queue_timeline'][i]),
                     'before_waits':before.get(str(i)), 'after_waits':now.get(str(i))}
             for i,n in enumerate(common['nodes']) if n['stop_id'] in RULE['soft_reference_stop_ids']}
    a,b=cohort(old),cohort(audit);assert set(a)==set(b)
    assert max(abs(a[k]['weight']-b[k]['weight']) for k in a)<1e-6
    paired=[k for k in a if abs(a[k]['weight']-a[k]['complete_weight'])<1e-7 and abs(b[k]['weight']-b[k]['complete_weight'])<1e-7]
    weight=math.fsum(a[k]['weight'] for k in paired)
    metrics={field:{'before':math.fsum(a[k][field] for k in paired)/weight/(1 if field=='route_changes' else 60),
                    'after':math.fsum(b[k][field] for k in paired)/weight/(1 if field=='route_changes' else 60)}
             for field in ('wait_seconds','walking_seconds','total_seconds','route_changes')}
    reasons=Counter();long_walk=Counter()
    for d in audit['behavior_decisions']:reasons[d['reason']]+=d['weight']
    result={'status':'PASS','scenario':scenario,'weekday':did,'core':core,'targets':targets,
            'all_stops':now,'baseline_all_stops':before,
            'maximum_continuous_wait_min':max(r['max_continuous_wait_min'] for r in now.values()),
            'over_20_minute_weight':math.fsum(r['over_20_minute_weight'] for r in now.values()),
            'baseline_over_20_minute_weight':math.fsum(r['over_20_minute_weight'] for r in before.values()),
            'decision_weight_by_reason':dict(reasons),'paired_complete_weight':weight,'paired_metrics':metrics,
            'field_fit':read(WORK/f'run-{scenario}-{did}.json').get('observation_fit'),
            'forty_reference_is_user_recollection_not_measurement':True}
    result['quality_gates']={'no_wait_over_20_min':result['over_20_minute_weight']<1e-7,
                             'named_stops_at_most_40':all(t['after_max_queue']<=40+1e-5 for t in targets.values()),
                             'independent_conservation':core['status']=='PASS'}
    base.save(WORK/f'analysis-{scenario}-{did}.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('core','all_stops','baseline_all_stops')},ensure_ascii=False),flush=True)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--day',choices=list(base.DAYS),required=True);p.add_argument('--scenario',choices=list(base.SCENARIOS),required=True)
    args=p.parse_args();analyze(args.day,args.scenario)
