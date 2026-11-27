"""Independent passenger-first terminal allocation and explicit shared-bus fixtures."""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
from bisect import bisect_left
from collections import defaultdict
import importlib.util,json,csv,math
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('waiting_estimates',ROOT/'estimate_wait.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
OUT=ROOT/'outputs_v2'
assert (OUT/'verification.json').exists(),'Wait for the main calculation and checks to finish.'
assert json.loads((OUT/'verification.json').read_text(encoding='utf-8'))['status']=='PASS'
real_services=m.services
fixtures=[]
try:
 m.services=lambda *args:[(723.,'admin_snu','a',60),(733.,'admin_snu','b',60)]
 bins={('월','admin_snu',720):90.}
 served,unserved,_,_=m.simulate(bins,'월',m.CONFIGS[0],0,{'circle':1.5,'reverse':1.5},1)
 assert abs(sum(x[2] for x in served)-90)<1e-9 and not unserved
 assert abs(sum(x[2]*x[3] for x in served)/90-(60*.5+30*10.5)/90)<1e-9
 fixtures.append({'test':'90 arrivals share two60-place buses','served':90,'expected_mean_min':23/6,'status':'PASS'})
 m.services=lambda *args:[(723.,'circle_302','a',60),(724.5,'circle_301','a',60),(733.,'circle_302','b',60),(734.5,'circle_301','b',60)]
 bins={('월','circle_302',720):50.,('월','circle_301',720):30.}
 served,unserved,_,_=m.simulate(bins,'월',m.CONFIGS[0],0,{'circle':1.5,'reverse':1.5},1)
 lower=[x for x in served if x[0]=='circle_301']
 assert abs(sum(x[2] for x in lower if x[6]==724.5)-10)<1e-9
 assert abs(sum(x[2] for x in lower if x[6]==734.5)-20)<1e-9
 assert abs(sum(x[2]*x[3] for x in lower)/30-26/3)<1e-9
 fixtures.append({'test':'302 boards50, so301 gets only10 places on same60-place bus','expected_301_mean_min':26/3,'status':'PASS'})
 m.services=lambda *args:[(723.,'admin_snu','a',60)]
 served,unserved,_,_=m.simulate({('월','admin_snu',720):90.},'월',m.CONFIGS[0],0,{'circle':1.5,'reverse':1.5},1)
 assert abs(sum(x[2] for x in unserved)-30)<1e-9
 fixtures.append({'test':'After last bus30 unserved is preserved, not assigned zero wait','unserved':30,'status':'PASS'})
finally:m.services=real_services
raw=defaultdict(float)
with (m.SRC/'conditional_mean_bins.csv').open(encoding='utf-8-sig',newline='') as f:
 for r in csv.DictReader(f):
  node=m.LOOKUP.get((r['route_id'],r['stop_id']))
  if node:raw[(r['weekday'],r['destination_group'],node,int(r['bin_minute']))]+=float(r['conditional_trip_events'])
bins=m.arrival_bins(m.CONFIGS[0],raw)
off=json.loads((OUT/'model_specs.json').read_text(encoding='utf-8'))['offsets_min']
results=[]
for day in m.DAYS:
 actual=m.simulate(bins,day,m.CONFIGS[0],3,off)[0]
 arrivals=m.packets_for(bins,day,60)
 for node in ('admin_snu','admin_daehak'):
  schedule=[(t,cap) for t,n,b,cap in real_services(m.CONFIGS[0],3,off) if n==node]
  times=[t for t,c in schedule];remaining=[float(c) for t,c in schedule]
  expected=defaultdict(lambda:[0.,0.]);not_served=0.
  # Independent loop order: assign each FIFO packet to successive residual seats.
  for ready,arrival,mass,b in arrivals[node]:
   j=bisect_left(times,ready-1e-8)
   while mass>1e-8 and j<len(times):
    take=min(mass,remaining[j]);remaining[j]-=take;mass-=take
    if 680<=b<1390:expected[b//60][0]+=take;expected[b//60][1]+=take*(times[j]-arrival)
    if remaining[j]<=1e-8:j+=1
   not_served+=mass
  observed=defaultdict(lambda:[0.,0.])
  for n,b,w,wait,e,s,t,a in actual:
   if n==node and 680<=b<1390:observed[b//60][0]+=w;observed[b//60][1]+=w*wait
  for h in sorted(set(expected)|set(observed)):
   err=max(abs(a-b) for a,b in zip(expected[h],observed[h]));assert err<1e-6
   results.append({'weekday':day,'node':node,'hour':h,'weight_error':abs(expected[h][0]-observed[h][0]),'weighted_wait_sum_error':abs(expected[h][1]-observed[h][1])})
with (OUT/'independent_terminal_check.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
proof={'status':'PASS','fixtures':fixtures,'independent_terminal_hour_cells':len(results),'max_weighted_wait_sum_error':max(x['weighted_wait_sum_error'] for x in results),'review_scope':'All weekdays, two terminal queues, phase3; shared302-to301 fixture; not field validation'}
(OUT/'independent_verification.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
failed=ROOT/'outputs/discretization_check.csv'
if failed.exists():
 with failed.open(encoding='utf-8-sig') as f:coarse=list(csv.DictReader(f))
 result={'status':'FAILED_COARSE_TIME_GRID','threshold_min':.25,'observed_max_difference_min':max(float(x['difference_min']) for x in coarse),'resolution':'30sec compared with5sec','replacement':'outputs_v2 uses5sec, checked against1sec. Original failed outputs preserved.'}
 (failed.parent/'FAILED.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(proof,ensure_ascii=False))
