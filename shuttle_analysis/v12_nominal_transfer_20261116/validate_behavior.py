"""Physical audit is separate; verify student strategy and truthful diagnostic scopes."""
from pathlib import Path
import argparse,gzip,hashlib,json,math,collections
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');p.add_argument('--group',default='observations');a=p.parse_args();w=Path(a.candidate).resolve()
    out=w/(a.group+'-behavior-validation.json');assert not out.exists()
    v=read(w/(a.group+'-validation.json'));b=read(w/'frozen/prepared_capacity44_pair.json.gz');common=b['prepared']['common'];rows=[]
    config=read(w/'config.json');loyalty=read(w/'loyalty-invariant-check.json') if config.get('retain_released_mode_flexibility') else None
    if loyalty is not None:assert loyalty['status']=='PASS'
    did={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}
    for r in v['results']:
        c=r['case'];path=Path(r['source_directory'])/f"audit-{c['scenario']}-{did[c['day']]}.json.gz";assert sha(path)==r['audit_sha256'];data=read(path)
        returned=far=wrong=early_shuttle=gate_left=wrong_direction=changed_after_intermediate=0.;checked=0
        invalid_first_release_weight=0.;release_records=period_records=0
        vehicles={x['id']:x for x in data['vehicles']};requirements=data['prototype_config'].get('terminal_direction_requirements',{})
        # New explicit intent is stronger than inferring intent from the
        # last realized ride after a later transfer-to-walk decision.
        for visit in data['wait_audit']:
            periods=visit.get('eligibility_periods',[])
            if periods:
                assert abs(periods[0]['from']-visit['arrival'])<1e-5
                previous=set();last=-math.inf
                for period in periods:
                    services={tuple(x) for x in period['services']}
                    assert visit['arrival']-1e-5<=period['from']<=visit['end']+1e-5 and period['from']>=last
                    assert previous<=services
                    previous=services;last=period['from']
                assert previous=={tuple(x) for x in visit['eligibility']}
                period_records+=len(periods)-1
            release=visit.get('student_first_release')
            if release:
                release_records+=1;expected=release['expected_total_queue_wait_seconds']
                lawful=expected is None or expected>=release['patience']-1e-5 or release['age']>=release['patience']-1e-5 or (release['mode']=='city' and release['full_passes']>=2 and release['predicted_additional_passes']>=2)
                if not lawful:invalid_first_release_weight+=visit['weight']
            if visit['outcome']!='boarded':continue
            intent=visit.get('boarding_intent');assert intent is not None
            if periods:assert (intent['rid'],intent['board']) in {tuple(x) for x in periods[-1]['services']}
            dest=b['destination_keys'][str(visit['parent_id'])];rid=intent['rid'];allowed=requirements.get(dest,{}).get(rid)
            if allowed is None:continue
            direction=b['prepared']['routes'][rid]['stops'][intent['board']].get('direction')
            if direction not in allowed:
                if intent['planned_terminal']:wrong_direction+=visit['weight']
                else:changed_after_intermediate+=visit['weight']
        for t in data['legs']:
            visits=[];previous=None
            for l in t['legs']:
                if l[0]==1 and not (previous is not None and previous[0]==1 and previous[4]==l[4] and abs(previous[2]-l[1])<1e-5):visits.append(l[4])
                previous=l
            if len(visits)!=len(set(visits)):returned+=t['weight']
            if not t['unserved']:
                last=t['legs'][-1];dest=b['destination_keys'][str(t['parent_id'])]
                end=common['paths'][last[3]][-1];target=common['destinations'][dest]
                if math.hypot((end[0]-target[0])*111320,(end[1]-target[1])*88200)>2:wrong+=t['weight']
                if dest=='snu' and last[0]==0:
                    geometry=common['paths'][last[3]]
                    meters=sum(math.hypot((q[0]-p[0])*111320,(q[1]-p[1])*88200) for p,q in zip(geometry,geometry[1:]))
                    if meters>1000+5:far+=t['weight']
            checked+=1
        destinations={t['id']:b['destination_keys'][str(t['parent_id'])] for t in data['legs']}
        current_pressure_violations=0.
        for d in data['behavior_decisions']:
            if data['prototype_config'].get('review_requires_current_queue_pressure'):
                expected=d.get('student_expected_queue_wait_seconds')
                denial=(d.get('student_mode_before')=='city' and d['full_passes']>=data['prototype_config']['city_denial_trigger'] and d.get('student_predicted_additional_passes',0)>=data['prototype_config']['city_additional_pass_trigger'])
                if d.get('perceived_old_eta') is not None and expected is not None and expected<d['student_patience_seconds']-1e-5 and not denial:
                    current_pressure_violations+=d['weight']
            if data['prototype_config'].get('gate_is_final_fallback') and d['origin']==data['prototype_config']['gate_fallback_node'] and destinations[d['uid']]=='snu':gate_left+=d['weight']
            if d.get('student_mode_before')=='shuttle' and d['continuous_wait_seconds']<d['student_patience_seconds']-1e-5:
                # No-future-service escape can legitimately precede patience.
                expected=d.get('student_expected_queue_wait_seconds')
                if d['old_eta'] is not None and expected is not None and expected<d['student_patience_seconds']-1e-5:early_shuttle+=d['weight']
            if d.get('target') in d.get('student_visited_before',[]):returned+=d['weight']
        stats=data['policy_report']['student_strategy'];counter=stats['counts']
        opportunity=data.get('walking_opportunities_report');flow=opportunity['flow']
        assert abs(flow.get('intercept_attempt_weight',0)-flow.get('opportunistic_boarded_weight',0)-flow.get('resumed_walking_weight',0))<1e-6
        for e in data.get('enroute_events',[]):
            if e['action']!='approach_platform':continue
            original,prefix,suffix=[common['paths'][e[k]] for k in ('original_path','prefix_path','suffix_path')]
            assert original[0]==prefix[0] and prefix[-1]==suffix[0] and suffix[-1]==original[-1]
            assert e['extra_meters']<=80+1e-6 and e['lateral_meters']<=30+1e-6
            assert 0<=e['deadline']-e['ready']<=30+1e-6
        row={'case':c,'source_sha256':sha(path),'finished_fragments_checked':checked,'returned_stop_weight':returned,
          'far_final_station_walk_weight':far,'wrong_destination_weight':wrong,'shuttle_left_early_with_forecastable_service_weight':early_shuttle,
          'ordinary_snu_final_gate_departure_weight':gate_left,
          'physical_changes_without_current_queue_pressure_weight':current_pressure_violations,
          'wrong_terminal_service_direction_weight':wrong_direction,
          'opposite_branch_intermediate_then_rerouted_weight':changed_after_intermediate,
          'initial_loyalty_guard_check':loyalty['status'] if loyalty else 'legacy_context_rule',
          'current_shuttle_threshold_departures_scope':'Includes already-released flexibility. First-release context audited separately where exported; supplemental guard checks retained.',
          'exported_first_release_visit_records':release_records,'invalid_first_release_visit_weight':invalid_first_release_weight,
          'same_stop_eligibility_period_updates':period_records,'initial_trunk_checks':stats.get('initial_trunk_checks'),
          'invalid_incumbent_chain_count':counter.get('unexpected_invalid_incumbent_chain',0),
          'initial_profile_mass':sum(stats['initial_mode_weights'].values()),'physical_source_mass':r['scope']['all']['weight'],
          'all_recorded_max_continuous_wait_min':r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min'],
          'over20_episode_weight':r['extended_diagnostics']['all_recorded_time_over20_episode_weight'],'unserved_weight':r['unserved_trip_weight'],
          'walking_opportunities':opportunity,'student_strategy_counts':counter}
        assert abs(row['initial_profile_mass']-row['physical_source_mass'])<1e-6
        loyalty_pass=loyalty['status']=='PASS' if loyalty else early_shuttle<1e-7
        row['behavior_gate_passed']=returned<1e-7 and far<1e-7 and wrong<1e-7 and loyalty_pass and gate_left<1e-7 and wrong_direction<1e-7 and row['invalid_incumbent_chain_count']==0 and invalid_first_release_weight<1e-7 and current_pressure_violations<1e-7
        if data['prototype_config'].get('initial_trunk_preservation'):assert stats['initial_trunk_checks'].get('violation_weight',0)==0
        rows.append(row);print('BEHAVIOR_AUDITED',c['case'],row['behavior_gate_passed'],'returned',returned,'far',far,'wrong',wrong,'early',early_shuttle,flush=True)
    result={'release_id':w.name,'group':a.group,'status':'PASS_STUDENT_BEHAVIOR_GATES' if all(r['behavior_gate_passed'] for r in rows) else 'BEHAVIOR_GATE_FAILED',
      'cases':rows,'direction_audit_scope':'Explicit planned_terminal flag at every actual boarding; forbidden final directions separated from allowed intermediate boardings.',
      'over20_is_diagnostic_not_deleted':True,'production_writes':False,'new_date_accuracy':'NOT_EVALUATED'}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(result['status'],flush=True)
if __name__=='__main__':main()
