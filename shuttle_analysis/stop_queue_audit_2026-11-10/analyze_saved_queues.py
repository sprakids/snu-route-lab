"""Read-only diagnostics of existing v7 peak audits. Never imports a simulator."""
import bisect,csv,gc,gzip,hashlib,json,math
from collections import defaultdict
from pathlib import Path

WORK=Path(__file__).resolve().parent
SIM=WORK.parent/'simulation_viewer_2026-11-07'
SOURCE=SIM/'gate_access_calibration_2026-11-09/candidates/alpha_075'
NODES=(46,47,60,61);START=680*60;END=1390*60;EPS=1e-7
DAYS={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}

def read(p):return json.loads(gzip.decompress(p.read_bytes()))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def clock(t):return f'{int(t)//3600:02d}:{int(t)%3600//60:02d}:{t%60:06.3f}'
def csvwrite(name,rows):
    if not rows:return
    with (WORK/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def quantile(rows,q):
    target=math.fsum(w for x,w in rows)*q;s=0.
    for x,w in sorted(rows):
        s+=w
        if s>=target:return x
    return None
def peak(rows):
    deltas=defaultdict(float)
    for r in rows:
        if r['arrival']>=r['end']:continue
        deltas[r['arrival']]+=r['weight'];deltas[r['end']]-=r['weight']
    current=0.;maximum=0.;at=START;previous=0.;over=0.
    for t,delta in sorted(deltas.items()):
        if current>40+EPS:over+=max(0.,min(t,END)-max(previous,START))
        current+=delta
        if START<=t<END and current>maximum+EPS:maximum=current;at=t
        previous=t
    return maximum,at,over

def main():
    WORK.mkdir(exist_ok=True);b=read(SOURCE/'prepared.json.gz');common=b['prepared']['common']
    meta={n:common['nodes'][n] for n in NODES}
    assert [meta[n]['ars'] for n in NODES]==['21269','21270','21298','21299']
    assert all(meta[n]['stop_id']!='120000029' for n in NODES)
    sources={str(SOURCE/'prepared.json.gz'):sha(SOURCE/'prepared.json.gz')}
    details=[];peak_rows=[];event_rows=[];option_rows=[];cause_rows=[]
    for node in NODES:
        for key,options in b['alternatives'].items():
            if not key.startswith(str(node)+'|'):continue
            for o in options:
                first=o['stages'][0] if o['stages'] else None
                option_rows.append({'node':node,'ars':meta[node]['ars'],'destination':key.split('|')[1],
                    'kind':o['kind'],'name':o.get('name'),'walk_seconds':o['walk'][1],
                    'first_route':first['rid'] if first else None,'first_board':first['board'] if first else None})
    for day,day_en in DAYS.items():
        p=SOURCE/f'audit-peak-{day_en}.json.gz';a=read(p);sources[str(p)]=sha(p)
        plans={r[0]:r for r in b['prepared']['plans'][day]}
        waits={node:[r for r in a['wait_audit'] if r['node']==node] for node in NODES}
        events={node:[r for r in a['events'] if r[1]==node] for node in NODES}
        peaks={node:peak(waits[node]) for node in NODES}
        active_trajectory={node:[] for node in NODES}
        vid_routes={e[2]:e[11] for e in a['events']}
        # Reconstruct peak queue using final split trajectories, preserving mass.
        for row in a['legs']:
            previous_wait=None;last_ride=None
            for leg in row['legs']:
                if leg[0]==3:last_ride=vid_routes[leg[6]]
                if leg[0]!=1:continue
                if leg[4] not in NODES:
                    previous_wait=(leg[4],leg[2]);last_ride=None;continue
                node=leg[4];at=peaks[node][1]
                if leg[1]<=at<min(leg[2],END):
                    count=sum(h[0]<=at+EPS for h in row['history'])
                    options=b['alternatives'].get(f"{node}|{b['destination_keys'][str(row['id'])]}",[])
                    walk=next((o['walk'][1]*b['walk_scales'][str(row['id'])] for o in options if not o['stages']),None)
                    arrival=row['legs'][-1][2]
                    source='after_ride_'+last_ride if last_ride else 'same_stop_rejoin' if previous_wait and previous_wait[0]==node and abs(previous_wait[1]-leg[1])<EPS else 'walk_access'
                    active_trajectory[node].append({'weight':row['weight'],'switches':count,
                        'walk_now_seconds':walk,'unserved':row['unserved'],'realized_remaining_seconds':arrival-at,
                        'walk_at_least_2min_faster':False if row['unserved'] or walk is None else walk+120<arrival-at,
                        'destination':plans[row['id']][2],'building':plans[row['id']][1],'source':source})
                previous_wait=(node,leg[2]);last_ride=None
        for node in NODES:
            maximum,at,over=peaks[node];rows=waits[node];active=[r for r in rows if r['arrival']<=at<r['end']]
            assert abs(math.fsum(r['weight'] for r in active)-maximum)<1e-5
            assert abs(math.fsum(r['weight'] for r in active_trajectory[node])-maximum)<1e-5
            eligible=defaultdict(float);dest=defaultdict(float);buildings=defaultdict(float)
            cause=defaultdict(float);peak_sources=defaultdict(float)
            for r in active:
                w=r['weight'];pattern=tuple(tuple(s) for s in r['eligibility'])
                eligible[str(pattern)]+=w;dest[plans[r['id']][2]]+=w;buildings[plans[r['id']][1]]+=w
                previous=[e for e in events[node] if r['ready']<=e[0]<=at and (e[11],e[12]) in pattern]
                refusals=sum(e[8]>EPS for e in previous)
                if r['ready']>at:cause['still_preparing']+=w
                if refusals>=1:cause['passed_by_compatible_full_1plus']+=w
                if refusals>=2:cause['passed_by_compatible_full_2plus']+=w
                if not previous:cause['no_compatible_service_since_ready']+=w
                if at-r['arrival']>600:cause['waited_over_10min_at_peak']+=w
                if at-r['arrival']>1800:cause['waited_over_30min_at_peak']+=w
            for r in active_trajectory[node]:
                w=r['weight']
                peak_sources[r['source']]+=w
                if r['switches']>=2:cause['switch_budget_exhausted']+=w
                if r['switches']==0:cause['no_switch_yet']+=w
                if r['walk_at_least_2min_faster']:cause['walking_now_2min_faster_than_realized']+=w
                if r['unserved']:cause['eventually_unserved']+=w
            for e in events[node]:
                assert abs(e[4]-e[5]+e[6]-e[7])<1e-5
                if at-1800<=e[0]<=at+600:
                    name=next((s['route_name'] for s in meta[node]['services'] if s['rid']==e[11] and s['board']==e[12]),e[11])
                    event_rows.append({'weekday':day,'node':node,'ars':meta[node]['ars'],'time':clock(e[0]),
                        'route':name,'route_id':e[11],'board_index':e[12],'capacity':e[3],
                        'before':e[4],'alighted':e[5],'available_before_boarding':e[3]-e[4]+e[5],
                        'boarded':e[6],'compatible_left':e[8],'ready_physical_queue_left':e[10],
                        'peak_at':clock(at),'before_or_at_peak':e[0]<=at})
            boarded=[(r['end']-r['arrival'],r['weight']) for r in rows if r['outcome']=='boarded']
            peakrow={'weekday':day,'node':node,'ars':meta[node]['ars'],'name':meta[node]['name'],
                'maximum_queue':maximum,'first_peak_time':clock(at),'first_peak_second':at,
                'seconds_over_40':over,'peak_waited_seconds_mean':math.fsum((at-r['arrival'])*r['weight'] for r in active)/maximum if maximum else 0.,
                'boarded_episode_wait_p95_seconds':quantile(boarded,.95),
                'peak_switch_exhausted':cause.get('switch_budget_exhausted',0.),
                'peak_compatible_full_2plus':cause.get('passed_by_compatible_full_2plus',0.),
                'peak_walk_now_faster_by_2min':cause.get('walking_now_2min_faster_than_realized',0.)}
            peak_rows.append(peakrow)
            cause_rows.extend({'weekday':day,'node':node,'ars':meta[node]['ars'],'cause':k,'weight':v} for k,v in cause.items())
            details.append({**peakrow,'causes_overlapping':dict(cause),
                'peak_eligibility':dict(eligible),'peak_destination':dict(dest),'peak_building':dict(buildings),'peak_sources':dict(peak_sources)})
        print(day_en,[(n,round(peaks[n][0],3),clock(peaks[n][1])) for n in NODES],flush=True)
        del a;gc.collect()
    csvwrite('weekday_peaks.csv',peak_rows);csvwrite('peak_causes.csv',cause_rows)
    csvwrite('peak_vehicle_events.csv',event_rows);csvwrite('existing_alternatives.csv',option_rows)
    assert all(sha(Path(p))==h for p,h in sources.items())
    result={'model':'v7 alpha_075 saved peak runs','nodes':meta,'unit':'weighted trip-event mass, not observed people',
        'details':details,'sources':sources,'checks':{'source_hashes_unchanged':True,'peak_queue_reconstructed_from_final_weighted_trajectories':True,
        'vehicle_flow_balance':True,'excluded_21128':True,'simulator_imports':0,'new_simulation_runs':0,'model_edits':0,'deployments':0},
        'limitations':['Causes overlap; do not add their weights.','Refusals reconstructed within each active waiting episode only.',
        'Switch exhaustion is a state at the maximum queue, not causal proof.',
        'Direct walk comparison is hindsight against completed trip, not a deployable foresight forecast.',
        'Rejected alternative forecasts are not in saved audits; absence of a switch does not prove its exact reason.',
        '40-person threshold is an unverified user recollection, not field ground truth or a cap.']}
    (WORK/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print('PASS saved v7 only; peak mass, trajectories, vehicle balances and unchanged sources')

if __name__=='__main__':main()
