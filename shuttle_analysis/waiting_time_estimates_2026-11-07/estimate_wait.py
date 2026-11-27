"""Conditional FIFO queue estimates from preserved mean five-minute arrival weights.

No live passenger observations, production edits, or new route-choice simulation.
302 -> 301 share each vehicle's capacity; other campus stops are outside scope.
"""
from pathlib import Path
from collections import defaultdict, deque
from bisect import bisect_left
from datetime import datetime, timezone
import csv, json, math, hashlib, time

ROOT=Path(__file__).resolve().parent
SRC=ROOT.parent/'scenario_comparison_2026-11-07/simulation_outputs'
OUT=ROOT/'outputs_v2'
DAYS='월화수목금'
PHASES=20
PREP=20/60
RHO=5772/29613
EPS=1e-8
NODES={
 'admin_snu':('shuttle-41841','snu-410','행정관 → 서울대입구역'),
 'admin_daehak':('shuttle-daehak','snu-410','행정관 → 대학동'),
 'circle_302':('shuttle-41946','snu-901','302동 · 순환'),
 'circle_301':('shuttle-41946','snu-1001','301동 · 순환'),
 'reverse_302':('shuttle-41914','snu-901','302동 · 역순환'),
 'reverse_301':('shuttle-41914','snu-1001','301동 · 역순환'),
}
LOOKUP={(r,s):n for n,(r,s,_) in NODES.items()}
CONFIGS=[
 {'id':'base60','label':'기준: 대형60명·입구역4분','large_capacity':60,'upper_capacity':60,'peak_headway':4,'move_share':.5,'mix':[55.7/99.9,27.2/99.9,17/99.9]},
 {'id':'fast3','label':'입구역 배차3분','large_capacity':60,'upper_capacity':60,'peak_headway':3,'move_share':.5,'mix':[55.7/99.9,27.2/99.9,17/99.9]},
 {'id':'slow5','label':'입구역 배차5분','large_capacity':60,'upper_capacity':60,'peak_headway':5,'move_share':.5,'mix':[55.7/99.9,27.2/99.9,17/99.9]},
 {'id':'large44','label':'대형 정원44명 가정','large_capacity':44,'upper_capacity':44,'peak_headway':4,'move_share':.5,'mix':[55.7/99.9,27.2/99.9,17/99.9]},
 {'id':'upper30','label':'순환302동의 가용정원30명','large_capacity':60,'upper_capacity':30,'peak_headway':4,'move_share':.5,'mix':[55.7/99.9,27.2/99.9,17/99.9]},
 {'id':'move25','label':'수업 직후 이동25%','large_capacity':60,'upper_capacity':60,'peak_headway':4,'move_share':.25,'mix':[55.7/99.9,27.2/99.9,17/99.9]},
 {'id':'move75','label':'수업 직후 이동75%','large_capacity':60,'upper_capacity':60,'peak_headway':4,'move_share':.75,'mix':[55.7/99.9,27.2/99.9,17/99.9]},
 {'id':'equal_mix','label':'교외 목적지 세 방향 균등','large_capacity':60,'upper_capacity':60,'peak_headway':4,'move_share':.5,'mix':[1/3]*3},
]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def clock(t):return f'{int(t)//60:02d}:{int(t)%60:02d}'
def write(name,rows):
 rows=list(rows)
 if not rows:return
 with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def weights(c):
 q=c['move_share'];return {'dorm':RHO*q,**{g:(1-RHO)*x*q for g,x in zip(('snu','nak','daehak'),c['mix'])}}
def arrival_bins(c,raw):
 result=defaultdict(float);w=weights(c)
 for (day,g,node,b),v in raw.items():result[(day,node,b)]+=v*w[g]
 return result
def dist(a,b):
 r=math.pi/180;x=(b['lon']-a['lon'])*r*math.cos((a['lat']+b['lat'])/2*r);y=(b['lat']-a['lat'])*r
 return 6371000*math.hypot(x,y)
def offsets(routes):
 answer={}
 for rid,prefix in [('shuttle-41946','circle'),('shuttle-41914','reverse')]:
  st=routes[rid]['stops'];i=next(i for i,s in enumerate(st) if s['id']=='snu-901');j=i+1
  assert st[j]['id']=='snu-1001'
  answer[prefix]=(dist(st[i],st[j])*1.2/5+15)/60
 return answer
def series(a,b,h,phase,include_end=False):
 t=a+phase*h;out=[]
 while t<b-EPS or (include_end and t<=b+EPS):out.append(t);t+=h
 return out
def services(c,phase_id,off):
 """Planned headways with unknown clock phase; exact night/reverse clocks.

 Vehicle counts are never multiplied into headway dispatch capacity. Two night
 buses are an explicitly simultaneous pair, unlike daytime fleet allocations.
 """
 p=phase_id/PHASES;pd=((7*phase_id)%PHASES)/PHASES;pc=((11*phase_id)%PHASES)/PHASES
 snu=series(420,480,15,p)+series(480,660,4,p)+series(660,900,10,p)+series(900,1140,c['peak_headway'],p)+series(1140,1200,15,p)+series(1200,1260,30,p)
 daehak=series(420,480,15,pd)+series(480,660,6.5,pd)+series(660,1140,10,pd)+[1140.]
 circle=series(480,1140,6,pc)+series(1140,1260,20,pc)+[1260.]
 reverse=list(range(590,1031,20))
 events=[];cap=c['large_capacity'];uc=c['upper_capacity']
 for idx,t in enumerate(snu):events.append((t,'admin_snu',f'snu-{idx}',cap))
 for idx,t in enumerate(daehak):events.append((t,'admin_daehak',f'daehak-{idx}',cap))
 for t in [1270,1300,1330,1360,1390]:
  events.extend([(float(t),'admin_snu',f'snu-night-{t}',cap*2),(float(t),'admin_daehak',f'daehak-night-{t}',cap*2)])
 for prefix,times,capacity in [('circle',circle,uc),('reverse',reverse,25)]:
  for idx,t in enumerate(times):
   bus=f'{prefix}-{idx}'
   events.extend([(float(t),prefix+'_302',bus,capacity),(float(t)+off[prefix],prefix+'_301',bus,capacity)])
 return sorted(events)
def packets_for(bins,day,subslots):
 a=defaultdict(list)
 for (d,node,b),mass in bins.items():
  if d!=day or mass<=EPS:continue
  # Retain earlier-than-window arrivals so pre-existing modeled queues carry in.
  if b>=1390:continue
  for k in range(subslots):
   arrival=b+(k+.5)*5/subslots
   a[node].append([arrival+PREP,arrival,mass/subslots,b])
 for n in NODES:a[n].sort()
 return a
def simulate(bins,day,c,phase_id,off,subslots=60):
 arrivals=packets_for(bins,day,subslots);events=services(c,phase_id,off)
 dep=defaultdict(list)
 for t,n,b,cap in events:dep[n].append(t)
 queues={n:deque() for n in NODES};idx=defaultdict(int);through=defaultdict(float)
 served=[];capacity_checks=[];maxq=defaultdict(float);ready_mass=defaultdict(float)
 for t,node,bus,totalcap in events:
  aa=arrivals[node]
  while idx[node]<len(aa) and aa[idx[node]][0]<=t+EPS:
   packet=aa[idx[node]].copy();queues[node].append(packet);ready_mass[node]+=packet[2];idx[node]+=1
  maxq[node]=max(maxq[node],ready_mass[node])
  retained=through[bus] if node.endswith('_301') else 0.
  available=max(0.,totalcap-retained);before=available;taken=0.
  q=queues[node]
  while q and available>EPS:
   ready,arrival,mass,b=q[0];take=min(mass,available)
   first=bisect_left(dep[node],ready-EPS);assert first<len(dep[node])
   schedule_wait=dep[node][first]-arrival
   wait=t-arrival;extra=t-dep[node][first]
   assert wait>=-EPS and extra>=-EPS
   served.append((node,b,take,wait,max(0.,extra),schedule_wait,t,arrival))
   available-=take;taken+=take;ready_mass[node]-=take
   if take>=mass-EPS:q.popleft()
   else:q[0][2]-=take
  if node.endswith('_302'):through[bus]=taken
  assert taken<=before+1e-6 and taken+retained<=totalcap+1e-6
  capacity_checks.append((node,taken+retained,totalcap))
 unserved=[]
 for node in NODES:
  for ready,arrival,mass,b in [*queues[node],*arrivals[node][idx[node]:]]:unserved.append((node,b,mass,arrival))
 total_in=sum(p[2] for a in arrivals.values() for p in a)
 assert abs(total_in-sum(x[2] for x in served)-sum(x[2] for x in unserved))<1e-5
 return served,unserved,maxq,capacity_checks
def quantile(pairs,q):
 if not pairs:return None
 pairs=sorted(pairs);target=sum(w for v,w in pairs)*q;acc=0
 for v,w in pairs:
  acc+=w
  if acc>=target:return v
 return pairs[-1][0]
def summary(group,unserved):
 served=sum(x[0] for x in group);lost=sum(unserved);total=served+lost
 if not served:return {'arrival_weight':total,'served_weight':0.,'unserved_weight':lost,'mean_wait_min':None,'p90_wait_min':None,'mean_capacity_extra_min':None,'mean_schedule_wait_min':None,'wait_over10_share':None,'capacity_delay_share':None}
 return {'arrival_weight':total,'served_weight':served,'unserved_weight':lost,
  'mean_wait_min':sum(w*v for w,v,e,s in group)/served,
  'p90_wait_min':quantile([(v,w) for w,v,e,s in group],.9),
  'mean_capacity_extra_min':sum(w*e for w,v,e,s in group)/served,
  'mean_schedule_wait_min':sum(w*s for w,v,e,s in group)/served,
  'wait_over10_share':sum(w for w,v,e,s in group if v>10)/served,
  'capacity_delay_share':sum(w for w,v,e,s in group if e>EPS)/served}
def main():
 started=time.perf_counter();assert not OUT.exists();OUT.mkdir(parents=True)
 source_paths=[SRC/'conditional_mean_bins.csv',SRC/'stop_inflow_5min_scenarios.csv',SRC.parent/'scenario_specs.json',ROOT.parent/'course_demand_2026-11-06/outputs/simulation_routes.json',ROOT.parent/'operation_plans_2026-11-01/sources/O11_2.pdf',ROOT.parent/'operation_plans_2026-11-01/sources/O12_1.pdf']
 before={str(p):sha(p) for p in source_paths};dump(OUT/'source_manifest.json',before)
 assert load(SRC/'execution_provenance.json')['status']=='complete'
 assert load(SRC/'runner_validation.json')['status']=='PASS'
 raw=defaultdict(float);selected_rows=0
 with (SRC/'conditional_mean_bins.csv').open(encoding='utf-8-sig',newline='') as f:
  for r in csv.DictReader(f):
   node=LOOKUP.get((r['route_id'],r['stop_id']))
   if node:
    v=float(r['conditional_trip_events']);assert v>=0 and math.isfinite(v)
    raw[(r['weekday'],r['destination_group'],node,int(r['bin_minute']))]+=v;selected_rows+=1
 base=arrival_bins(CONFIGS[0],raw);equal=arrival_bins(CONFIGS[-1],raw)
 reference=defaultdict(float)
 with (SRC/'stop_inflow_5min_scenarios.csv').open(encoding='utf-8-sig',newline='') as f:
  for r in csv.DictReader(f):
   node=LOOKUP.get((r['route_id'],r['stop_id']))
   if node and r['scenario'] in ('historical_reference','equal_reference'):
    reference[(r['scenario'],r['weekday'],node,int(r['bin_minute']))]+=float(r['expected_trip_events'])
 diffs=[]
 for scenario,values in [('historical_reference',base),('equal_reference',equal)]:
  keys={(day,n,b) for day,n,b in values if 680<=b<1390}|{(d,n,b) for sc,d,n,b in reference if sc==scenario}
  diffs.extend(abs(values.get(k,0)-reference.get((scenario,*k),0)) for k in keys)
 assert max(diffs)<1e-7,max(diffs)
 routes={r['id']:r for r in load(source_paths[3])['routes']};off=offsets(routes)
 write('arrival_inputs_5min.csv',({'weekday':d,'node':n,'label':NODES[n][2],'bin_minute':b,'time':clock(b),'arrival_weight':v} for (d,n,b),v in sorted(base.items()) if 680<=b<1390))
 hourly_rows=[];fine_rows=[];daily_rows=[];phase_rows=[];queue_rows=[];buses_checked=0
 for c in CONFIGS:
  bins=arrival_bins(c,raw)
  for day in DAYS:
   grouped=defaultdict(list);uns=defaultdict(list);phase_means=defaultdict(list);fine=defaultdict(list);fine_uns=defaultdict(list);qmax=defaultdict(list)
   for phase in range(PHASES):
    served,unserved,mq,checks=simulate(bins,day,c,phase,off)
    buses_checked+=len(checks);phase_groups=defaultdict(list)
    for node,b,w,wait,extra,sched,t,arrival in served:
     if not 680<=b<1390:continue
     h=b//60;value=(w/PHASES,wait,extra,sched)
     grouped[(node,h)].append(value);fine[(node,b)].append(value);phase_groups[(node,h)].append((w,wait,extra,sched))
    for node,b,w,a in unserved:
     if 680<=b<1390:uns[(node,b//60)].append(w/PHASES);fine_uns[(node,b)].append(w/PHASES)
    for (node,h),values in phase_groups.items():
     v=summary(values,[])['mean_wait_min'];phase_means[(node,h)].append(v)
     phase_rows.append({'config':c['id'],'weekday':day,'node':node,'hour':h,'phase_id':phase,'mean_wait_min':v})
    for n,v in mq.items():qmax[n].append(v)
   for node in NODES:
    allvals=[];alluns=[]
    for h in range(11,24):
     vals=grouped[(node,h)];us=uns[(node,h)];s=summary(vals,us);pm=phase_means[(node,h)]
     hourly_rows.append({'config':c['id'],'weekday':day,'node':node,'label':NODES[node][2],'hour':h,'arrival_window':('11:20–12:00' if h==11 else '23:00–23:10' if h==23 else f'{h:02}:00–{h+1:02}:00'),**s,'phase_mean_min':min(pm) if pm else None,'phase_mean_max':max(pm) if pm else None,'phase_mean_count':len(pm),'scope':'Conditional mean-inflow queue; no actual crowd observations'})
     allvals.extend(vals);alluns.extend(us)
    daily_rows.append({'config':c['id'],'weekday':day,'node':node,'label':NODES[node][2],**summary(allvals,alluns)})
    queue_rows.append({'config':c['id'],'weekday':day,'node':node,'max_preboarding_queue_weight_min_phase':min(qmax[node]),'max_preboarding_queue_weight_max_phase':max(qmax[node])})
    for b in range(680,1390,5):fine_rows.append({'config':c['id'],'weekday':day,'node':node,'bin_minute':b,'time':clock(b),**summary(fine[(node,b)],fine_uns[(node,b)])})
   print(c['id'],day,'complete',flush=True)
 write('waiting_hourly.csv',hourly_rows);write('waiting_5min.csv',fine_rows);write('waiting_daily.csv',daily_rows);write('hourly_phase_means.csv',phase_rows);write('queue_peak_sensitivity.csv',queue_rows)
 # Independent spot check of time discretization at the two principal busy weekdays.
 discretization=[]
 for day in ('월','수'):
  a=simulate(base,day,CONFIGS[0],3,off,60)[0];b=simulate(base,day,CONFIGS[0],3,off,300)[0]
  for node in NODES:
   def mean(rows):
    vals=[(w,v,e,s) for n,bb,w,v,e,s,t,ar in rows if n==node and 680<=bb<1390];return summary(vals,[])['mean_wait_min']
   x,y=mean(a),mean(b);discretization.append({'weekday':day,'node':node,'step5sec_mean':x,'step1sec_mean':y,'difference_min':abs(x-y) if x is not None and y is not None else None})
 write('discretization_check.csv',discretization)
 assert max(r['difference_min'] or 0 for r in discretization)<.25
 assert all(sha(p)==v for p,v in before.items())
 checks={'status':'PASS','method':'Mean arrival-flow FIFO queue postprocessing, not replay of individual students','input_reconciliation_max_error':max(diffs),'selected_conditional_rows':selected_rows,'protected_input_hashes_unchanged':True,'capacity_events_checked':buses_checked,'phase_scenarios':PHASES,'configs':len(CONFIGS),'hourly_rows':len(hourly_rows),'fine_rows':len(fine_rows),'discretization_max_difference_min':max(r['difference_min'] or 0 for r in discretization),'live_api_calls':0,'app_code_changes':False,'elapsed_seconds':round(time.perf_counter()-started,2)}
 dump(OUT/'verification.json',checks)
 dump(OUT/'model_specs.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'configs':CONFIGS,'nodes':NODES,'offsets_min':off,'arrival_support_minutes':[680,1390],'arrival_bin_reconstruction':'Uniform across5min bin; sixty5sec midpoint packets, checked against three hundred1sec packets','capacity':'Large60 user-selected unverified; reverse25 nominal small-bus assumption','fifo':'302 boardings remain aboard through301; residual capacity shared','initial_occupancy':'Zero at302 baseline; upper30 sensitivity reserves30 places for unmodelled riders','queues':'Separate lines for every route and stop; no rerouting or abandonment','transfer_arrivals':'Held at original model times; queue delay does not propagate to later transfers','daytime_clock':'20 equally spaced unknown departure phases, not a confidence interval','demand':'Mean of prior10 route-choice repetitions; not mean queue over10 repetitions','background_demand':'Not measured, not added; results conditional on modeled course-related flow','time_scope':'Regular semester weekdays, 2026-2 general operation, no September-October-only extra buses or exam-night extra bus','study_week':'Nov9-13 typical-week labels only; not an actual-day forecast','service_boundaries':'Published last departures19:00Daehak,21:00at302circle,17:10at302reverse,23:10night','prep_seconds':20})
 print(json.dumps(checks,ensure_ascii=False))
 for node in ('admin_snu','admin_daehak','circle_302','circle_301','reverse_302','reverse_301'):
  print('BASE',node)
  for d in DAYS:
   eligible=[r for r in hourly_rows if r['config']=='base60' and r['weekday']==d and r['node']==node and 12<=r['hour']<19 and r['served_weight']>=10]
   best=max(eligible,key=lambda r:r['mean_wait_min']) if eligible else None
   print(d,{k:best[k] for k in ('arrival_window','arrival_weight','mean_wait_min','p90_wait_min','mean_capacity_extra_min','phase_mean_min','phase_mean_max')} if best else None)
if __name__=='__main__':main()
