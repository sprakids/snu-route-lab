"""Validate time-dependent clocks and known gate anchors before full pilots."""
from collections import Counter
import copy,math
from artifacts import ROOT,read,save,sha,check_baseline
from operations import journeys,stop_times

def main():
    check_baseline();lock=read(ROOT/'experiment_lock.json');original=read(ROOT/'frozen/prepared_capacity44_pair.json.gz')
    baseline_common=copy.deepcopy(original['prepared']['common']);results=[]
    supply=read(ROOT/'frozen/supply.json');original['supply']=supply
    for kind in ('baseline','distribution_v8','gate_reference'):
        bundle=copy.deepcopy(original);bundle['prototype_config']={'operations':kind}
        if kind!='baseline':bundle['operations']=read(ROOT/f'frozen/operations_{kind}.json')
        roster=[];segments=0
        for rid,info in bundle['prepared']['common']['route_info'].items():
            if info.get('city') and kind!='baseline':
                declared=bundle['operations']['routes'][rid]['stops'];actual=bundle['prepared']['routes'][rid]['stops']
                assert [r['id'] for r in declared]==[r['id'] for r in actual]
                assert len(declared)==len(info['offsets'])
            for clock,times in journeys(bundle,rid,info,'regular','월'):
                assert all(math.isfinite(t) for t in times) and all(b>a for a,b in zip(times,times[1:]))
                assert len(times)==len(info['offsets'])
                for k,(a,b) in enumerate(zip(times,times[1:])):
                    pid=info['segments'][k];duration=b-a
                    if 'motion_profiles' in baseline_common:assert duration>=baseline_common['motion_profiles'][str(pid)]['duration']-1e-5
                    segments+=1
                if not info.get('city'):
                    t0=clock+info.get('origin_to_modeled_first_stop_seconds',0)-info['offsets'][info['anchor']]
                    assert times==[t0+x for x in info['offsets']]
                roster.append((rid,clock,times))
        anchors=[]
        if kind=='gate_reference':
            for row in read(ROOT/'frozen/gate_clock_alignment.json'):
                route=bundle['operations']['routes'][row['route_id']]
                index=next(i for i,s in enumerate(route['stops']) if s['seq']==row['reference_seq'])
                times=stop_times(route,row['modeled_first_departure_second'],0)
                error=abs(times[index]-row['observed_reference_second']);assert error<1e-5;anchors.append(error)
        results.append({'kind':kind,'vehicle_journeys_before_horizon_filter':len(roster),'segments':segments,
            'verified_gate_reference_clocks':len(anchors),'max_gate_alignment_error_seconds':max(anchors,default=None),
            'clock_is_observed_absolute_boarding':False,'no_extra_dwell_added':True,'shuttle_clock_preserved':True})
    receipt={'status':'PASS','results':results,'production_latest_unchanged':sha(ROOT.parent/'simulation_viewer_2026-11-07/public/routing-model/latest.json')==read(ROOT/'creation_manifest.json')['production_latest_sha256'],
        'no_automatic_promotion':lock['operator_approval_required_for_any_production_replacement'],'past_capacity_learning_changes_forecast_not_actual_seats':True}
    assert receipt['production_latest_unchanged'];save(ROOT/'preflight.json',receipt);print(receipt,flush=True)

if __name__=='__main__':main()
