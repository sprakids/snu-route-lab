"""Pure standard-library helpers extracted from the frozen v5 model.

All time arguments are seconds, distances metres, points [latitude, longitude].
These functions neither query observations nor infer actual vehicle capacities.
"""
import bisect
import math

EPS=1e-7


def distance_m(a,b):
    r=math.pi/180
    return 6371000*math.hypot((b[0]-a[0])*r,(b[1]-a[1])*r*math.cos((a[0]+b[0])/2*r))


def inside_polygon(point,ring):
    x,y=point;inside=False
    for a,b in zip(ring,ring[1:]):
        cross=(x-a[0])*(b[1]-a[1])-(y-a[1])*(b[0]-a[0])
        if abs(cross)<1e-14 and min(a[0],b[0])-1e-12<=x<=max(a[0],b[0])+1e-12 and min(a[1],b[1])-1e-12<=y<=max(a[1],b[1])+1e-12:return True
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:inside=not inside
    return inside


def zones(p,q,ring,force_campus=False,campus_kmh=40.,external_kmh=65.):
    length=distance_m(p,q)
    if force_campus:return [(length,campus_kmh)]
    rx,ry=q[0]-p[0],q[1]-p[1];fractions=[]
    for a,b in zip(ring,ring[1:]):
        if any(min(a[k],b[k])>max(p[k],q[k])+1e-12 or max(a[k],b[k])<min(p[k],q[k])-1e-12 for k in (0,1)):continue
        sx,sy=b[0]-a[0],b[1]-a[1];dx,dy=a[0]-p[0],a[1]-p[1];denom=rx*sy-ry*sx
        if abs(denom)<=1e-16:continue
        t=(dx*sy-dy*sx)/denom;u=(dx*ry-dy*rx)/denom
        if 1e-10<t<1-1e-10 and -1e-10<=u<=1+1e-10:fractions.append(round(t,12))
    cuts=[0.]+sorted(set(fractions))+[1.];out=[]
    for lo,hi in zip(cuts,cuts[1:]):
        if hi-lo<1e-12:continue
        mid=[p[0]+rx*(lo+hi)/2,p[1]+ry*(lo+hi)/2]
        out.append((length*(hi-lo),campus_kmh if inside_polygon(mid,ring) else external_kmh))
    return out


def kinematic_profile(points,cuts,ring,force_campus=False,accel=1.,dwell=15.):
    """Exact v5 5m-cell acceleration kernel, including dwell at EVERY cut.

    The final cut includes the destination's dwell. Do not add another 15s to
    a departure clock when using this model's service-event offsets.
    """
    if accel<=0 or dwell<0:raise ValueError('Invalid acceleration/dwell')
    if not points or not cuts or cuts[-1]!=len(points)-1:raise ValueError('Final cut must be the final point')
    if not ring or ring[0]!=ring[-1]:raise ValueError('Polygon ring must be closed')
    times=[0.];distances=[0.];speeds=[0.];caps_out=[];last=0;inside=outside=0.
    for stop in cuts:
        if not last<=stop<len(points):raise ValueError('Cuts must be ordered point indexes')
        cells=[]
        for p,q in zip(points[last:stop+1],points[last+1:stop+1]):
            for length,cap in zones(p,q,ring,force_campus):
                if length<1e-8:continue
                count=max(2,int(math.ceil(length/5)));cells.extend([(length/count,cap)]*count)
                if cap==40.:inside+=length
                else:outside+=length
        if cells:
            caps=[cap/3.6 for _,cap in cells]
            velocity=[0.]+[min(caps[k-1],caps[k]) for k in range(1,len(caps))]+[0.]
            for k,(ds,_) in enumerate(cells):velocity[k+1]=min(velocity[k+1],math.sqrt(velocity[k]**2+2*accel*ds))
            for k in range(len(cells)-1,-1,-1):velocity[k]=min(velocity[k],math.sqrt(velocity[k+1]**2+2*accel*cells[k][0]))
            for k,(ds,cap) in enumerate(cells):
                dt=2*ds/(velocity[k]+velocity[k+1]);times.append(times[-1]+dt);distances.append(distances[-1]+ds);speeds.append(velocity[k+1]);caps_out.append(cap)
        times.append(times[-1]+dwell);distances.append(distances[-1]);speeds.append(0.);caps_out.append(0.);last=stop
    return {'t':[round(t,6) for t in times],'d':[round(d,6) for d in distances],
            'v':[round(v,6) for v in speeds],'cap':caps_out,'duration':times[-1],
            'inside_m':round(inside,3),'outside_m':round(outside,3),'dwell_seconds':dwell*len(cuts)}


def city_segment_seconds(profile,saved_speed_kmh=None):
    """Snapshot-speed scenario, NOT an override for a measured trip time."""
    if saved_speed_kmh is None:return profile['duration']
    if not .5<=saved_speed_kmh<=100:raise ValueError('Unusable speed snapshot')
    return max(profile['duration'],profile['d'][-1]/(saved_speed_kmh/3.6))


def ride_seconds(inputs,route_id,board,alight):
    route=inputs['routes'][route_id];offsets=route['offsets_seconds']
    if not 0<=board<alight<len(offsets):raise ValueError('No modeled forward leg')
    return offsets[alight]-offsets[board]


def find_stop_indices(route,stop_id,source_seq=None):
    """Return ALL occurrences. The caller must disambiguate loops/direction."""
    return [i for i,s in enumerate(route['stops']) if str(s['id'])==str(stop_id) and
            (source_seq is None or str(s.get('source_seq'))==str(source_seq))]


def stage_choice(stage,rid,board):
    return next((s for s in stage.get('pool',[stage]) if s['rid']==rid and s['board']==board),None)


def first_boardable(rows,vehicles,ready,now,stage,weight,waiting):
    """Reference branch of city_capacity_model.first_boardable; no state mutation.

    No future queue inflow or unobserved upstream boarding is invented.
    Capacity/free-seat evidence and current queue must be supplied explicitly.
    """
    rows=tuple(tuple(row) for row in rows)
    ahead=[[float(s['w']),s['stages'][s['stage']]] for s in waiting];need=weight
    for when,vid,k in rows[bisect.bisect_left(rows,(now-EPS,-1,-1)):]:
        vehicle=vehicles[vid]
        if vehicle['last_stop']>=k:continue
        available=vehicle['cap']-sum(s['w'] for target,s in vehicle['onboard'] if target>k)
        if available<=EPS:continue
        for other in ahead:
            if other[0]<=EPS or stage_choice(other[1],vehicle['rid'],k) is None:continue
            take=min(available,other[0]);other[0]-=take;available-=take
            if available<=EPS:break
        choice=stage_choice(stage,vehicle['rid'],k)
        if when<ready-EPS or choice is None or available<=EPS:continue
        if need<=available+EPS:return when,vid,k,choice
        need-=available
    return None
