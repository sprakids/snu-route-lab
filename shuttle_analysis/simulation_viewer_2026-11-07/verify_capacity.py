"""Independent output-level queue, capacity, mass and chart reconciliation."""
from pathlib import Path
from collections import defaultdict
import gzip,json,math,argparse
import numpy as np
ROOT=Path(__file__).resolve().parent
def load(p):return json.loads(p.read_text(encoding='utf-8'))
parser=argparse.ArgumentParser();parser.add_argument('--dataset',default='capacity_v2');parser.add_argument('--work',default='capacity_model');args=parser.parse_args()
DATA=ROOT/'public/data'/args.dataset;WORK=ROOT/args.work
common=load(DATA/'common.json')
reports=[];checked=0;queue_samples=0;legacy=load(ROOT.parent/'waiting_time_estimates_2026-11-07/outputs_v2/chart_configs.json')
charts=load(DATA/'charts.json');assert charts['legacy_wait_charts']==legacy
for scenario in ('regular','peak'):
 for did in ('mon','tue','wed','thu','fri'):
  d=load(DATA/f'{scenario}-{did}.json')
  a=json.loads(gzip.decompress((WORK/f'audit-{scenario}-{did}.json.gz').read_bytes()))
  assert abs(sum(p['weight'] for p in a['legs'])-a['report']['input_weight'])<1e-5
  for p in a['legs']:
   assert all(l[2]>=l[1] and all(math.isfinite(x) for x in l[1:3]) for l in p['legs'])
   assert all(abs(l[2]-r[1])<1e-5 for l,r in zip(p['legs'],p['legs'][1:]))
  rows=defaultdict(list)
  for r in a['waits']:rows[r[0]].append(r)
  # A final path fragment carries its fraction of every previous boarding.
  # This independently identifies each of two simultaneous night vehicles.
  boarding_by_vehicle=defaultdict(float)
  for p in a['legs']:
   for l in p['legs']:
    if l[0]==3:boarding_by_vehicle[(l[6],l[4],round(l[1],6))]+=p['weight']
  max_error=0.
  for node,rr in rows.items():
   arr=np.array([r[1] for r in rr]);end=np.array([r[2] for r in rr]);w=np.array([r[3] for r in rr]);denied=np.array([r[4] for r in rr]);unserved=np.array([r[5] for r in rr])
   ordered=sorted(rr,key=lambda r:(r[1],r[2]));assert all(y[2]>=x[2]-1e-6 for x,y in zip(ordered,ordered[1:])),(scenario,did,node,'FIFO')
   node_events=[e for e in a['events'] if e[1]==node]
   for ei,e in enumerate(node_events):
    t=e[0];board=boarding_by_vehicle[(e[2],node,round(t,6))]
    later_same_clock=sum(other[6] for other in node_events[ei+1:] if abs(other[0]-t)<1e-6)
    left=float(w[(arr+20<=t+1e-6)&(end>t+1e-6)].sum())+later_same_clock
    max_error=max(max_error,abs(board-e[6]),abs(left-e[8]))
    assert abs(e[4]-e[5]+e[6]-e[7])<1e-5
    assert 0<=e[7]<=e[3]+1e-6
    if e[8]>1e-6:assert abs(e[7]-e[3])<1e-5
    checked+=1
   # Independent direct interval counting against exported exact-time queue lookup.
   timeline=d['queue_timeline'][node];times=[r[0] for r in timeline]
   import bisect
   for t in range(40817,83390,419):
    tt=t+.137;i=bisect.bisect_right(times,tt)-1;export=timeline[i][1:] if i>=0 else [0.,0.]
    q=float(w[(arr<=tt)&(end>tt)].sum());dq=float(w[(denied>=0)&(denied<=tt)&(end>tt)].sum())
    assert abs(q-export[0])<1e-4 and abs(dq-export[1])<1e-4,(scenario,did,node,tt,q,export)
    queue_samples+=1
   for h in range(11,24):
    eligible=(arr>=max(40800,h*3600))&(arr<min(83400,(h+1)*3600));served=eligible&(~unserved)
    sw=float(w[served].sum());stat=charts['scenarios'][scenario][did]['hourly'][str(node)][str(h)]
    assert abs(float(w[eligible].sum())-stat['arrival_weight'])<1e-5
    if sw>1e-7:assert abs(float(((end[served]-arr[served])*w[served]).sum())/sw/60-stat['mean_wait_min'])<1e-6
    else:assert stat['mean_wait_min'] is None
  assert max_error<1e-5,max_error
  reports.append({'scenario':scenario,'day':did,'max_board_queue_reconciliation_error':max_error,'mass_conserved':True,'fifo':True})
result={'status':'PASS','capacity_and_boarding_events_checked':checked,'independent_queue_time_samples':queue_samples,'legacy_charts_identical':True,'runs':reports,'scope':'Output-level independent interval counting and aggregation; not validation against observed passengers.'}
(WORK/'independent_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
