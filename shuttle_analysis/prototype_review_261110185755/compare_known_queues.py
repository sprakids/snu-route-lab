"""All four known reports, fixed comparison protocol. Not a holdout or calibration."""
from pathlib import Path
from collections import defaultdict
import argparse,bisect,csv,gzip,hashlib,json,math
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def distance(x,lo,hi):return max(lo-x,0.,x-hi)
def stats(timeline,start,lo,hi):
    stop=start+60;times=[x[0] for x in timeline]
    k=bisect.bisect_right(times,start)-1;q=timeline[k][1] if k>=0 else 0.;at=start;parts=[]
    for t,value in timeline[k+1:]:
        if t>=stop:break
        if t>at:parts.append((q,t-at))
        at=t;q=value
    if at<stop:parts.append((q,stop-at))
    assert abs(math.fsum(dt for q,dt in parts)-60)<1e-7
    def quantile(p):
        acc=0.
        for x,w in sorted(parts):
            acc+=w
            if acc>=60*p:return x
    return {'uniform_minute_mean':math.fsum(q*dt for q,dt in parts)/60,
            'uniform_minute_p10':quantile(.1),'uniform_minute_p90':quantile(.9),
            'minute_minimum':min(q for q,dt in parts),'minute_maximum':max(q for q,dt in parts),
            'expected_absolute_distance_to_count_or_interval':math.fsum(distance(q,lo,hi)*dt for q,dt in parts)/60}
def main(candidate,validation):
    candidate=Path(candidate);validation=Path(validation)
    target=ROOT/'known_queue_diagnostic.json';assert not target.exists()
    # These four reports need only the completed Monday/Tuesday cells and two
    # extraMonday clocks; do not label the still-running full grid complete.
    assert (validation/'validation-started.json').exists()
    prepared=read(candidate/'frozen/prepared_capacity44_pair.json.gz');nodes=prepared['prepared']['common']['nodes']
    old=ANALYSIS/'field_observations_2026-11-09';new=ANALYSIS/'field_observations_2026-11-10'
    files=[old/'queue_admin_snu_1653.json',old/'queue_culture_1655.json',old/'queue_snu_gate_1703.json',new/'queue_admin_snu_1523.json']
    events=[]
    for i,p in enumerate(files):
        s=read(p)
        if i==3:
            count=s['people']['preferred_reported_outside_queue_count_including_observer'];band=[count,count];clock=s['reported_queue_join_time']
        else:
            band=s.get('reported_queue_people_range') or [s['reported_queue_people']]*2;clock=s['reported_time']
        if i in (0,3):indices=[n for n,row in enumerate(nodes) if row['route']=='shuttle-41841' and row['name']=='행정관']
        else:indices=[n for n,row in enumerate(nodes) if row.get('city') and row.get('stop_id')==s['stop_id']]
        assert len(indices)==1,(s['observation_id'],indices)
        hh,mm=map(int,clock.split(':'))
        events.append({'id':s['observation_id'],'day':'tue' if i==3 else 'mon','minute':clock,'second':hh*3600+mm*60,
                       'node':indices[0],'low':band[0],'high':band[1],
                       'mapping':s.get('stop_mapping_assumption','reported administration toSNU-station shuttle line'),
                       'source':str(p),'source_sha256':sha(p),'date_inferred':True})
    jobs=[]
    v11=ANALYSIS/'simulation_viewer_2026-11-07/peak_pair_correction_2026-11-10'
    for scenario in ('regular','peak'):
        for day in ('mon','tue'):
            jobs.append(('V11',scenario,day,v11/f'audit-{scenario}-{day}.json.gz'))
            folder=candidate/'runs/distribution_v8-combined-regular-mon/attempt_01' if scenario=='regular' and day=='mon' else validation/f'runs/distribution_v8-combined-{scenario}-{day}/attempt_01'
            if not folder.exists():folder=validation/f'runs/distribution_v8-combined-{scenario}-{day}/attempt_01'
            jobs.append(('prototype_V8',scenario,day,folder/f'audit-{scenario}-{day}.json.gz'))
    for kind in ('baseline','gate_reference'):
        jobs.append(('prototype_'+kind,'regular','mon',candidate/f'runs/{kind}-combined-regular-mon/attempt_01/audit-regular-mon.json.gz'))
    rows=[];sources=[]
    for name,scenario,day,p in jobs:
        assert p.exists(),p
        if name!='V11':
            checked=read(p.parent/'independent_analysis.json')
            assert checked['status']=='PASS_INTERNAL_INVARIANTS' and checked['audit_sha256']==sha(p)
        relevant=[e for e in events if e['day']==day];needed={e['node'] for e in relevant};delta={n:defaultdict(float) for n in needed}
        audit=read(p)
        for n,a,b,w,*rest in audit['waits']:
            if n not in needed:continue
            delta[n][a]+=w;delta[n][b]-=w
        del audit
        timelines={}
        for n,changes in delta.items():
            running=0.;timeline=[]
            for t,d in sorted(changes.items()):running+=d;timeline.append((t,running))
            assert abs(running)<1e-5
            timelines[n]=timeline
        sources.append({'model':name,'scenario':scenario,'day':day,'audit':str(p),'sha256':sha(p)})
        for event in relevant:
            r={'observation_id':event['id'],'model':name,'scenario':scenario,'weekday':day,'reported_minute':event['minute'],
               'node':event['node'],'stop':nodes[event['node']]['name'],'observed_low':event['low'],'observed_high':event['high']}
            r.update(stats(timelines[event['node']],event['second'],event['low'],event['high']));rows.append(r)
            if name=='V11' and scenario=='regular' and day=='tue':
                assert abs(r['uniform_minute_mean']-89.43304130823327)<1e-4,'Independent audit reconstruction must match the existing V11 minute diagnostic'
    with (ROOT/'known_queue_diagnostic.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
    result={'status':'DIAGNOSTIC_ONLY_NOT_EVALUABLE','observations':events,'rows':rows,'audit_sources':sources,
            'all_known_reports_compared':4,'independent_observations_for_final_selection':0,
            'time_rule':'Exact integral of physical waiting queue over uniform unknown second in reported minute; no best second or best scenario selected.',
            'third_and_new_report_uniform_timing_is_comparison_assumption':True,
            'old_record_initial_not_used_flags_do_not_override_later_V9_selection_use':True,
            'culture_direction_mapping_unconfirmed':True,'date_inferred_from_conversation_not_independent_confirmation':True,
            'new_observer_not_added_as_extra_model_mass':True,'no_coefficients_tuned_to_these_comparisons':True,
            'individual189_seconds_not_validated_by_queue_count_or_instantaneous_network_events':True}
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print('ALL_KNOWN_QUEUE_REPORTS_DIAGNOSED',len(rows),'NOT_EVALUABLE')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--candidate',required=True);p.add_argument('--validation',required=True);a=p.parse_args();main(a.candidate,a.validation)
