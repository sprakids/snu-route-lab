"""Monday diagnostic evidence only; never updates models, collectors or sites."""
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime,timezone,timedelta
from bisect import bisect_right
import csv,gzip,hashlib,json,math,statistics

ROOT=Path(__file__).resolve().parent
A=ROOT/'analysis'
SIM=ROOT.parent/'simulation_viewer_2026-11-07'
OUT=ROOT/'diagnostics'
KST=timezone(timedelta(hours=9))


def read(path):return json.loads(path.read_bytes())
def csvread(path):return list(csv.DictReader(path.open(encoding='utf-8-sig')))
def write(name,rows):
    if not rows:return
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(dict.fromkeys(k for r in rows for k in r)));w.writeheader();w.writerows(rows)
def dump(name,data):(OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def hour(at):return datetime.fromtimestamp(at,KST).hour
def q(values,p):
    values=sorted(values);return values[min(len(values)-1,int((len(values)-1)*p))] if values else None
def near(row,stop):return math.hypot((row['lat']-stop['lat'])*111195,(row['lon']-stop['lon'])*111195*math.cos(math.radians(row['lat'])))<=60


def main():
    OUT.mkdir(exist_ok=True)
    stops=read(A/'route_stops.json');byseq={rid:{int(s['seq']):s for s in rows} for rid,rows in stops.items()}
    common=read(SIM/'public/data/capacity_v7/common.json')
    bundle=json.loads(gzip.decompress((SIM/'gate_access_calibration_2026-11-09/candidates/alpha_075/prepared.json.gz').read_bytes()))
    routes=bundle['prepared']['routes'];names={r['route_id']:r['name'] for r in common['city_services']}
    nominal={r['route_id']:r['headway_seconds'] for r in common['city_services']}
    positions={};fetches=defaultdict(list);full=Counter();traffic_batches=Counter()
    ambiguous={tuple(x) for x in read(A/'ambiguous_provider_keys.private.json')}
    for line in gzip.decompress((A/'collector-2026-11-09.json.gz').read_bytes()).splitlines():
        record=json.loads(line)
        for r in record['route_records']:
            fetches[r['route_id']].append((r['at'],r.get('error')))
            if r.get('traffic'):traffic_batches[r['route_id']]+=1
        for v in record['vehicles']:
            key=v['route_id'],v['id'],v['provided_at']
            if key not in positions or v['captured_at']<positions[key]['captured_at']:positions[key]=v
    tracks=defaultdict(list);exclusions=Counter()
    for key,r in positions.items():
        seq=int(r['section_order']);age=r['captured_at']-r['provided_at']
        if key in ambiguous:exclusions['ambiguous']+=1;continue
        if not 0<=age<=300 or seq not in byseq[r['route_id']]:exclusions['stale_invalid']+=1;continue
        tracks[r['route_id'],r['id']].append(dict(r,seq=seq))
        if r.get('full_known'):
            full[r['route_name'],'known']+=1
            if r['full']:full[r['route_name'],'true']+=1;full[r['route_name'],'full_grade_'+r['crowd_code']]+=1
    fetch_periods=[]
    for rid,rows in fetches.items():
        for label,low,high in [('before15',11,15),('peak15_19',15,19),('after19',19,24)]:
            ts=sorted(set(t for t,e in rows if low<=hour(t)<high));gaps=[b-a for a,b in zip(ts,ts[1:])]
            fetch_periods.append({'route':names[rid],'period':label,'saved_requests':len(ts),'median_gap_seconds':statistics.median(gaps) if gaps else None,
                                  'p90_gap_seconds':q(gaps,.9),'max_gap_seconds':max(gaps) if gaps else None,'error_records':sum(bool(e) for t,e in rows if low<=hour(t)<high)})
    write('sampling_by_period.csv',fetch_periods)
    crossings=[];near_events=[];travel=[]
    for (rid,vehicle),rows in tracks.items():
        rows.sort(key=lambda r:r['provided_at']);previous=None;run=0;seen=set();history=[]
        vid=hashlib.sha256(vehicle.encode()).hexdigest()[:14]
        for r in rows:
            s=byseq[rid][r['seq']];reset=previous is None or r['seq']<previous['seq'] or r['provided_at']-previous['provided_at']>300 or s['direction']!=byseq[rid][previous['seq']]['direction']
            if reset:run+=1;seen=set();history=[]
            if not reset and r['seq']>previous['seq']:
                width=r['provided_at']-previous['provided_at'];delta=r['seq']-previous['seq']
                for seq in range(previous['seq']+1,r['seq']+1):
                    crossings.append({'route_id':rid,'route':names[rid],'seq':seq,'stop':byseq[rid][seq]['name'],'stop_id':byseq[rid][seq]['id'],
                                      'direction':byseq[rid][seq]['direction'],'vehicle_hash':vid,'run':run,'lower':previous['provided_at'],
                                      'upper':r['provided_at'],'midpoint':(previous['provided_at']+r['provided_at'])/2,
                                      'width_seconds':width,'sequence_jump':delta,'tight':width<=45 and delta<=3})
            event_near=r['at_stop'] and near(r,s)
            if event_near and r['seq'] not in seen:
                seen.add(r['seq'])
                bounded=not reset and not(previous['at_stop'] and previous['seq']==r['seq'] and near(previous,s))
                lower=previous['provided_at'] if bounded else None;upper=r['provided_at']
                event={'route_id':rid,'seq':r['seq'],'lower':lower,'upper':upper,'vehicle_hash':vid,'run':run,
                       'tight':lower is not None and 0<upper-lower<=45,'direction':s['direction']}
                near_events.append(event)
                if event['tight']:
                    for old in history:
                        if not old['tight'] or not 1<=r['seq']-old['seq']<=12:continue
                        low=event['lower']-old['upper'];high=event['upper']-old['lower']
                        if not 0<low<=high<=1800:continue
                        travel.append({'route_id':rid,'from_seq':old['seq'],'to_seq':r['seq'],'hour':hour(old['upper']),
                                       'lower_seconds':low,'upper_seconds':high,'mid_seconds':(low+high)/2,'vehicle_hash':vid,'run':run})
                history.append(event);history=history[-12:]
            previous=r
    crossing_groups=defaultdict(list)
    for r in crossings:crossing_groups[r['route_id'],r['seq']].append(r)
    headway_rows=[]
    for (rid,seq),rows in crossing_groups.items():
        rows.sort(key=lambda r:r['midpoint'])
        for a,b in zip(rows,rows[1:]):
            if not(a['tight'] and b['tight']) or not(15<=hour(a['midpoint'])<19 and 15<=hour(b['midpoint'])<19):continue
            low=b['lower']-a['upper'];high=b['upper']-a['lower']
            if not 0<low<=high<=3600:continue
            headway_rows.append({'route_id':rid,'route':names[rid],'seq':seq,'stop':b['stop'],'stop_id':b['stop_id'],'direction':b['direction'],
                                 'hour':hour(b['midpoint']),'nominal_minutes':nominal[rid]/60,'headway_lower_seconds':low,
                                 'headway_upper_seconds':high,'headway_mid_seconds':(low+high)/2,
                                 'less_than_70pct_nominal_even_at_upper_bound':high<nominal[rid]*.7,
                                 'greater_than_130pct_nominal_even_at_lower_bound':low>nominal[rid]*1.3,
                                 'first_vehicle':a['vehicle_hash'],'second_vehicle':b['vehicle_hash']})
    write('headway_interval_pairs.private.csv',headway_rows)
    headway_cells=[]
    for key,rows in sorted(group(headway_rows,lambda r:(r['route_id'],r['seq'])).items()):
        rid,seq=key;s=byseq[rid][seq];v=[r['headway_mid_seconds']/60 for r in rows]
        headway_cells.append({'route_id':rid,'route':names[rid],'seq':seq,'stop':s['name'],'stop_id':s['id'],'direction':s['direction'],
                              'n':len(rows),'nominal_minutes':nominal[rid]/60,'median_mid_minutes':statistics.median(v),
                              'p10_mid_minutes':q(v,.1),'p90_mid_minutes':q(v,.9),
                              'short_interval_n':sum(r['less_than_70pct_nominal_even_at_upper_bound'] for r in rows),
                              'long_interval_n':sum(r['greater_than_130pct_nominal_even_at_lower_bound'] for r in rows),
                              'independent_days':1,'is_exact_stop_arrival_headway':False})
    write('peak_headway_cells.csv',headway_cells)
    speed_rows=[]
    for p in csvread(A/'transport_observations/provider_section_speed_hourly.csv'):
        rid=p['route_id'];seq=int(p['to_seq']);indexes={int(s['seq']):i for i,s in enumerate(routes[rid]['stops'])}
        if seq not in indexes or seq-1 not in indexes:continue
        i=indexes[seq]-1;info=common['route_info'][rid];pid=info['segments'][i];motion=common['motion_profiles'][str(pid)]
        old=info['offsets'][i+1]-info['offsets'][i];new=max(motion['duration'],motion['d'][-1]/(float(p['median_speed_kmh'])/3.6))
        speed_rows.append({**p,'route':names[rid],'model_seconds':old,'monday_speed_reference_seconds':new,
                           'reference_to_model_ratio':new/old,'hypothetical_only':True,'kinematic_minimum_seconds':motion['duration']})
    write('provider_speed_model_comparison.csv',speed_rows)
    modeled=[]
    for p in travel:
        rid=p['route_id'];index={int(s['seq']):i for i,s in enumerate(routes[rid]['stops'])}
        a=index.get(p['from_seq']);b=index.get(p['to_seq'])
        if a is None or b is None or b<=a:continue
        info=common['route_info'][rid];seconds=info['offsets'][b]-info['offsets'][a]
        dist=sum(common['motion_profiles'][str(pid)]['d'][-1] for pid in info['segments'][a:b])
        if p['to_seq']-p['from_seq']<3 or dist<500:continue
        modeled.append({**p,'route':names[rid],'from_stop':byseq[rid][p['from_seq']]['name'],'to_stop':byseq[rid][p['to_seq']]['name'],
                        'direction':byseq[rid][p['to_seq']]['direction'],'model_seconds':seconds,'distance_m':dist,
                        'model_shorter_than_lower_by_15s':seconds<p['lower_seconds']-15,
                        'model_longer_than_upper_by_15s':seconds>p['upper_seconds']+15})
    write('bounded_corridor_time_pairs.private.csv',modeled)
    cells=[]
    for key,rows in group(modeled,lambda r:(r['route_id'],r['from_seq'],r['to_seq'],r['hour'])).items():
        first=rows[0];runs={(r['vehicle_hash'],r['run']) for r in rows}
        if len(runs)<5:continue
        cells.append({k:first[k] for k in ['route_id','route','from_seq','to_seq','from_stop','to_stop','direction','hour','model_seconds','distance_m']}|
                     {'pairs':len(rows),'unique_vehicle_runs':len(runs),'median_observation_lower_seconds':statistics.median(r['lower_seconds'] for r in rows),
                      'median_observation_upper_seconds':statistics.median(r['upper_seconds'] for r in rows),
                      'median_observation_mid_seconds':statistics.median(r['mid_seconds'] for r in rows),
                      'model_shorter_n':sum(r['model_shorter_than_lower_by_15s'] for r in rows),
                      'model_longer_n':sum(r['model_longer_than_upper_by_15s'] for r in rows),'independent_days':1,'includes_dwell':True})
    write('bounded_corridor_time_cells.csv',sorted(cells,key=lambda r:(r['route'],r['from_seq'],r['to_seq'],r['hour'])))
    anchor_defs=read(A/'transport_observations/empirical_transport_candidates.json')['occupancy_anchor_definitions']
    occupancy=[]
    for scenario in ['regular','peak']:
        data=read(SIM/f'public/data/capacity_v7/{scenario}-mon.json')
        targets={}
        for anchor in anchor_defs:
            rid=anchor['route_id'];index={int(s['seq']):i for i,s in enumerate(routes[rid]['stops'])};i=index.get(anchor['before_seq'])
            if i is not None and i<len(common['route_info'][rid]['segments']):targets[anchor['key']]=(rid,common['route_info'][rid]['segments'][i])
        grouped=defaultdict(list)
        for vid,rid,cap,legs in data['vehicles']:
            for a,b,pid,load in legs:
                if not 15<=int(b//3600)<19:continue
                for key,(target_rid,target_pid) in targets.items():
                    if rid==target_rid and pid==target_pid:grouped[key].append(load)
        for key,values in grouped.items():
            occupancy.append({'scenario':scenario,'anchor_key':key,'model_vehicle_passages':len(values),'model_empty_passages':sum(v<1e-6 for v in values),
                              'model_mean_load':statistics.mean(values),'model_max_load':max(values),'actual_people_counts_known':False})
    write('modeled_entry_load_peak.csv',occupancy)
    summary={'status':'PASS','primary_clean_provider_rows':sum(map(len,tracks.values())),'excluded':dict(exclusions),
             'tight_crossing_windows':sum(r['tight'] for r in crossings),'all_crossing_windows':len(crossings),
             'primary_peak_headway_pairs':len(headway_rows),'peak_headway_cells':len(headway_cells),
             'bounded_near_stop_events':sum(r['tight'] for r in near_events),'bounded_corridor_pairs':len(modeled),'bounded_corridor_cells_n5':len(cells),
             'provider_speed_cells_compared':len(speed_rows),'saved_traffic_fetches_by_route':dict(traffic_batches),
             'full_flags_by_route':{route:{k:v for (r,k),v in full.items() if r==route} for route in names.values()},
             'headway_note':'Same section-threshold crossings, interval-censored; missed buses and source revisions remain possible. Long gaps do not prove low service frequency.',
             'travel_note':'First near-stop/at-stop detections, bounded by prior observation <=45s; includes dwell, not pure driving speed.',
             'independent_mondays':1,'model_modified':False,'collector_modified':False}
    dump('diagnostic_summary.json',summary);print(json.dumps(summary,ensure_ascii=False))


def group(rows,key):
    result=defaultdict(list)
    for row in rows:result[key(row)].append(row)
    return result


if __name__=='__main__':main()
