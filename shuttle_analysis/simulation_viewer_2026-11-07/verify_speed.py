"""Independent kinematic checks and campus membership sampling of stored profiles."""
from pathlib import Path
import bisect,json,math
ROOT=Path(__file__).resolve().parent
c=json.loads((ROOT/'public/data/capacity_v3/common.json').read_text(encoding='utf-8'))
ring=c['bus_speed_model']['campus_polygon'];profiles=c['motion_profiles']
def metres(p,q):
 r=math.pi/180;return 6371000*math.hypot((p[0]-q[0])*r,(p[1]-q[1])*r*math.cos((p[0]+q[0])*r/2))
def inside(point):
 # Winding-angle test, independent of the builder's ray-crossing predicate.
 angle=0.;x,y=point
 for a,b in zip(ring,ring[1:]):
  ax,ay=a[0]-x,a[1]-y;bx,by=b[0]-x,b[1]-y
  angle+=math.atan2(ax*by-ay*bx,ax*bx+ay*by)
 return abs(angle)>math.pi
phases=samples=0;max_speed={'campus':0.,'external':0.};max_integral_error=0.;acceleration_max=0.
for pid,p in profiles.items():
 t,d,v,cap=p['t'],p['d'],p['v'],p['cap'];points=c['paths'][int(pid)];cum=[0.]
 for a,b in zip(points,points[1:]):cum.append(cum[-1]+metres(a,b))
 assert abs(cum[-1]-d[-1])<.01
 assert len(t)==len(d)==len(v)==len(cap)+1
 for i,limit in enumerate(cap):
  dt=t[i+1]-t[i];dd=d[i+1]-d[i];assert dt>0 and dd>=-1e-6
  error=abs(dd-(v[i]+v[i+1])*dt/2);max_integral_error=max(max_integral_error,error);assert error<1e-4
  speed=max(v[i],v[i+1])*3.6;assert speed<=limit+1e-4
  if limit==0:assert dd==0 and v[i]==v[i+1]==0 and abs(dt-15)<1e-5
  else:
   acceleration=abs(v[i+1]-v[i])/dt
   if dt>.001:assert acceleration<=1.002
   acceleration_max=max(acceleration_max,acceleration)
   max_speed['campus' if limit==40 else 'external']=max(max_speed['campus' if limit==40 else 'external'],speed)
  phases+=1
 stride=max(1,len(cap)//25)
 for i in range(0,len(cap),stride):
  if cap[i]==0:continue
  dt=(t[i+1]-t[i])/2;speed=(v[i]+v[i+1])/2
  dist=d[i]+v[i]*dt+.5*(v[i+1]-v[i])/(2*dt)*dt*dt
  k=min(len(points)-2,max(0,bisect.bisect_right(cum,dist)-1))
  f=(dist-cum[k])/(cum[k+1]-cum[k]) if cum[k+1]>cum[k] else 0
  point=[points[k][0]+(points[k+1][0]-points[k][0])*f,points[k][1]+(points[k+1][1]-points[k][1])*f]
  assert speed*3.6 <= (40 if inside(point) else 65)+.001
  samples+=1
result={'status':'PASS','profiles':len(profiles),'phases':phases,'independent_polygon_speed_samples':samples,
 'maximum_kmh':max_speed,'max_integral_error_m':max_integral_error,'max_stored_acceleration_m_s2':acceleration_max,
 'scenario':'User-selected maxima: campus40, external65; not observed or legally verified speeds.'}
(ROOT/'capacity_model/speed_40_65/speed_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
