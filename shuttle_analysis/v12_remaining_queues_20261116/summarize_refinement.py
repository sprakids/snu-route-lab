"""Read immutable candidate ledgers; compare matching cases, never fit or simulate."""
from pathlib import Path
from collections import defaultdict,Counter
import argparse,csv,gzip,hashlib,importlib.util,json,math,sys
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent;PARENT=ANALYSIS/'261116010854'
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists(),str(p)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
def csvout(p,rows):
    assert not p.exists() and rows,str(p)
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
def matching(rows,case):
    found=[r for r in rows if all(r['case'][k]==case[k] for k in ('day','scenario','seed','operations'))]
    assert len(found)==1,(case,len(found));return found[0]
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');p.add_argument('--group',default='grid');args=p.parse_args()
    work=Path(args.candidate).resolve();validation=read(work/f'{args.group}-validation.json');rows=validation['results']
    spec=importlib.util.spec_from_file_location('old_validation_helpers',ANALYSIS/'v12_build_2026-11-12/validation_v12.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    frozen_bundle=read(work/'frozen/prepared_capacity44_pair.json.gz');common=frozen_bundle['prepared']['common'];nodes=common['nodes']
    config=read(work/'config.json');physical=read(next(work.glob('physical_paths_*.json.gz')))
    release_map=read(work/'frozen/class_release_map.json.gz') if config.get('cohort_release_lag_scale',1.)!=1. else None
    observations,individual=helper.field_events(work,common)
    before=read(PARENT/'grid-validation.json')['results']
    tails=[];stops=[];fields=[];half=defaultdict(list);all_half=defaultdict(list);all_waits=defaultdict(list);cases=[]
    for result in rows:
        case=result['case'];ref=matching(before,case);folder=Path(result['source_directory'])
        did={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}[case['day']]
        audit_path=folder/f"audit-{case['scenario']}-{did}.json.gz";assert sha(audit_path)==result['audit_sha256']
        data=read(folder/f"{case['scenario']}-{did}.json.gz")
        for event in observations:
            if event['day']==case['day']:
                fields.append({'model':work.name,'scenario':case['scenario'],'weekday':did,'observation_id':event['observation_id'],'case':case['case'],
                  'reported_minute':event['minute'],'stop':event['stop'],'observed_low':event['low'],'observed_high':event['high'],
                  **helper.minute_stats(data['queue_timeline'][event['node']],event['second'],event['low'],event['high'])})
        named=[]
        for n,node in enumerate(nodes):
            if str(node.get('ars','')) not in ('21269','21299','21270','21298'):continue
            pts=data['queue_timeline'][n];prior=[x for x in pts if x[0]<=40800]
            values=[[40800,prior[-1][1] if prior else 0.]]+[x for x in pts if 40800<x[0]<83400]
            maximum=max(values,key=lambda x:x[1])
            above=run=max_run=0.
            ordered=values+[[83400,0.]]
            for left,right in zip(ordered,ordered[1:]):
                seconds=max(0.,right[0]-left[0])
                if left[1]>40:above+=seconds;run+=seconds;max_run=max(max_run,run)
                else:run=0.
            named.append({'node':n,'name':node['name'],'ars':node['ars'],'maximum_queue':maximum[1],'at':maximum[0],
              'minutes_above40_recollection_reference':above/60,'longest_spell_above40_minutes':max_run/60})
        del data
        for metric in ('walk_min','cumulative_wait_min','total_min','changes'):
            tails.append({'case':case['case'],'day':case['day'],'scenario':case['scenario'],'metric':metric,
              **{'parent_'+k:v for k,v in ref['extended_diagnostics']['finished_trip_quantiles'][metric].items()},
              **{'repair_'+k:v for k,v in result['extended_diagnostics']['finished_trip_quantiles'][metric].items()}})
        for stop in result['stop_waits']:stops.append({'case':case['case'],'weekday':case['day'],'scenario':case['scenario'],**stop})
        a=read(audit_path);finished=[t for t in a['legs'] if not t['unserved']]
        worst=max(finished,key=lambda t:t['finish_time']-t['start']);loops=0.;over90=0.;over120=0.;hist=Counter();bad_eta=0.
        initial_path_checks=0
        source_plans={str(p[0]):p for p in frozen_bundle['prepared']['plans'][case['day']]}
        preserve=config.get('initial_assignment_policy')=='preserve_source_mixture' and case.get('config_overrides',{}).get('initial_assignment_policy')!='free_choice'
        for trip in a['legs']:
            if preserve:
                source_plan=source_plans[str(trip['parent_id'])];path_id=source_plan[5][0]
                if physical[path_id]['seconds']>1e-7:
                    first=trip['legs'][0]
                    assert first[0]==0 and first[3]==path_id,(case,trip['id'],'initial source path changed')
                    expected_start=source_plan[4]
                    if release_map is not None:
                        end=release_map['events'][(trip['parent_id']-1)//48]['class_end_seconds']
                        expected_start=end+config['cohort_release_lag_scale']*(expected_start-end)
                    assert abs(first[1]-expected_start)<1e-5
                    initial_path_checks+=1
            w=trip['weight'];hist[len(trip['history'])]+=w
            if not trip['unserved']:
                duration=trip['finish_time']-trip['start']
                if duration>5400:over90+=w
                if duration>7200:over120+=w
            visits=[];pending=None
            def record(item):
                if item is None:return
                n,start,end=item
                if trip['unserved']:end=min(end,83400)
                if end>start:
                    all_half[case['case'],case['day'],case['scenario'],n,int(start//1800)*1800].append(((end-start)/60,w))
                    all_waits[case['case'],case['day'],case['scenario'],n].append(((end-start)/60,w))
                if start<83400 and end>40800 and end>start:half[case['case'],case['day'],case['scenario'],n,int(start//1800)*1800].append(((end-start)/60,w))
            for leg in trip['legs']:
                if leg[0]==1:
                    if pending and pending[0]==leg[4] and abs(pending[2]-leg[1])<1e-5:pending[2]=leg[2]
                    else:record(pending);pending=[leg[4],leg[1],leg[2]];visits.append(leg[4])
                else:record(pending);pending=None
            record(pending)
            if len(set(visits))<len(visits):loops+=w
        changes=a['behavior_decisions']
        for change in changes:
            if change['old_eta'] is not None and change['new_eta']>change['old_eta']+300:bad_eta+=change['weight']
        case_row={'case':case,'source_directory':str(folder),'audit_sha256':sha(audit_path),
          'maximum_continuous_wait_min':result['maximum_continuous_wait_min'],'over20_episode_weight':result['over20_weight'],
          'all_recorded_diagnostics':result['extended_diagnostics'],'unserved_trip_weight':result['unserved_trip_weight'],
          'late_finished_weight':result['late_finished_weight'],'same_stop_revisit_trip_weight':loops,
          'over90_total_trip_weight':over90,'over120_total_trip_weight':over120,'change_distribution':dict(sorted(hist.items())),
          'switches_over5min_later_than_recorded_comparator_weight':bad_eta,
          'comparator_scope':'For boarding_joint_choice old_eta is the wait alternative excluding the arriving bus, not boarding that bus; other reviews use incumbent first-boardable projection. Not a unified board-versus-walk regret measure.',
          'declines_by_action':dict(Counter(x['action'] for x in a['boarding_choices'])),
          'named_stop_40_recollection_comparison':named,
          'worst_trip':{k:worst[k] for k in ('id','parent_id','weight','start','finish_time','history')},
          'parent_reference_maximum_wait_min':ref['maximum_continuous_wait_min'],
          'parent_reference_audit_sha256':ref['audit_sha256'],'preserved_initial_access_path_trip_fragment_checks':initial_path_checks}
        cases.append(case_row)
        print('SUMMARIZED',case['case'],flush=True)
    original=[{**r,'case':r.get('case','preserved-reference')} for r in csv.DictReader((PARENT/'grid-field-comparison.csv').open(encoding='utf-8-sig'))]
    csvout(work/f'{args.group}-field-comparison.csv',original+fields)
    csvout(work/f'{args.group}-journey-comparison.csv',tails);csvout(work/f'{args.group}-all-stops.csv',stops)
    halfrows=[]
    for (cid,day,scenario,n,start),values in sorted(half.items()):
        mass=math.fsum(w for t,w in values)
        halfrows.append({'case':cid,'day':day,'scenario':scenario,'node':n,'stop':nodes[n]['name'],'queue_entry_half_hour':start,
          'episode_weight':mass,'mean_wait_min':math.fsum(t*w for t,w in values)/mass,
          'max_wait_min':max(t for t,w in values),'over20_episode_weight':math.fsum(w for t,w in values if t>20+1e-7)})
    csvout(work/f'{args.group}-half-hour-waits.csv',halfrows)
    allstoprows=[];allhalfrows=[]
    for result in rows:
        c=result['case'];case_max=case_over=0.
        for n,node in enumerate(nodes):
            values=all_waits[c['case'],c['day'],c['scenario'],n];mass=math.fsum(w for t,w in values)
            maximum=max((t for t,w in values),default=0.);over=math.fsum(w for t,w in values if t>20+1e-7)
            case_max=max(case_max,maximum);case_over+=over
            allstoprows.append({'case':c['case'],'weekday':c['day'],'scenario':c['scenario'],'node':n,'stop':node['name'],'ars':node.get('ars',''),
                'episode_weight':mass,'mean_wait_min':math.fsum(t*w for t,w in values)/mass if mass else None,'max_wait_min':maximum,'over20_episode_weight':over,
                'scope':'all recorded times; consecutive waits at same stop merged; unserved censored at simulation end'})
        assert abs(case_max-result['extended_diagnostics']['all_recorded_time_max_continuous_wait_min'])<1e-6
        assert abs(case_over-result['extended_diagnostics']['all_recorded_time_over20_episode_weight'])<1e-6
    for (cid,day,scenario,n,start),values in sorted(all_half.items()):
        mass=math.fsum(w for t,w in values)
        allhalfrows.append({'case':cid,'day':day,'scenario':scenario,'node':n,'stop':nodes[n]['name'],'queue_entry_half_hour':start,
            'queue_entry_time_kst':f'{start//3600:02d}:{start%3600//60:02d}',
            'episode_weight':mass,'mean_wait_min':math.fsum(t*w for t,w in values)/mass,'max_wait_min':max(t for t,w in values),
            'over20_episode_weight':math.fsum(w for t,w in values if t>20+1e-7)})
    csvout(work/f'{args.group}-all-recorded-stops.csv',allstoprows)
    csvout(work/f'{args.group}-all-recorded-half-hour-waits.csv',allhalfrows)
    result={'release_id':work.name,'parent':PARENT.name,'scope':'same weighted demand, supply and seed; not independent field validation',
      'group':args.group,'cases':cases,'source_group_sha256':sha(work/f'{args.group}-validation.json'),
      'all_invariant_audits_pass':all(r['status']=='PASS_INTERNAL_INVARIANTS' for r in rows),
      'all_continuous_waits_under20':all(r['over20_weight']<1e-7 and r['extended_diagnostics']['all_recorded_time_over20_episode_weight']<1e-7 for r in rows),
      'unserved_trip_weight':math.fsum(r['unserved_trip_weight'] for r in rows),'half_hour_rows':len(halfrows),'stop_rows':len(stops),
      'all_recorded_stop_rows':len(allstoprows),'all_recorded_half_hour_rows':len(allhalfrows),
      'historical_queue_observations':observations,'pristine_holdout_dates':[],'production_replacement_allowed':False}
    save(work/f'{args.group}-diagnostics.json',result)
    print('SUMMARY_COMPLETE',work.name,args.group,'all_under20',result['all_continuous_waits_under20'],flush=True)
if __name__=='__main__':main()
