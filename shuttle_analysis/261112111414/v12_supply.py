"""A stop-passage scenario is inverted into first-modeled-stop clocks, not depot dispatch."""
import bisect,hashlib

def stop_times(route,start):
    times=[float(start)];profiles=route['segment_profiles']['0']
    for k in range(len(route['stops'])-1):
        i=max(0,bisect.bisect_right([p[0] for p in profiles],times[-1])-1)
        times.append(times[-1]+profiles[i][2][k])
    return times

def invert_passage(route,target,index):
    guess=target-(stop_times(route,target)[index]-target);best=None
    for _ in range(12):
        actual=stop_times(route,guess)[index];error=target-actual
        if best is None or abs(error)<abs(best[1]):best=(guess,error,actual)
        if abs(error)<1e-6:break
        guess+=error
    return best

def anchored_departures(route,rid,day,evidence):
    original=route['departures'][str(day)]
    reference=next(i for i,s in enumerate(route['stops']) if s['seq']==route['reference_seq'])
    old=[(start,stop_times(route,start)[reference]) for start in original]
    outside=[start for start,at in old if not 40800<=at<83400]
    inside=[(start,at) for start,at in old if 40800<=at<83400]
    if not inside:return original,[]
    target=inside[0][1];end=min(83400,old[-1][1]+1e-6);count=0;starts=[];rows=[]
    while target<end:
        start,error,actual=invert_passage(route,target,reference)
        if original[0]-1e-6<=start<=original[-1]+1e-6:
            starts.append(start)
        values,source=evidence.headways(rid,route['reference_seq'],actual)
        if values:
            shift=int.from_bytes(hashlib.sha256(f'v12-stop-passage:{rid}:{day}:{int(actual//3600)}'.encode()).digest()[:4],'big')
            gap=values[(count+shift)%len(values)]
        else:
            source='preserved_official_representative_fallback';gap=route['official_plan']['headway_seconds']
        assert 15<=gap<=3600
        rows.append({'route':rid,'weekday_index':day,'reference_seq':route['reference_seq'],
          'requested_reference_passage':target,'achieved_reference_passage':actual,
          'first_modeled_stop_start':start,'inverse_error_seconds':error,
          'next_reference_gap_scenario':gap,'source':source,
          'is_depot_dispatch_observation':False,'sampling_truncated_below15_above3600':True})
        target+=gap;count+=1
        assert count<2000
    values=sorted(set(outside+starts+[original[0],original[-1]]))
    assert all(b>a for a,b in zip(values,values[1:]))
    return values,rows
