"""Read-only diagnosis of frozen v5 queues, supply and on-board loads."""
from pathlib import Path
from collections import defaultdict,Counter
import bisect,csv,gzip,hashlib,json,math
import numpy as np

HERE=Path(__file__).resolve().parent
VIEW=HERE.parent/'simulation_viewer_2026-11-07'
START,END,STEP=40800.,83400.,1800
DAYS={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}
PERIODS=[(max(START,t),min(END,t+STEP)) for t in range(int(START)//STEP*STEP,int(END),STEP)]


def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,x):(HERE/name).write_text(json.dumps(x,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8')
def csvfile(name,rows):
    with (HERE/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def clock(t):return f'{int(t)//3600:02d}:{int(t)//60%60:02d}'


def trajectory(rows):
    changes=defaultdict(lambda:[0.,0.])
    for node,a,b,w,denied,unserved,uid,outcome in rows:
        if unserved:b=min(b,END)
        changes[a][0]+=w;changes[b][0]-=w
        if denied>=0:changes[denied][1]+=w;changes[b][1]-=w
    times=sorted(changes);values=np.cumsum([changes[t] for t in times],axis=0) if times else np.zeros((0,2))
    assert len(values)==0 or values.min()>-1e-5
    return np.array(times),np.maximum(values,0.)


def interval_metrics(times,values,lo,hi):
    before=np.searchsorted(times,lo,side='right')-1
    q=values[before].copy() if before>=0 else np.zeros(2)
    peak=q.copy();area=np.zeros(2);positive=0.;last=lo
    for i in range(before+1,len(times)):
        at=times[i]
        if at>=hi:break
        dt=at-last;area+=q*dt
        if q[0]>1e-7:positive+=dt
        q=values[i];peak=np.maximum(peak,q);last=at
    area+=q*(hi-last)
    if q[0]>1e-7:positive+=hi-last
    return {'queue_person_min':float(area[0]/60),'denied_person_min':float(area[1]/60),
            'mean_queue':float(area[0]/(hi-lo)),'max_queue':float(peak[0]),
            'max_denied_queue':float(peak[1]),'positive_queue_minutes':positive/60}


def main():
    bundle_path=VIEW/'city_bus_model_2026-11-08/prepared.json.gz';bundle=read(bundle_path)
    prep=bundle['prepared'];common=prep['common'];nodes=common['nodes'];half=read(VIEW/'public/data/half_hour_v1/capacity_v5.json')
    assert common['city_speed_revision']=='campus_stop_corridors_20261108'
    byphysical=defaultdict(list)
    for i,n in enumerate(nodes):byphysical[('city' if n.get('city') else 'shuttle')+'|'+n['stop_id']].append(i)
    sources=[{'path':bundle_path.relative_to(HERE.parent).as_posix(),'sha256':sha(bundle_path)}]
    cells=[];load_cells=[];history_comparison=[];daytotals=[];checks=[]
    for scenario in ('regular','peak'):
        for day,did in DAYS.items():
            audit_path=VIEW/f'city_bus_model_2026-11-08/audit-{scenario}-{did}.json.gz'
            data_path=VIEW/f'public/data/capacity_v5/{scenario}-{did}.json'
            a=read(audit_path);d=read(data_path);waits=a['waits']
            sources.extend({'path':p.relative_to(HERE.parent).as_posix(),'sha256':sha(p)} for p in (audit_path,data_path))
            upper={p[0] for p in prep['plans'][day] if p[1] in ('301','302')}
            nodewaits=defaultdict(list);events=defaultdict(list)
            for w in waits:nodewaits[w[0]].append(w)
            for e in a['events']:
                if START<=e[0]<END:events[e[1],int(e[0]//STEP)*STEP].append(e)
            total=upper_total=0.
            for node,n in enumerate(nodes):
                rows=nodewaits[node];times,values=trajectory(rows)
                uts,uvs=trajectory([w for w in rows if w[6] in upper])
                for lo,hi in PERIODS:
                    key=int(lo//STEP)*STEP;m=interval_metrics(times,values,lo,hi);u=interval_metrics(uts,uvs,lo,hi)
                    cohort=half['scenarios'][scenario][did][str(node)][str(key)]
                    es=events[node,key];free=[max(0.,e[3]-e[4]+e[5]) for e in es]
                    count=len(es);blocked=sum(f<1e-7 for f in free)
                    row={'scenario':scenario,'weekday':day,'start_seconds':lo,'end_seconds':hi,'window':clock(lo)+'~'+clock(hi),
                        'node':node,'stop_id':n['stop_id'],'stop_name':n['name'],'queue_name':n['label'],
                        'mode':'city' if n.get('city') else 'shuttle','route_id':n['route'],
                        'is_upper_boarding':any(s in n['name'] for s in ('301','302','제1공학관','제2공학관')),
                        **m,'upper_origin_queue_person_min':u['queue_person_min'],
                        'arrival_weight':cohort['arrival_weight'],'boarded_weight':cohort['served_weight'],
                        'mean_boarded_wait_min':cohort['mean_wait_min'],'p90_boarded_wait_min':cohort['p90_wait_min'],
                        'mean_all_queue_exposure_min':cohort['mean_queue_exposure_min'],
                        'switched_weight':cohort['switched_weight'],'unserved_weight':cohort['unserved_weight'],
                        'cohort_denied_share':cohort['denied_share'],'cohort_denied_weight':cohort['denied_weight'],
                        'service_events':count,'empty_seat_supply':math.fsum(free),
                        'offered_reference_capacity':math.fsum(e[3] for e in es),
                        'boardings_in_clock_window':math.fsum(e[6] for e in es),
                        'new_denied_in_clock_window':math.fsum(e[9] for e in es),
                        'full_upstream_arrivals':blocked,'full_upstream_with_unmet_demand':sum(f<1e-7 and e[8]>1e-7 for f,e in zip(free,es)),
                        'unmet_departures':sum(e[8]>1e-7 for e in es)}
                    cells.append(row);total+=m['queue_person_min'];upper_total+=u['queue_person_min']
            independently=math.fsum(max(0.,min(w[2],END)-max(w[1],START))*w[3]/60 for w in waits)
            assert abs(total-independently)<1e-5,(scenario,day,total,independently)
            assert abs(math.fsum(e[9] for e in a['events'])-math.fsum(w[3] for w in waits if w[4]>=0))<1e-5
            # Occupancy is the course-derived modeled component, without outside passengers.
            occup=defaultdict(lambda:[0.,0.,0.,0.,0.,0.,0.]);section_sums=Counter();section_runs=Counter()
            for vid,rid,cap,legs in d['vehicles']:
                route=prep['routes'][rid];info=common['route_info'][rid]
                for k,(start,end,pid,load) in enumerate(legs):
                    assert k<len(info['segments']) and info['segments'][k]==pid
                    ratio=load/cap
                    for lo,hi in PERIODS:
                        dt=max(0.,min(end,hi)-max(start,lo))
                        if not dt:continue
                        key=rid,k,lo;v=occup[key]
                        v[0]+=dt;v[1]+=load*dt;v[2]+=cap*dt;v[3]+=dt*(ratio>=.95);v[4]+=load*dt*ratio;v[5]=max(v[5],load);v[6]+=int(lo<=start<hi)
                    if info.get('city') and 12*3600<=start<23*3600:
                        s,t=route['stops'][k:k+2]
                        key=rid,int(s['seq']),s['id'],t['id'],int(start//3600)
                        section_sums[key]+=load;section_runs[key]+=1
            for (rid,k,lo),v in occup.items():
                route=prep['routes'][rid];s,t=route['stops'][k:k+2]
                load_cells.append({'scenario':scenario,'weekday':day,'start_seconds':lo,'route_id':rid,'route_name':route['name'],
                    'from_index':k,'from_stop_id':s['id'],'to_stop_id':t['id'],'from_name':s['name'],'to_name':t['name'],
                    'vehicle_seconds':v[0],'passenger_seconds':v[1],'reference_capacity_seconds':v[2],
                    'modeled_load_ratio':v[1]/v[2] if v[2] else None,
                    'passenger_experienced_ratio':v[4]/v[1] if v[1] else None,
                    'full_vehicle_time_share':v[3]/v[0] if v[0] else None,
                    'max_modeled_load':v[5],'vehicle_entries':int(v[6])})
            for (rid,seq,sid,tid,hour),value in section_sums.items():
                lookup='|'.join(map(str,(rid,seq,sid,tid,list(DAYS).index(day),hour)))
                empirical=common['city_history']['profiles'].get(lookup)
                if empirical:
                    history_comparison.append({'scenario':scenario,'weekday':day,'route_id':rid,'route_name':prep['routes'][rid]['name'],
                        'section_seq':seq,'from_stop_id':sid,'to_stop_id':tid,'hour':hour,
                        'modeled_student_section_sum':value,'modeled_runs':section_runs[rid,seq,sid,tid,hour],
                        'historical_total_section_sum':empirical['mean_sum_load'],'history_dates':empirical['sample_dates'],
                        'scope':'same weekday-hour-section, different historical dates; not vehicle occupancy accuracy'})
            daytotals.append({'scenario':scenario,'weekday':day,'clock_queue_person_min':total,
                'upper_origin_clock_queue_person_min':upper_total,'input_trip_weight':d['report']['input_weight'],
                'switched_trip_weight':d['report']['switched_trip_weight'],'unserved_trip_weight':d['report']['unserved_trip_weight']})
            checks.append({'scenario':scenario,'weekday':day,'queue_exposure_difference':total-independently})
            print(scenario,day,'queue_person_min',round(total,2),flush=True)
    physical=[]
    grouped=defaultdict(list)
    for row in cells:grouped[row['scenario'],row['weekday'],row['start_seconds'],row['mode']+'|'+row['stop_id']].append(row)
    for (sc,day,lo,key),rows in grouped.items():
        first=rows[0];physical.append({'scenario':sc,'weekday':day,'start_seconds':lo,'window':first['window'],'physical_key':key,
            'stop_name':first['stop_name'],'mode':first['mode'],'node_count':len(rows),
            'queue_person_min':math.fsum(r['queue_person_min'] for r in rows),
            'mean_queue':math.fsum(r['mean_queue'] for r in rows),
            'upper_origin_queue_person_min':math.fsum(r['upper_origin_queue_person_min'] for r in rows),
            'arrival_weight':math.fsum(r['arrival_weight'] for r in rows),
            'switched_weight':math.fsum(r['switched_weight'] for r in rows),
            'new_denied_in_clock_window':math.fsum(r['new_denied_in_clock_window'] for r in rows)})
    save('queue_cells.json',cells);csvfile('queue_cells.csv',cells)
    save('physical_stop_cells.json',physical);csvfile('physical_stop_cells.csv',physical)
    save('modeled_occupancy_cells.json',load_cells);csvfile('modeled_occupancy_cells.csv',load_cells)
    save('historical_context_comparison.json',history_comparison);csvfile('historical_context_comparison.csv',history_comparison)
    save('daily_totals.json',daytotals);save('verification.json',{'status':'PASS','checks':checks,'sources':sources,
        'queue_cells':len(cells),'physical_stop_cells':len(physical),'occupancy_cells':len(load_cells),
        'historical_matched_cells':len(history_comparison),'simulation_recomputed':False})
    print('PASS',len(cells),len(load_cells),len(history_comparison),flush=True)


if __name__=='__main__':main()
