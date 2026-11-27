"""Replay the capacity model with user-selected 40/65 km/h speed ceilings.

Road geometry determines distance. A saved OSM campus polygon determines the
speed region. Acceleration/braking and stop dwell are explicit scenario inputs.
Original route choice is fixed; changed ride times propagate through transfers.
"""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import bisect,gzip,hashlib,json,math,time
import numpy as np
import capacity_model as base

ROOT=Path(__file__).resolve().parent
WORK=ROOT/'capacity_model/speed_40_65'
OUT=ROOT/'public/data/capacity_v3'
BOUNDARY_SOURCE=ROOT.parent/'app/data/campus_map_osm.json'
CAMPUS_KMH,EXTERNAL_KMH,ACCEL,DWELL=40.,65.,1.,15.

class Campus:
    def __init__(self):
        data=base.read(BOUNDARY_SOURCE);elements={(e['type'],e['id']):e for e in data['elements']}
        rel=elements['relation',11917142];ways=[list(elements['way',m['ref']]['nodes']) for m in rel['members'] if m['role']=='outer']
        chain=ways.pop(0)
        while ways:
            found=False
            for i,w in enumerate(ways):
                if w[0]==chain[-1]:chain.extend(w[1:]);ways.pop(i);found=True;break
                if w[-1]==chain[-1]:chain.extend(w[-2::-1]);ways.pop(i);found=True;break
            assert found,'Campus boundary must form one connected outer ring.'
        assert chain[0]==chain[-1]
        self.ring=[[elements['node',n]['lat'],elements['node',n]['lon']] for n in chain]
        points=np.array(self.ring);self.a=points[:-1];self.b=points[1:];self.delta=self.b-self.a
        self.low=np.minimum(self.a,self.b);self.high=np.maximum(self.a,self.b)
        self.bounds=(points.min(axis=0),points.max(axis=0));self.cache={}
    def inside(self,p):
        x,y=p
        if x<self.bounds[0][0] or x>self.bounds[1][0] or y<self.bounds[0][1] or y>self.bounds[1][1]:return False
        inside=False
        for a,b in zip(self.ring,self.ring[1:]):
            cross=(x-a[0])*(b[1]-a[1])-(y-a[1])*(b[0]-a[0])
            if abs(cross)<1e-14 and min(a[0],b[0])-1e-12<=x<=max(a[0],b[0])+1e-12 and min(a[1],b[1])-1e-12<=y<=max(a[1],b[1])+1e-12:return True
            if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:inside=not inside
        return inside
    def zones(self,p,q):
        key=tuple(p)+tuple(q)
        if key in self.cache:return self.cache[key]
        a=np.array(p);r=np.array(q)-a
        low=np.minimum(p,q);high=np.maximum(p,q)
        possible=np.all(self.low<=high+1e-12,axis=1)&np.all(self.high>=low-1e-12,axis=1)
        aa=self.a[possible];s=self.delta[possible];difference=aa-a
        denom=r[0]*s[:,1]-r[1]*s[:,0]
        valid=np.abs(denom)>1e-16
        t=np.divide(difference[:,0]*s[:,1]-difference[:,1]*s[:,0],denom,out=np.zeros_like(denom),where=valid)
        u=np.divide(difference[:,0]*r[1]-difference[:,1]*r[0],denom,out=np.zeros_like(denom),where=valid)
        fractions=[0.]+sorted(set(round(float(v),12) for v in t[valid&(t>1e-10)&(t<1-1e-10)&(u>=-1e-10)&(u<=1+1e-10)]))+[1.]
        length=base.distance(p,q);zones=[]
        for lo,hi in zip(fractions,fractions[1:]):
            if hi-lo<1e-12:continue
            midpoint=(a+r*((lo+hi)/2)).tolist();zones.append((length*(hi-lo),CAMPUS_KMH if self.inside(midpoint) else EXTERNAL_KMH))
        self.cache[key]=zones;return zones

def cumulative(points):
    result=[0.]
    for p,q in zip(points,points[1:]):result.append(result[-1]+base.distance(p,q))
    return result

def stops_for_path(points,rid,i,j,routes,road):
    """Use endpoints of saved route segments; nearest-road vertex only as fallback."""
    coords={}
    for k,p in enumerate(points):coords.setdefault(tuple(p),[]).append(k)
    segments=road.get(rid,{}).get('segments',[]);cuts=[];last=0;fallbacks=0
    for k in range(i,j):
        if k==j-1:at=len(points)-1
        else:
            segment=segments[k] if k<len(segments) else None
            target=tuple(round(float(v),6) for v in segment['geometry'][-1]) if segment else None
            options=coords.get(target,[]);position=bisect.bisect_left(options,last)
            if position<len(options):at=options[position]
            else:
                stop=routes[rid]['stops'][k+1];target=[stop['lat'],stop['lon']]
                at=min(range(last,len(points)),key=lambda idx:base.distance(points[idx],target));fallbacks+=1
                assert base.distance(points[at],target)<150,'Stop-to-road fallback is too distant.'
        assert at>=last;cuts.append(at);last=at
    return cuts,fallbacks

def profile(points,cuts,campus):
    times=[0.];distances=[0.];speeds=[0.];phase_caps=[];last=0;inside_m=outside_m=0.
    for stop_index in cuts:
        cells=[]
        for p,q in zip(points[last:stop_index+1],points[last+1:stop_index+1]):
            for length,cap in campus.zones(p,q):
                if length<1e-8:continue
                count=max(2,int(math.ceil(length/5)))
                cells.extend([(length/count,cap)]*count)
                if cap==CAMPUS_KMH:inside_m+=length
                else:outside_m+=length
        if cells:
            caps=[c/3.6 for _,c in cells];velocity=[0.]+[min(caps[k-1],caps[k]) for k in range(1,len(caps))]+[0.]
            for k,(ds,_) in enumerate(cells):velocity[k+1]=min(velocity[k+1],math.sqrt(velocity[k]**2+2*ACCEL*ds))
            for k in range(len(cells)-1,-1,-1):velocity[k]=min(velocity[k],math.sqrt(velocity[k+1]**2+2*ACCEL*cells[k][0]))
            for k,(ds,cap) in enumerate(cells):
                dt=2*ds/(velocity[k]+velocity[k+1]);times.append(times[-1]+dt);distances.append(distances[-1]+ds);speeds.append(velocity[k+1]);phase_caps.append(cap)
        times.append(times[-1]+DWELL);distances.append(distances[-1]);speeds.append(0.);phase_caps.append(0.)
        last=stop_index
    assert len(times)==len(distances)==len(speeds)==len(phase_caps)+1
    assert abs(distances[-1]-cumulative(points)[-1])<1e-5
    for k,cap in enumerate(phase_caps):
        assert max(speeds[k],speeds[k+1])*3.6<=cap+1e-5 if cap else speeds[k]==speeds[k+1]==0
        assert abs(speeds[k+1]-speeds[k])/(times[k+1]-times[k])<=ACCEL+1e-6
    return {'t':[round(t,6) for t in times],'d':[round(d,6) for d in distances],
            'v':[round(v,6) for v in speeds],'cap':phase_caps,'duration':times[-1],
            'inside_m':round(inside_m,3),'outside_m':round(outside_m,3),'dwell_seconds':DWELL*len(cuts)}

def apply_speed(prepared):
    settings={'campus_max_kmh':CAMPUS_KMH,'external_target_kmh':EXTERNAL_KMH,'acceleration_m_s2':ACCEL,
        'stop_dwell_seconds':DWELL,'boundary_relation':11917142,'boundary_source_sha256':base.sha(BOUNDARY_SOURCE),
        'prepared_sha256':base.sha(ROOT/'capacity_model/prepared.json.gz'),'profile_version':1}
    cache=WORK/'motion_profiles.json.gz';WORK.mkdir(parents=True,exist_ok=True)
    if cache.exists():
        stored=json.loads(gzip.decompress(cache.read_bytes()));assert stored['settings']==settings
    else:
        campus=Campus();common=prepared['common'];wanted={};road=base.read(base.OLD/'road_geometry.json')['routes']
        for rid,info in common['route_info'].items():
            for i,pid in enumerate(info['segments']):wanted[pid]=(rid,i,i+1)
        for plans in prepared['plans'].values():
            for plan in plans:
                for stage in plan[6]:
                    if not stage['rid'].startswith('shuttle'):wanted[stage['ride_path']]=(stage['rid'],stage['board'],stage['alight'])
        profiles={};fallbacks=0
        for number,(pid,(rid,i,j)) in enumerate(sorted(wanted.items())):
            points=common['paths'][pid];cuts,missing=stops_for_path(points,rid,i,j,prepared['routes'],road);fallbacks+=missing
            profiles[str(pid)]=profile(points,cuts,campus)
            if number and number%100==0:print('speed profile',number,'/',len(wanted),flush=True)
        stored={'settings':settings,'profiles':profiles,'campus_polygon':campus.ring,'stop_vertex_fallbacks':fallbacks}
        base.packed(cache,stored)
    common=prepared['common'];common['motion_profiles']=stored['profiles']
    common['bus_speed_model']={**settings,'campus_polygon':stored['campus_polygon'],
        'note':'사용자 지정 속도 시나리오. 저장된 OSM 경계 안 최고40, 밖 목표65km/h. 가감속1m/s²·정류장15초. 실측·법정 제한속도 자료가 아닙니다.'}
    original={rid:info['offsets'][-1] for rid,info in common['route_info'].items()}
    for rid,info in common['route_info'].items():
        offsets=[0.]
        for pid in info['segments']:offsets.append(offsets[-1]+stored['profiles'][str(pid)]['duration'])
        info['offsets']=offsets
    for plans in prepared['plans'].values():
        for plan in plans:
            for stage in plan[6]:
                if not stage['rid'].startswith('shuttle'):stage['ride_seconds']=stored['profiles'][str(stage['ride_path'])]['duration']
    return stored,original

def main():
    started=time.perf_counter();prepared,hashes=base.prepare();stored,old_times=apply_speed(prepared)
    base.OUT=OUT;base.WORK=WORK;OUT.mkdir(parents=True,exist_ok=True)
    base.public('common.json',prepared['common']);charts={};reports=[]
    for scenario in base.SCENARIOS:
        charts[scenario]={}
        for day,did in base.DAYS.items():
            report,hourly,daily=base.simulate(prepared,day,scenario)
            charts[scenario][did]={'hourly':hourly,'daily':daily,'report':report};reports.append(report)
    base.public('charts.json',{'scenarios':charts,'legacy_wait_charts':base.read(ROOT.parent/'waiting_time_estimates_2026-11-07/outputs_v2/chart_configs.json'),
        'legacy_note':'이전 평균 유입·20위상·이전 속도 조건. 새 속도·정원 연계 모형과 구분합니다.'})
    assert all(base.sha(p)==h for p,h in hashes.items())
    assert stored['settings']['boundary_source_sha256']==base.sha(BOUNDARY_SOURCE)
    v={'status':'PASS','user_speed_scenario':stored['settings'],'speed_profiles':len(stored['profiles']),
        'profile_phases':sum(len(p['cap']) for p in stored['profiles'].values()),'stop_vertex_fallbacks':stored['stop_vertex_fallbacks'],
        'runs':reports,'capacity_large':60,'capacity_reverse':25,'route_choice_reselected':False,'representative_seed':20261106,
        'builder_sha256':base.sha(Path(__file__)),'capacity_engine_sha256':base.sha(ROOT/'capacity_model.py'),
        'source_hashes_unchanged':True,'original_route_travel_seconds':old_times,
        'new_route_travel_seconds':{rid:info['offsets'][-1] for rid,info in prepared['common']['route_info'].items()},
        'created_at_utc':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':time.perf_counter()-started}
    base.save(WORK/'verification.json',v)
    print('SPEED MODEL DONE',round(time.perf_counter()-started,2),flush=True)
if __name__=='__main__':main()
