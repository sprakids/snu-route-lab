"""Read saved runs only. No simulator imports, API calls, model edits or deploys."""
import bisect
import csv
import gc
import gzip
import hashlib
import json
import math
from collections import Counter,defaultdict
from pathlib import Path

WORK=Path(__file__).resolve().parent
SIM=WORK.parent/'simulation_viewer_2026-11-07'
CASES={'v7':SIM/'gate_access_calibration_2026-11-09/candidates/alpha_075',
       'v8':SIM/'weekday_operations_2026-11-10',
       'docked':SIM/'gate_clock_repair_2026-11-10'}
GATE=62;T0=17*3600+3*60;T1=T0+60
REALLOCATED_PATH=CASES['v7']/'reallocated_particles.csv'
with REALLOCATED_PATH.open(encoding='utf-8-sig',newline='') as f:
    REALLOCATED={int(r['particle_id']):r for r in csv.DictReader(f) if r['weekday']=='월'}

def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def signature(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def clock(t):return f'{int(t)//3600:02d}:{int(t)%3600//60:02d}:{t%60:06.3f}'
def write_csv(name,rows):
    if not rows:return
    with (WORK/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def area(a,b,w,left=T0,right=T1):return max(0,min(b,right)-max(a,left))*w/(right-left)

def process(label,folder):
    a=read(folder/'audit-peak-mon.json.gz');bundle=read(folder/'prepared.json.gz')
    common=bundle['prepared']['common'];day=next(iter(bundle['prepared']['plans']))
    plans=bundle['prepared']['plans'][day];byuid={p[0]:p for p in plans}
    assert common['nodes'][GATE]['stop_id']=='120000029'
    lookup={n['id']:i for i,n in enumerate(common['nodes'])}
    def first_node(plan):
        if not plan[6]:return None
        s=plan[6][0].get('pool',[plan[6][0]])[0];key=f'{s["rid"]}|{s["board"]}'
        return lookup.get(key) if s['rid'].startswith('shuttle') else bundle['city_node_lookup'].get(key)
    initials={p[0]:first_node(p) for p in plans}
    initial_modes={p[0]:('walk' if not p[6] else 'shuttle' if p[6][0]['rid'].startswith('shuttle') else 'city') for p in plans}
    inputs={'demand_signature':signature([[p[0],*p[1:5]] for p in plans]),'full_plans_signature':signature(plans),
        'demand_weight':math.fsum(p[3] for p in plans),'plan_count':len(plans),
        'capacities':{rid:r.get('capacity',25 if rid=='shuttle-41914' else 60) for rid,r in common['route_info'].items()},
        'gate_access':bundle.get('gate_access_calibration')}
    model_mass=defaultdict(float)
    for row in a['legs']:model_mass[row['id']]+=row['weight']
    assert set(model_mass)==set(byuid)
    assert max(abs(model_mass[k]-byuid[k][3]) for k in byuid)<1e-5
    pairs=[(w,m) for w,m in zip(a['waits'],a['wait_audit']) if w[0]==GATE]
    assert all(w[1]==m['arrival'] and w[2]==m['end'] and w[3]==m['weight'] and w[6]==m['id'] for w,m in pairs)
    intervals=[(m['arrival'],m['end'],m['weight']) for w,m in pairs]
    entry=defaultdict(float);exitrows=[]
    for w,m in pairs:
        key=(m['id'],m['arrival'],m['ready'],m['ticket'])
        entry[key]+=m['weight'];exitrows.append((m['end'],m['weight'],m['outcome']))
    def queue(t,ready=False):
        return math.fsum(m['weight'] for w,m in pairs if (m['ready'] if ready else m['arrival'])<=t<m['end'])
    def cumulative(t):
        return {'arrivals':math.fsum(w for (uid,arrival,ready,ticket),w in entry.items() if arrival<=t),
            **{outcome:math.fsum(w for end,w,o in exitrows if o==outcome and end<=t) for outcome in ('boarded','switched','unserved')}}
    mean=math.fsum(area(round(x,3),round(y,3),w) for x,y,w in intervals)
    decomposition={'case':label,'q_170300':queue(T0),'mean_q_1703':mean,
        'arrival_mean_increment':math.fsum(w*(T1-t)/60 for (uid,t,ready,ticket),w in entry.items() if T0<t<T1),
        **{outcome+'_mean_decrement':math.fsum(w*(T1-t)/60 for t,w,o in exitrows if o==outcome and T0<t<T1) for outcome in ('boarded','switched','unserved')},
        'mean_preparation_weight':math.fsum(area(m['arrival'],min(m['end'],m['ready']),m['weight']) for w,m in pairs)}
    raw_mean=math.fsum(area(x,y,w) for x,y,w in intervals)
    predicted=decomposition['q_170300']+decomposition['arrival_mean_increment']-sum(decomposition[k+'_mean_decrement'] for k in ('boarded','switched','unserved'))
    assert abs(predicted-raw_mean)<1e-7
    checkpoints=[]
    for t in (16*3600,16*3600+30*60,16*3600+50*60,17*3600,T0,T1,17*3600+5*60):
        c=cumulative(t);residual=c['arrivals']-c['boarded']-c['switched']-c['unserved']-queue(t)
        assert abs(residual)<1e-7
        checkpoints.append({'case':label,'time':clock(t),'second':t,'queue':queue(t),'ready_queue':queue(t,True),**c,'residual':residual})
    windows=[]
    for left,right in [(16*3600+50*60,T0),(17*3600,T0),(T0,T1),(17*3600,17*3600+5*60),(16*3600,T0)]:
        l,r=cumulative(left),cumulative(right)
        windows.append({'case':label,'start':clock(left),'end':clock(right),'q_start':queue(left),'q_end':queue(right),
            **{key:r[key]-l[key] for key in l}})
    vidrid={e[2]:e[11] for e in a['events']};gateevents=[]
    for e in a['events']:
        if e[1]!=GATE:continue
        t,node,vid,cap,before,off,on,after,left,new,physical,rid,k=e
        assert abs(before-off+on-after)<1e-6
        boarded=math.fsum(m['weight'] for w,m in pairs if m['outcome']=='boarded' and m['vehicle']==vid and abs(m['end']-t)<1e-6)
        assert abs(boarded-on)<1e-5
        if 16*3600+45*60<=t<=17*3600+10*60:
            gateevents.append({'case':label,'time':clock(t),'second':t,'route_id':rid,'route':common['route_info'][rid].get('name',rid),
                'capacity':cap,'before':before,'alighted':off,'available':cap-before+off,'boarded':on,'onboard_after':after,
                'compatible_left':left,'ready_queue_left':physical,'display_queue_after':queue(t),
                'preparing_weight':queue(t)-queue(t,True)})
    # Reconstruct the same queue from final weighted packet trajectories. A
    # shared prefix is weighted by each final packet's mass, never row-counted.
    categories=defaultdict(lambda:defaultdict(float));origins=defaultdict(lambda:defaultdict(float))
    trace=[];rejoins=[];leg_area=0.;leg_entry_mass=0.
    for row in a['legs']:
        uid=row['id'];weight=row['weight'];last_ride=None;previous_wait=None
        for leg in row['legs']:
            if leg[0]==3:last_ride=vidrid[leg[6]]
            if leg[0]!=1:continue
            if leg[4]!=GATE:
                previous_wait=(leg[4],leg[2]);last_ride=None;continue
            x,y=leg[1:3];leg_area+=area(round(x,3),round(y,3),weight);leg_entry_mass+=weight
            reallocated=uid in REALLOCATED
            if previous_wait and previous_wait[0]==GATE and abs(x-previous_wait[1])<1e-5 and last_ride is None:
                category='same_stop_rejoin';rejoins.append((uid,x,weight))
            elif last_ride:category='after_shuttle_ride' if last_ride.startswith('shuttle') else 'after_city_ride'
            elif initials[uid]==GATE and abs(x-(byuid[uid][4]+byuid[uid][5][1]))<1e-5:
                category='reallocated_initial_gate_walk' if reallocated else 'baseline_initial_gate_walk'
            else:category='walk_reroute_from_'+initial_modes[uid]
            original_route=REALLOCATED[uid]['original_first_route'] if reallocated else byuid[uid][6][0]['rid'] if byuid[uid][6] else 'walk'
            for g in (categories[category],origins[(byuid[uid][1],byuid[uid][2],reallocated,original_route)]):
                g['arrival_to_1703']+=weight if x<=T0 else 0
                g['arrival_1650_1703']+=weight if 16*3600+50*60<x<=T0 else 0
                g['queue_1703']+=weight if x<=T0<y else 0
                g['mean_queue_1703']+=area(round(x,3),round(y,3),weight)
            if 16*3600+45*60<=x<=17*3600+10*60:
                trace.append({'arrival':x,'end':y,'weight':weight,'category':category,
                    'building':byuid[uid][1],'destination':byuid[uid][2],'previous_route':last_ride,
                    'reallocated':reallocated,'original_route':original_route})
            previous_wait=(GATE,y);last_ride=None
    assert abs(leg_area-mean)<1e-5
    assert abs(leg_entry_mass-math.fsum(w for key,w in entry.items()))<1e-5
    categoryrows=[{'case':label,'category':k,**dict(v)} for k,v in categories.items()]
    originrows=[{'case':label,'building':k[0],'destination':k[1],'reallocated':k[2],'original_route':k[3],**dict(v)} for k,v in origins.items()]
    rejoinmap=defaultdict(float)
    for uid,t,w in rejoins:rejoinmap[(uid,t)]+=w
    switchedmap=defaultdict(float)
    for w,m in pairs:
        if m['outcome']=='switched':switchedmap[(m['id'],m['end'])]+=m['weight']
    assert all(w<=switchedmap[key]+1e-6 for key,w in rejoinmap.items())
    for window in windows:
        left=sum(float(v)*m for v,m in zip(window['start'].split(':'),(3600,60,1)))
        right=sum(float(v)*m for v,m in zip(window['end'].split(':'),(3600,60,1)))
        rejoin=math.fsum(w for uid,t,w in rejoins if left<t<=right)
        window.update(same_stop_rejoins=rejoin,external_arrivals=window['arrivals']-rejoin,physical_walkaways=window['switched']-rejoin)
        assert abs(window['q_start']+window['external_arrivals']-window['boarded']-window['physical_walkaways']-window['unserved']-window['q_end'])<1e-6
    switches=[{'case':label,'time':clock(r[0]),'second':r[0],'node':r[1],'weight':r[2],
        'old_route':r[4],'kind':r[5],'option':r[6]} for r in a['switches'] if 16*3600+45*60<=r[0]<=17*3600+5*60 and (r[1]==GATE or '120000029' in str(r[6]) or '서울대학교' in str(r[6]))]
    timeseries=[{'second':t,'queue':queue(t),'ready_queue':queue(t,True)} for t in range(16*3600+50*60,17*3600+8*60+1,5)]
    source_checks={str(folder/'audit-peak-mon.json.gz'):sha(folder/'audit-peak-mon.json.gz'),str(folder/'prepared.json.gz'):sha(folder/'prepared.json.gz')}
    result={'inputs':inputs,'decomposition':decomposition,'checkpoints':checkpoints,'windows':windows,'events':gateevents,
        'categories':categoryrows,'origins':originrows,'switches':switches,'timeseries':timeseries,'trace':trace,'sources':source_checks}
    del a,bundle;gc.collect();return result

def main():
    WORK.mkdir(exist_ok=True);results={}
    for name,folder in CASES.items():
        results[name]=process(name,folder)
        print(name,json.dumps(results[name]['decomposition']),flush=True)
    assert len({v['inputs']['demand_signature'] for v in results.values()})==1
    assert all(r['inputs']['capacities']==results['v7']['inputs']['capacities'] for r in results.values())
    decision=read(CASES['docked']/'pilot-decision.json')
    for label,source in [('v7','v7'),('v8','v8'),('docked','candidate')]:
        expected=next(r['uniform_minute_mean'] for r in decision[source] if r['id']=='snu_gate_1703')
        assert abs(results[label]['decomposition']['mean_q_1703']-expected)<1e-5
    for name,field in [('gate_events.csv','events'),('gate_checkpoints.csv','checkpoints'),('window_balances.csv','windows'),('origin_flows.csv','categories'),('building_source_flows.csv','origins'),('switches_near_gate.csv','switches')]:
        write_csv(name,[row for result in results.values() for row in result[field]])
    write_csv('minute_decomposition.csv',[v['decomposition'] for v in results.values()])
    private={name:r.pop('trace') for name,r in results.items()}
    (WORK/'private_gate_trajectories.json.gz').write_bytes(gzip.compress(json.dumps(private,ensure_ascii=False,separators=(',',':')).encode()))
    (WORK/'analysis.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('saved analysis; demand/capacity, queue balances, independent trajectory reconstruction PASS')

if __name__=='__main__':main()
