"""Versioned supply clocks: distribution scenarios and docking-reference replay stay distinct."""
import bisect
from capacity import batch_size_at_clock
from artifacts import DAYS

def segment_seconds(route,at,day_index):
    profiles=route['segment_profiles'][str(day_index)]
    i=bisect.bisect_right([p[0] for p in profiles],at)-1
    return profiles[max(0,min(len(profiles)-1,i))][2]

def stop_times(route,start,day_index):
    times=[float(start)]
    for k in range(len(route['stops'])-1):times.append(times[-1]+segment_seconds(route,times[-1],day_index)[k])
    return times

def journeys(bundle,rid,info,scenario,day):
    index=list(DAYS).index(day);kind=bundle['prototype_config'].get('operations','baseline')
    if info.get('city') and kind!='baseline':
        route=bundle['operations']['routes'][rid]
        for start in route['departures'][str(index)]:
            yield start,stop_times(route,start,index)
    else:
        for clock in bundle['supply'][scenario][rid]:
            for _ in range(batch_size_at_clock(info,clock)):
                t0=clock+info.get('origin_to_modeled_first_stop_seconds',0)-info['offsets'][info['anchor']]
                yield clock,[t0+x for x in info['offsets']]
