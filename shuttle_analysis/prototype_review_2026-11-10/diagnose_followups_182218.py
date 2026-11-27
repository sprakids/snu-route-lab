"""Private audit ledger: every long physical queue episode in completed prototypes."""
from pathlib import Path
from collections import defaultdict
import bisect,csv,gzip,json,math
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent

def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def hms(t):
    return f'{int(t//3600):02}:{int(t//60)%60:02}:{t%60:06.3f}'
def prefix(values):
    values=sorted(values);return [x[0] for x in values],[0.,*__import__('itertools').accumulate(x[1] for x in values)]
def total(index,a,b):
    times,mass=index;return mass[bisect.bisect_right(times,b)]-mass[bisect.bisect_left(times,a)]
def main():
    assert (ANALYSIS/'prototype_validation_261110182218/validation.json').exists(),'Do not label an incomplete grid as complete'
    roots=[ANALYSIS/'prototype_followup_261110175338',ANALYSIS/'prototype_followup_261110180529',ANALYSIS/'prototype_followup_261110181553',ANALYSIS/'prototype_validation_261110182218']
    output=ROOT/'long_wait_episodes_followups_182218.csv';assert not output.exists(),'Preserve the existing ledger; choose a new output version when inputs change'
    count=0;weight=0.;cases=[];writer=None
    with output.open('w',encoding='utf-8-sig',newline='') as stream:
        for work in roots:
            bundle=read(work/'frozen/prepared_capacity44_pair.json.gz');common=bundle['prepared']['common']
            for case in read(work/'experiment_lock.json')['pilot_cases']:
                attempt='attempt_04' if work.name=='prototype_model_2026-11-10' else 'attempt_01'
                folder=work/'runs'/case['case']/attempt
                if not (folder/'result.json').exists():continue
                did={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}[case['day']];s=case['scenario']
                audit=read(folder/f'audit-{s}-{did}.json.gz');data=read(folder/f'{s}-{did}.json.gz')
                parents={p[0]:p for p in bundle['prepared']['plans'][case['day']]};metas=defaultdict(list);declines=defaultdict(list);events=defaultdict(list)
                incoming=defaultdict(list);boarded=defaultdict(list);switched=defaultdict(list)
                for m in audit['wait_audit']:metas[m['id']].append(m)
                for r in audit.get('boarding_choices',[]):declines[r['uid']].append(r)
                for e in audit['events']:events[e[1],e[11],e[12]].append(e)
                for n,a,b,w,*rest in audit['waits']:
                    incoming[n].append((a,w))
                    if rest[-1]=='boarded':boarded[n].append((b,w))
                    elif rest[-1]=='switched':switched[n].append((b,w))
                incoming={n:prefix(v) for n,v in incoming.items()};boarded={n:prefix(v) for n,v in boarded.items()};switched={n:prefix(v) for n,v in switched.items()}
                lookup={key:([e[0] for e in values],values) for key,values in events.items()}
                case_count=0;case_weight=0.
                for trip in audit['legs']:
                    pending=None;episodes=[]
                    for leg in trip['legs']:
                        if leg[0]==1:
                            if pending and pending[0]==leg[4] and abs(pending[2]-leg[1])<1e-5:pending[2]=leg[2]
                            else:
                                if pending:episodes.append(pending)
                                pending=[leg[4],leg[1],leg[2]]
                        else:
                            if pending:episodes.append(pending);pending=None
                    if pending:episodes.append(pending)
                    for n,a,b in episodes:
                        b=min(b,83400.)
                        if a>=83400 or b<=40800 or b-a<=1200.000001:continue
                        uid=trip['id'];parent=trip.get('parent_id',uid);plan=parents[parent]
                        matched=[m for m in metas[uid] if m['node']==n and m['arrival']>=a-1e-5 and m['end']<=b+1e-5]
                        services={tuple(service) for m in matched for service in m['eligibility']};ready=min((m['ready'] for m in matched),default=a+20)
                        passed=[];preparation_misses=0
                        for rid,k in services:
                            times,values=lookup.get((n,rid,k),([],[]));lo=bisect.bisect_left(times,a);hi=bisect.bisect_right(times,b)
                            for e in values[lo:hi]:
                                if e[0]<ready-1e-7:preparation_misses+=1
                                else:passed.append(e)
                        free=[e[3]-e[4]+e[5] for e in passed]
                        timeline=data['queue_timeline'][n];times=[r[0] for r in timeline];lo=bisect.bisect_right(times,a)-1;hi=bisect.bisect_right(times,b)
                        q0=timeline[lo][1] if lo>=0 else 0.;qmax=max([q0,*[r[1] for r in timeline[max(0,lo+1):hi]]])
                        history=[h for h in trip['history'] if h[0]<=a+1e-6]
                        node=common['nodes'][n]
                        row={'candidate':work.name,'case':case['case'],'weekday':case['day'],'scenario':s,'synthetic_uid':uid,'parent_trip_id':parent,
                            'weight':trip['weight'],'origin_building':plan[1],'destination':plan[2],'node':n,'stop':node['name'],'stop_id':node.get('stop_id'),'ars':node.get('ars'),
                            'arrival_service_second':a,'ready_service_second':ready,'leave_service_second':b,'arrival_hms':hms(a),'leave_hms':hms(b),'continuous_wait_min':(b-a)/60,
                            'queue_at_arrival_model_weight':q0,'max_queue_in_episode_model_weight':qmax,
                            'physical_stop_inflow_visit_weight':total(incoming.get(n,([], [0.])),a,b),
                            'local_boarding_weight':total(boarded.get(n,([], [0.])),a,b),'walk_away_visit_weight':total(switched.get(n,([], [0.])),a,b),
                            'compatible_service_events_after_ready':len(passed),'services_passed_during_preparation':preparation_misses,
                            'model_free_seats_after_alighting_min':min(free,default=None),'model_free_seats_after_alighting_max':max(free,default=None),
                            'model_free_seats_after_alighting_mean':math.fsum(free)/len(free) if free else None,
                            'personal_full_passes_seen':max((m.get('full_passes_seen',0) for m in matched),default=0),
                            'voluntary_boarding_declines':sum(r['node']==n and a<=r['time']<=b for r in declines[uid]),
                            'route_changes_before_queue':len(history),'route_change_history_before_queue':json.dumps(history,ensure_ascii=False,separators=(',',':')),
                            'compatible_services':json.dumps(sorted(services),separators=(',',':')),
                            'episode_censored_at_window_end':any(m['outcome']=='unserved' and abs(m['end']-83400)<1e-6 for m in matched),'trip_unserved':trip['unserved']}
                        if writer is None:writer=csv.DictWriter(stream,list(row));writer.writeheader()
                        writer.writerow(row);count+=1;case_count+=1;weight+=trip['weight'];case_weight+=trip['weight']
                cases.append({'candidate':work.name,'case':case['case'],'rows':case_count,'over20_weight':case_weight})
                print('DIAGNOSED',work.name,case['case'],case_count,flush=True)
    result={'status':'COMPUTED_PRIVATE_DIAGNOSTIC','rows':count,'weighted_episode_sum_across_distinct_scenarios':weight,
        'not_unique_people_or_independent_observations':True,'cases':cases,'time_basis':'scenario service-day seconds; reported clocks are simulated, not observed',
        'model_free_seats_not_observed_external_occupancy':True,'flow_interval':'inclusive episode endpoints; visits/boardings/walk-aways are separate weighted events',
        'censor_and_preparation_preserved':True}
    (ROOT/'long_wait_episodes_followups_182218.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print('ALL_DIAGNOSTICS_DONE',count)

if __name__=='__main__':main()
