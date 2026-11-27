"""Continuous FIFO link arrival times interpolated at segment entry, no dwell add-on."""
import bisect

def values_at(route,at,day_index=0):
    profiles=route['segment_profiles'][str(day_index)]
    i=max(0,min(len(profiles)-1,bisect.bisect_right([p[0] for p in profiles],at)-1))
    left=profiles[i]
    if route.get('time_interpolation')!='linear_fifo' or i+1==len(profiles):return left[2]
    right=profiles[i+1];width=right[0]-left[0]
    mix=max(0.,min(1.,(at-left[0])/width))
    return [a+(b-a)*mix for a,b in zip(left[2],right[2])]

def assert_fifo_profiles(route):
    minimum=1.
    for profiles in route['segment_profiles'].values():
        for a,b in zip(profiles,profiles[1:]):
            width=b[0]-a[0];assert width>0
            for x,y in zip(a[2],b[2]):
                slope=1+(y-x)/width;assert slope>0,'Non-FIFO arrival profile; do not patch through silently'
                minimum=min(minimum,slope)
    return minimum
