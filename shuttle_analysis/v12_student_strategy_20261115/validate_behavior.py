"""Physical audit is separate; verify student strategy and truthful diagnostic scopes."""
from pathlib import Path
import argparse,gzip,hashlib,json,math,collections
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');p.add_argument('--group',default='observations');a=p.parse_args();w=Path(a.candidate).resolve()
    out=w/(a.group+'-behavior-validation.json');assert not out.exists()
    v=read(w/(a.group+'-validation.json'));b=read(w/'frozen/prepared_capacity44_pair.json.gz');common=b['prepared']['common'];rows=[]
    did={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}
    for r in v['results']:
        c=r['case'];path=Path(r['source_directory'])/f"audit-{c['scenario']}-{did[c['day']]}.json.gz";assert sha(path)==r['audit_sha256'];data=read(path)
        returned=far=wrong=early_shuttle=gate_left=wrong_direction=changed_after_intermediate=0.;checked=0
        vehicles={x['id']:x for x in data['vehicles']};requirements=data['prototype_config'].get('terminal_direction_requirements',{})
        for t in data['legs']:
            visits=[];previous=None
            for l in t['legs']:
                if l[0]==1 and not (previous is not None and previous[0]==1 and previous[4]==l[4] and abs(previous[2]-l[1])<1e-5):visits.append(l[4])
                previous=l
            if len(visits)!=len(set(visits)):returned+=t['weight']
            if not t['unserved']:
                last=t['legs'][-1];dest=b['destination_keys'][str(t['parent_id'])]
                last_ride=next((l for l in reversed(t['legs']) if l[0]==3),None)
                if last_ride is not None:
                    vehicle=vehicles[last_ride[6]];rid=vehicle['rid'];allowed=requirements.get(dest,{}).get(rid)
                    if allowed is not None:
                        indices=[i for i,time in enumerate(vehicle['times']) if abs(time-last_ride[1])<1e-5]
                        assert len(indices)==1,(rid,last_ride[1],indices)
                        direction=b['prepared']['routes'][rid]['stops'][indices[0]].get('direction')
                        if direction not in allowed:
                            alights=[i for i,time in enumerate(vehicle['times']) if abs(time-last_ride[2])<1e-5];assert len(alights)==1
                            stop=b['prepared']['routes'][rid]['stops'][alights[0]]
                            later_change=any(h[0]>=last_ride[2]-1e-5 for h in t['history'])
                            # An intended transfer can later become a walk. It
                            # must not be relabeled a forbidden direct ride.
                            # Still flag any opposite-branch ride all the way
                            # to the actual Daehak stop, even with a later edit.
                            if not later_change or (dest=='daehak' and str(stop.get('ars'))=='21157'):wrong_direction+=t['weight']
                            else:changed_after_intermediate+=t['weight']
                end=common['paths'][last[3]][-1];target=common['destinations'][dest]
                if math.hypot((end[0]-target[0])*111320,(end[1]-target[1])*88200)>2:wrong+=t['weight']
                if dest=='snu' and last[0]==0:
                    geometry=common['paths'][last[3]]
                    meters=sum(math.hypot((q[0]-p[0])*111320,(q[1]-p[1])*88200) for p,q in zip(geometry,geometry[1:]))
                    if meters>1000+5:far+=t['weight']
            checked+=1
        destinations={t['id']:b['destination_keys'][str(t['parent_id'])] for t in data['legs']}
        for d in data['behavior_decisions']:
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
          'wrong_terminal_service_direction_weight':wrong_direction,
          'opposite_branch_intermediate_then_rerouted_weight':changed_after_intermediate,
          'invalid_incumbent_chain_count':counter.get('unexpected_invalid_incumbent_chain',0),
          'initial_profile_mass':sum(stats['initial_mode_weights'].values()),'physical_source_mass':r['scope']['all']['weight'],
          'all_recorded_max_continuous_wait_min':r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min'],
          'over20_episode_weight':r['extended_diagnostics']['all_recorded_time_over20_episode_weight'],'unserved_weight':r['unserved_trip_weight'],
          'walking_opportunities':opportunity,'student_strategy_counts':counter}
        assert abs(row['initial_profile_mass']-row['physical_source_mass'])<1e-6
        row['behavior_gate_passed']=returned<1e-7 and far<1e-7 and wrong<1e-7 and early_shuttle<1e-7 and gate_left<1e-7 and wrong_direction<1e-7 and row['invalid_incumbent_chain_count']==0
        rows.append(row);print('BEHAVIOR_AUDITED',c['case'],row['behavior_gate_passed'],'returned',returned,'far',far,'wrong',wrong,'early',early_shuttle,flush=True)
    result={'release_id':w.name,'group':a.group,'status':'PASS_STUDENT_BEHAVIOR_GATES' if all(r['behavior_gate_passed'] for r in rows) else 'BEHAVIOR_GATE_FAILED',
      'cases':rows,'direction_audit_scope':'Actual last ride with no later route edit, plus any opposite-branch ride all the way toDaehak. Intended intermediate rides followed by a later walk/route edit are exposed separately; no planned-stage intent field was exported.',
      'over20_is_diagnostic_not_deleted':True,'production_writes':False,'new_date_accuracy':'NOT_EVALUATED'}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(result['status'],flush=True)
if __name__=='__main__':main()
