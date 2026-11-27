"""Path-local physical corrections; unavailable gradients remain explicitly unknown."""
from dataclasses import dataclass
import math

def distance(a,b):
    r=math.pi/180
    return 6371000*math.hypot((b[0]-a[0])*r,(b[1]-a[1])*r*math.cos((a[0]+b[0])/2*r))

def numeric_incline(value):
    if not isinstance(value,str):return None
    try:
        if value.endswith('%'):return float(value[:-1])/100
        if value.endswith('°'):return math.tan(math.radians(float(value[:-1])))
    except ValueError:return None
    return None

def segment_seconds(meters,kmh=4.8,slope=None,stairs=False,stairs_factor=3.):
    factor=stairs_factor if stairs else math.exp(3.5*(abs(slope+.05)-.05)) if slope is not None else 1.
    return meters/(kmh/3.6)*factor

def catalog(paths,osm,config):
    nodes={e['id']:(e['lat'],e['lon']) for e in osm['elements'] if e['type']=='node'};edges={}
    pointkey=lambda p:tuple(round(float(x),6) for x in p)
    for way in osm['elements']:
        if way['type']!='way':continue
        tags=way.get('tags',{});slope=numeric_incline(tags.get('incline'));stairs=tags.get('highway')=='steps'
        for a,b in zip(way['nodes'],way['nodes'][1:]):
            if a not in nodes or b not in nodes:continue
            key=(pointkey(nodes[a]),pointkey(nodes[b]))
            edges[key]=(slope,stairs);edges[key[::-1]]=(-slope if slope is not None else None,stairs)
    result=[]
    for path in paths:
        seconds=meters=stairs_m=unknown=uphill=0.
        for a,b in zip(path,path[1:]):
            length=distance(a,b);slope,stairs=edges.get((pointkey(a),pointkey(b)),(None,False))
            seconds+=segment_seconds(length,config['walking_kmh'],slope,stairs,config['stairs_time_factor'])
            meters+=length;stairs_m+=length*stairs;unknown+=length*(slope is None and not stairs)
            uphill+=length*max(0.,slope or 0.)
        result.append({'seconds':seconds,'meters':meters,'stairs_meters':stairs_m,'unknown_slope_meters':unknown,'known_climb_meters':uphill})
    return result
