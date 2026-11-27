"""Versioned, directed road geometry. Missing geometry never becomes a chord."""
import math
import json
from collections import OrderedDict
from pathlib import Path

def meters(a,b):
    p,q=map(math.radians,(a[0],b[0]));x=math.sin((q-p)/2)**2+math.cos(p)*math.cos(q)*math.sin(math.radians(b[1]-a[1])/2)**2
    return 12742000*math.asin(min(1,math.sqrt(x)))

def length(points):return sum(meters(a,b) for a,b in zip(points,points[1:]))

def project(p,points,minimum=0,maximum=math.inf):
    best=None;offset=0
    for i,(a,b) in enumerate(zip(points,points[1:])):
        size=meters(a,b)
        if size==0:continue
        dx=(b[1]-a[1])*math.cos(math.radians(p[0]));dy=b[0]-a[0]
        t=max(0,min(1,((p[1]-a[1])*math.cos(math.radians(p[0]))*dx+(p[0]-a[0])*dy)/(dx*dx+dy*dy)))
        t=max(t,(minimum-offset)/size);t=min(t,(maximum-offset)/size)
        if 0<=t<=1:
            q=[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t]
            v={'point':q,'meters':offset+t*size,'offset_m':meters(p,q),'index':i}
            if best is None or v['offset_m']<best['offset_m']:best=v
        offset+=size
    return best

def point_at(points,at):
    for a,b in zip(points,points[1:]):
        size=meters(a,b)
        if at<=size:
            t=max(0,at/size) if size else 0
            return [a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])]
        at-=size
    return list(points[-1]) if points else None

def slice_path(points,start,end):
    if end<start:return []
    result=[point_at(points,start)];offset=0
    for a,b in zip(points,points[1:]):
        offset+=meters(a,b)
        if start<offset<end:result.append(list(b))
    result.append(point_at(points,end))
    return [p for i,p in enumerate(result) if p and (i==0 or p!=result[i-1])]

class RoadGeometry:
    def __init__(self,path=None):
        p=Path(path) if path else Path(__file__).parent/'data/road_geometry.json'
        self.payload=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'version':'unavailable','routes':{}}
        self.routes=self.payload['routes'];self.version=self.payload['version'];self.leg_cache=OrderedDict()

    def leg(self,route,i,j):
        # Directed geometry is immutable for the lifetime of this versioned file.
        key=(route['id'],i,j)
        if key not in self.leg_cache:
            self.leg_cache[key]=self._leg(route,i,j)
            if len(self.leg_cache)>4096:self.leg_cache.popitem(last=False)
        else:self.leg_cache.move_to_end(key)
        return self.leg_cache[key]

    def _leg(self,route,i,j):
        spec=self.routes.get(route['id'],{});segments=spec.get('segments',[]);points=[]
        for k in range(i,j):
            if not segments or k>=len(segments) or not segments[k]:return None
            part=segments[k]['geometry']
            if points and meters(points[-1],part[0])>3:return None
            points.extend(part if not points else part[1:])
        if not points:return None
        return {'geometry':points,'meters':length(points),'geometry_source':spec.get('source'),
                'geometry_version':self.version}

    def match_vehicle(self,vehicle,now,*,replay=None,route=None):
        spec=self.routes.get(vehicle.get('route_id'),{});segments=spec.get('segments',[])
        try:section=int(vehicle.get('section_order') or 0)-1
        except (ValueError,TypeError):section=-1
        # Provider section order identifies a directed occurrence, including loops.
        if section<0 or section>=len(segments) or not segments[section]:return None
        path=segments[section]['geometry'];hit=project((vehicle['lat'],vehicle['lon']),path)
        if not hit or hit['offset_m']>50:return None
        at=vehicle.get('provided_at')
        if not at or not -5<=now-at<=600:return None
        age=max(0,now-at);progress=hit['meters'];traversed=[]
        speed=max(0,min(12,float(vehicle.get('speed_mps',5))));speed_source='provider_speed' if vehicle.get('speed_mps') is not None else '18km/h assumption'
        if replay and route and vehicle.get('speed_mps') is None and section+1<len(route['stops']):
            distance=segments[section]['meters']
            duration,basis=replay.ride(route,section,section+1,distance)
            if duration>0:
                # Dwell is applied when passing the stop below.
                speed=min(12,distance/max(1,duration-15));speed_source=basis
        previous=vehicle.get('previous_observation')
        if previous and previous.get('section_order')==vehicle.get('section_order') and previous.get('provided_at'):
            dt=at-previous['provided_at'];before=project([previous['lat'],previous['lon']],path)
            if 5<=dt<=600 and before and before['offset_m']<=50 and before['meters']<=progress:
                speed=min(12,(progress-before['meters'])/dt);speed_source='same-section observations'
        if not vehicle.get('at_stop'):
            remaining=age*speed
            idx=section
            while remaining>0 and idx<len(segments):
                part=segments[idx]
                if not part:break
                poly=part['geometry'];size=length(poly)
                available=max(0,size-progress)
                if remaining<=available:
                    progress+=remaining;remaining=0;break
                remaining-=available
                # Dwell is explicit; never skip an unknown next segment.
                remaining=max(0,remaining-15*speed);traversed.append(idx);idx+=1;progress=0
            if idx<len(segments) and segments[idx]:path=segments[idx]['geometry'];section=idx
            else:progress=length(path)
        predicted=point_at(path,progress)
        return {**vehicle,'raw_lat':vehicle['lat'],'raw_lon':vehicle['lon'],
                'lat':predicted[0],'lon':predicted[1],'position_source':'estimated' if age>5 and not vehicle.get('at_stop') else 'observed',
                'observed_at':at,'age_seconds':round(age),'matched_section':section+1,'passed_stops':len(traversed),
                'geometry_source':spec.get('source'),'geometry_version':self.version,'match_offset_m':round(hit['offset_m'],1),
                'progress_m':progress,'motion_geometry':slice_path(path,progress,length(path)),
                'motion_speed_mps':0 if vehicle.get('at_stop') else speed,'speed_source':speed_source}

def inside(p,poly):
    yes=False;x,y=p[1],p[0]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        if (a[0]>y)!=(b[0]>y) and x<(b[1]-a[1])*(y-a[0])/(b[0]-a[0])+a[1]:yes=not yes
    return yes

def crosses(a,b,c,d):
    def side(p,q,r):return (q[1]-p[1])*(r[0]-p[0])-(q[0]-p[0])*(r[1]-p[1])
    return side(a,b,c)*side(a,b,d)<-1e-24 and side(c,d,a)*side(c,d,b)<-1e-24

class Buildings:
    def __init__(self,payload=None):
        self.items=(payload or {}).get('buildings',[]);self.grid={}
        for b in self.items:
            b['bounds']=[min(p[0] for p in b['polygon']),min(p[1] for p in b['polygon']),max(p[0] for p in b['polygon']),max(p[1] for p in b['polygon'])]
            x,y,z,w=b['bounds']
            for i in range(int(x*1000),int(z*1000)+1):
                for j in range(int(y*1000),int(w*1000)+1):self.grid.setdefault((i,j),[]).append(b)

    def candidates(self,a,b):
        found={}
        for i in range(int(min(a[0],b[0])*1000),int(max(a[0],b[0])*1000)+1):
            for j in range(int(min(a[1],b[1])*1000),int(max(a[1],b[1])*1000)+1):
                for item in self.grid.get((i,j),[]):found[item['id']]=item
        return found.values()

    def containing(self,p):return [b for b in self.candidates(p,p) if inside(p,b['polygon'])]

    def blocked(self,a,b):
        # Endpoints at an entrance may touch the boundary, but not cross interior.
        for item in self.candidates(a,b):
            poly=item['polygon']
            if any(inside([a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t],poly) for t in (.05,.25,.5,.75,.95)):return True
            if any(crosses(a,b,c,d) for c,d in zip(poly,poly[1:]+poly[:1])):return True
        return False
