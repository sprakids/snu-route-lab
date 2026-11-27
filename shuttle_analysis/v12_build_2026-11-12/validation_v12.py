"""Post-run evidence coverage, field constraints and journey tails; no refitting."""
from pathlib import Path
from collections import defaultdict,Counter
from datetime import datetime,timezone,timedelta
import argparse,bisect,csv,gzip,hashlib,json,math

ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent;KST=timezone(timedelta(hours=9))
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists(),f'Preserve prior result: {p}'
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
def csvout(p,rows):
    assert rows and not p.exists()
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
def minute_stats(points,start,low,high):
    end=start+60;times=[r[0] for r in points];k=bisect.bisect_right(times,start)-1
    q=points[k][1] if k>=0 else 0.;at=start;pieces=[]
    for t,value,*_ in points[k+1:]:
        if t>=end:break
        if t>at:pieces.append((q,t-at))
        at=t;q=value
    if at<end:pieces.append((q,end-at))
    assert abs(sum(t for q,t in pieces)-60)<1e-6
    return {'uniform_minute_mean':math.fsum(q*t for q,t in pieces)/60,
       'minute_minimum':min(q for q,t in pieces),'minute_maximum':max(q for q,t in pieces),
       'expected_absolute_distance_to_count_or_interval':math.fsum(max(low-q,0.,q-high)*t for q,t in pieces)/60}

def field_events(release,common):
    base=release/'evidence';old=base/'field_observations_2026-11-09'
    paths=[old/'queue_admin_snu_1653.json',old/'queue_culture_1655.json',old/'queue_snu_gate_1703.json',
      base/'field_observations_2026-11-10/queue_admin_snu_1523.json']
    events=[];latest=None
    for i,p in enumerate(paths):
        s=read(p);latest=s if i==3 else latest
        minute=s['reported_queue_join_time'] if i==3 else s['reported_time']
        band=[s['people']['preferred_reported_outside_queue_count_including_observer']]*2 if i==3 else s.get('reported_queue_people_range') or [s['reported_queue_people']]*2
        nodes=[n for n,r in enumerate(common['nodes']) if r.get('route')=='shuttle-41841' and r.get('name')=='행정관'] if i in (0,3) else [n for n,r in enumerate(common['nodes']) if r.get('city') and r.get('stop_id')==s['stop_id']]
        assert len(nodes)==1;hh,mm=map(int,minute.split(':'))
        events.append({'observation_id':s['observation_id'],'day':'화' if i==3 else '월','minute':minute,'second':hh*3600+mm*60,
          'node':nodes[0],'stop':common['nodes'][nodes[0]]['name'],'low':band[0],'high':band[1],
          'source':str(p.relative_to(release)),'source_sha256':sha(p),'independent_holdout':False,
          'time_rule':'uniform unknown second in reported minute; third and Tuesday treatment are comparison assumptions'})
    assert latest['people']['preferred_reported_outside_queue_count_including_observer']==67
    assert latest['durations']['reported_pure_queue_wait_seconds']==189
    assert latest['durations']['reported_seconds_from_end_of_queue_wait_to_departure']==30
    return events,latest

def historical_context(release):
    inventory=read(release/'frozen/historical_evidence_context.json');out=[]
    for dataset in inventory['datasets']:
        out.append({'id':dataset['id'],'unit':dataset['unit'],'direct_demand_input':dataset.get('direct_demand_input'),
          'event_period':dataset.get('event_period'),'source_files':dataset.get('source_files',[]),
          'supported_use':dataset.get('supported_use'),'cautions':dataset.get('cautions',[]),
          'v12_usage':'validation of source grain/coverage and contextual scale only; not extra arrivals or numeric bus occupancy'})
    return out

def main(release):
    release=Path(release).resolve();validation=read(release/'validation_reference_corrected.json');assert validation['cases']==10
    assert validation['invariant_audits']=='PASS';target=release/'evidence_validation_final.json';assert not target.exists()
    bundle=read(release/'frozen/prepared_capacity44_pair.json.gz');common=bundle['prepared']['common'];events,individual=field_events(release,common)
    rows=[];tails=[];half=defaultdict(list);loops=[];consumption=[];named=[]
    for result in validation['results']:
        case=result['case'];folder=Path(result['source_directory']);did={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}[case['day']]
        audit_path=folder/f'audit-{case["scenario"]}-{did}.json.gz';assert sha(audit_path)==result['audit_sha256']
        data=read(folder/f'{case["scenario"]}-{did}.json.gz')
        for event in events:
            if event['day']!=case['day']:continue
            rows.append({'model':'V12','scenario':case['scenario'],'weekday':did,'observation_id':event['observation_id'],
              'reported_minute':event['minute'],'stop':event['stop'],'observed_low':event['low'],'observed_high':event['high'],
              **minute_stats(data['queue_timeline'][event['node']],event['second'],event['low'],event['high'])})
        for node,r in enumerate(common['nodes']):
            if str(r.get('ars','')) not in ('21269','21299','21270','21298'):continue
            pts=data['queue_timeline'][node];pre=[p for p in pts if p[0]<40800];window=([[40800,pre[-1][1]]] if pre else [])+[p for p in pts if 40800<=p[0]<83400]
            peak=max(window,key=lambda p:p[1],default=[None,0.])
            named.append({'weekday':case['day'],'scenario':case['scenario'],'stop':r['name'],'ars':r['ars'],
              'window_max_queue':peak[1],'peak_at':peak[0],'above40_recollection_reference':peak[1]>40})
        del data
        quant=result['extended_diagnostics']['finished_trip_quantiles'];ref=result['r10_reference']['extended_diagnostics']['finished_trip_quantiles']
        for metric in ('walk_min','cumulative_wait_min','total_min','changes'):
            tails.append({'weekday':case['day'],'scenario':case['scenario'],'metric':metric,
              **{'r10_'+k:val for k,val in ref[metric].items()},**{'v12_'+k:val for k,val in quant[metric].items()}})
        consumption.append({'case':case['case'],'evidence_queries':result['policy_report']['empirical_evidence']})
        audit=read(audit_path);revisit_weight=total_weight=0.;max_changes=0;worst=None
        for trip in audit['legs']:
            w=trip['weight'];total_weight+=w;max_changes=max(max_changes,len(trip['history']))
            if not trip['unserved'] and (worst is None or trip['finish_time']-trip['start']>worst['finish_time']-worst['start']):worst=trip
            visits=[];pending=None
            def record(p):
                if p is None:return
                node,a,b=p
                if trip['unserved']:b=min(b,83400)
                if a<83400 and b>40800 and b>a:half[(case['day'],case['scenario'],node,int(a//1800)*1800)].append(((b-a)/60,w))
            for leg in trip['legs']:
                if leg[0]==1:
                    if pending and pending[0]==leg[4] and abs(pending[2]-leg[1])<1e-5:pending[2]=leg[2]
                    else:
                        record(pending);pending=[leg[4],leg[1],leg[2]];visits.append(leg[4])
                else:record(pending);pending=None
            record(pending)
            if len(set(visits))<len(visits):revisit_weight+=w
        loops.append({'weekday':case['day'],'scenario':case['scenario'],'input_trip_weight':total_weight,
          'same_stop_revisit_trip_weight':revisit_weight,'revisit_does_not_itself_prove_invalid_route':True,'maximum_changes':max_changes,
          'worst_total_min':(worst['finish_time']-worst['start'])/60,'worst_trip_weight':worst['weight'],
          'worst_changes':len(worst['history']),'worst_history':worst['history']})
        del audit
        print('V12_EVIDENCE_VALIDATION_CELL',case['case'],flush=True)
    assert len(rows)==8 and len(tails)==40 and len(named)==40
    # Existing diagnostics are preserved; no scenario/second chosen to optimize fit.
    oldrows=list(csv.DictReader((ANALYSIS/'prototype_review_261110193823/known_queue_diagnostic.csv').open(encoding='utf-8-sig')))
    compare=[]
    for r in oldrows:
        if r['model'] not in ('V11','prototype_V8'):continue
        compare.append({k:r[k] for k in rows[0]})
    compare.extend(rows);assert len(compare)==24
    csvout(release/'field_queue_comparison_final.csv',compare);csvout(release/'journey_tails_final.csv',tails);csvout(release/'named_stop_queues_final.csv',named)
    halfrows=[]
    for (day,scenario,node,start),values in sorted(half.items()):
        mass=math.fsum(w for t,w in values)
        halfrows.append({'weekday':day,'scenario':scenario,'node':node,'stop':common['nodes'][node]['name'],
          'queue_entry_half_hour':start,'episode_weight':mass,'mean_continuous_wait_min':math.fsum(t*w for t,w in values)/mass,
          'maximum_continuous_wait_min':max(t for t,w in values),'over20_episode_weight':math.fsum(w for t,w in values if t>20+1e-7)})
    csvout(release/'half_hour_waits_final.csv',halfrows)
    history=historical_context(release);rule=read(release/'evidence/collected_data_review_2026-11-12/v12_support/future_holdout_rule.json')
    usage={'schema':'v12_field_observation_usage_ledger','role':'diagnostic constraints only, no fitting or extra demand',
      'observations':events,'individual_wait':{'queue_people':67,'individual_samples':1,'queue_wait_seconds':189,'post_boarding_seconds':30,
        'combined_seconds':219,'source_schema':individual['schema'],'network_validation_status':'NOT_EVALUABLE',
        'reason':'Global arrival/boarding/departure still coalesced; no observed exact bus arrival or fleet-wide boarding service distribution',
        'micro_model_interface':'dwell.py simulate_batch retains two independent44-seat vehicles; micro scenarios are not fitted/validated global dwell'},
      'snapshot_date_and_culture_direction_uncertainties_preserved':True,'no_best_second_selected':True}
    save(release/'field_observation_usage_ledger_final.json',usage)
    inventory=read(release/'evidence_inventory_initial.json')
    context_sources=[
      ('course_schedule_and_enrollment_base','course_demand_2026-11-06/sources/source_register.json','runtime_existing_baseline',
       'frozen/prepared_capacity44_pair.json.gz and prepare.py; schedule/enrollment-derived weighted departures, not observed unique homeward students'),
      ('dorm_and_historical_destination_evidence','collaboration/research_inputs.json','validation_context',
       'User-selected dorm ratio and historical destination scenarios are not current measured Gwanak shares; questionnaires are not response results'),
      ('library_observation_source_scope','library_flow_research_2026-11-08/source_register.json','validation_context',
       'Annual facility use and loans are not daily exits or unique students; no added queue arrivals'),
      ('library_detour_scenario_scope','library_detour_estimates_2026-11-08/result_summary.json','validation_context',
       'Conditional detour scenario preserved separately; do not add scenario mass to inherited demand')]
    context_root=release/'validation_sources_final';context_root.mkdir()
    for name,relative,role,meaning in context_sources:
        source=ANALYSIS/relative;destination=context_root/(name+'.json');destination.write_bytes(source.read_bytes())
        inventory['items'].append({'id':name,'category':'baseline_demand_and_earlier_context','source':str(source),'source_sha256':sha(source),
          'snapshot':str(destination.relative_to(release)),'role':role,'consumer':meaning,'limitations':'Reference scope retained; not a new independent queue observation'})
    for item in inventory['items']:
        item['integration_status']='CONNECTED_TO_VALIDATION' if item['role'].startswith('validation') else 'CONNECTED_TO_RUNTIME'
        item['validated_consumer']='validation_v12.py' if item['role'].startswith('validation') else item['consumer']
    for name,why,fallback in [
      ('shuttle_actual_dispatch_distribution','No continuous BUSIN archive; schematic positions are not GPS','Official timetable plus explicitly conditional44-seat/peak-pair scenario'),
      ('numeric_external_city_occupancy','Ordinal grades/full flags do not identify exact onboard or remaining seats','Physical model has simulated campus demand; external numeric background remains unidentified'),
      ('village_crowd_grades','API valid congestion grades absent on two village routes','None and clearly labeled simulated-load scenario, never observed empty'),
      ('date_hour_individual_queue_arrivals','Month-hour and date-total boardings are admitted events of different grain','Historical contextual validation, not extra arrivals'),
      ('fully_extracted_campus_card_trips','DC/DD/DX full campus extraction incomplete; previews are not completed journeys','Preserved archive and verified schema/date metadata only'),
      ('global_boarding_dwell_distribution','Single189s+30s report cannot identify full-fleet service dynamics','Latest one-person constraints; global event approximation remains NOT_EVALUABLE')]:
        inventory['items'].append({'id':name,'category':'unavailable_or_not_identifiable','role':'not_applied',
          'integration_status':'UNAVAILABLE_NOT_APPLIED','consumer':None,'reason':why,'declared_fallback':fallback})
    inventory.update(finalized_at=datetime.now(KST).isoformat(),runtime_consumption=consumption,
      field_usage_ledger='field_observation_usage_ledger_final.json',historical_context=history,future_evaluation_rule=rule,
      no_numeric_grade_occupancy_conversion=True,queue_accuracy='NOT_EVALUABLE',production_replacement_allowed=False)
    save(release/'evidence_inventory_final.json',inventory)
    save(target,{'status':'COMPLETED_EVIDENCE_DIAGNOSTICS_NOT_FIELD_ACCURACY_PROOF','events':events,'field_rows':rows,
      'tails':tails,'route_revisits':loops,'named_stop_above40_reference_cells':sum(r['above40_recollection_reference'] for r in named),
      'half_hour_rows':len(halfrows),'runtime_consumption':consumption,'historical_context':history,
      'individual_wait_validation':'NOT_EVALUABLE','future_rule':rule,'production_writes':False})
    print('V12_EVIDENCE_VALIDATION_DONE',len(compare),len(halfrows),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--release',required=True);a=p.parse_args();main(a.release)
