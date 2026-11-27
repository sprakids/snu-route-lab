"""Frozen empirical inputs for entry occupancy signals and travel-time updates.

No original source, app, collector, or public replay is changed by this builder.
Provider section-speed samples and vehicle near-stop passage times are separate.
"""
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta
import ast, csv, gzip, hashlib, json, math, statistics

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'transport_observations'
SIM=ROOT.parent.parent/'simulation_viewer_2026-11-07'
KST=timezone(timedelta(hours=9))


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dt(at):return datetime.fromtimestamp(at,KST)
def q(v,p):
    v=sorted(v);return v[min(len(v)-1,int((len(v)-1)*p))]
def metres(a,b):
    return math.hypot((a[0]-b[0])*111195,(a[1]-b[1])*111195*math.cos(math.radians((a[0]+b[0])/2)))
def readcsv(p):
    with p.open(encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def writecsv(name,rows):
    if not rows:return
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
def dump(name,d):(OUT/name).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    OUT.mkdir(exist_ok=True)
    manifest=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
    for f in manifest['files']:assert digest(ROOT/f['path'])==f['sha256']
    stops=json.loads((ROOT/'route_stops.json').read_text(encoding='utf-8'))
    byseq={rid:{int(s['seq']):s for s in r} for rid,r in stops.items()}
    parsed=ast.parse((SIM/'prepare_city.py').read_text(encoding='utf-8'))
    assignment=next(n for n in parsed.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CAMPUS_STOP_NAMES' for t in n.targets))
    names=set(ast.literal_eval(assignment.value.args[0].func.value).split('|'))
    def zone(rid,seq):
        a,b=byseq[rid].get(seq-1),byseq[rid].get(seq)
        if not a or not b:return 'unmapped'
        inside=(a['name'] in names,b['name'] in names)
        return 'campus_corridor' if all(inside) else 'boundary_corridor' if any(inside) else 'external_corridor'

    provider={};raw=[];raw_counter=Counter()
    for spec in manifest['files']:
        if not spec['path'].startswith('collector-'):continue
        for line in gzip.decompress((ROOT/spec['path']).read_bytes()).splitlines():
            record=json.loads(line)
            raw.extend(dict(v,day=spec['day']) for v in record.get('vehicles',[]))
            for r in record.get('route_records',[]):
                traffic=r.get('traffic')
                if not traffic:continue
                at=traffic['fetched_at'];date=dt(at)
                for seq,cell in traffic.get('sections',{}).items():
                    v=cell.get('speed_kmh');seq=int(seq)
                    raw_counter['speed_rows']+=1
                    if not isinstance(v,(int,float)) or not .5<=v<=100 or seq-1 not in byseq[r['route_id']] or seq not in byseq[r['route_id']]:
                        raw_counter['speed_unusable']+=1;continue
                    key=r['route_id'],seq,at
                    row=dict(day=date.date().isoformat(),weekday=date.weekday(),hour=date.hour,route_id=r['route_id'],to_seq=seq,
                             from_stop=byseq[r['route_id']][seq-1]['name'],to_stop=byseq[r['route_id']][seq]['name'],
                             direction=byseq[r['route_id']][seq]['direction'],fetched_at=at,speed_kmh=v,zone=zone(r['route_id'],seq))
                    if key in provider:assert provider[key]['speed_kmh']==v
                    provider[key]=row
    writecsv('provider_section_speed_samples.csv',list(provider.values()))
    grouped=defaultdict(list)
    for r in provider.values():grouped[r['day'],r['weekday'],r['hour'],r['route_id'],r['to_seq'],r['zone']].append(r['speed_kmh'])
    profiles=[]
    for key,values in sorted(grouped.items()):
        day,weekday,hour,rid,seq,z=key
        profiles.append(dict(day=day,weekday=weekday,hour=hour,route_id=rid,to_seq=seq,from_stop=byseq[rid][seq-1]['name'],
            to_stop=byseq[rid][seq]['name'],direction=byseq[rid][seq]['direction'],zone=z,n=len(values),
            median_speed_kmh=statistics.median(values),p10_speed_kmh=q(values,.1),p90_speed_kmh=q(values,.9)))
    writecsv('provider_section_speed_hourly.csv',profiles)
    # Stable day medians are the unit for a pooled reference. This does not
    # treat a partial Monday or repeated fetches as an independent weekday.
    daily=defaultdict(list)
    for row in provider.values():daily[row['route_id'],row['to_seq'],row['day']].append(row['speed_kmh'])
    aggregate=defaultdict(list)
    for (rid,seq,day),values in daily.items():aggregate[rid,seq].append((day,statistics.median(values)))
    pooled={f'{rid}:{seq}':dict(speed_kmh=statistics.median(v for _,v in values),days=len(values),dates=[d for d,_ in sorted(values)],
        zone=zone(rid,seq),source='median_of_saved_day_medians',cohort='single_Monday_reference_not_out_of_sample_fit') for (rid,seq),values in aggregate.items()}

    unique={}
    for row in sorted(raw,key=lambda v:v['captured_at']):unique.setdefault((row['day'],row['route_id'],row['id'],row['provided_at']),row)
    ambiguous={tuple(k) for k in json.loads((ROOT/'ambiguous_provider_keys.private.json').read_text(encoding='utf-8'))}
    tracks=defaultdict(list);rejections=Counter()
    for row in unique.values():
        if (row['route_id'],row['id'],row['provided_at']) in ambiguous:
            rejections['ambiguous_provider_key']+=1;continue
        seq=int(row['section_order']);stop=byseq[row['route_id']].get(seq)
        age=row['captured_at']-row['provided_at']
        if not stop or not 0<=age<=300 or dt(row['provided_at']).date().isoformat()!=row['day']:
            rejections['invalid_or_stale']+=1;continue
        tracks[row['day'],row['route_id'],row['id']].append(dict(row,seq=seq,direction=stop['direction'],near_stop_m=metres((row['lat'],row['lon']),(stop['lat'],stop['lon']))))
    passages=[];times=[]
    for (day,rid,vehicle),rows in tracks.items():
        rows.sort(key=lambda r:r['provided_at']);history=[];seen=set();prior=None;run=0
        for row in rows:
            if prior is None or row['seq']<prior['seq'] or row['direction']!=prior['direction'] or row['provided_at']-prior['provided_at']>300:
                history=[];seen=set();run+=1
            prior=row
            if not row['at_stop'] or row['near_stop_m']>60 or row['seq'] in seen:continue
            seen.add(row['seq']);seq=row['seq'];hashed=hashlib.sha256(vehicle.encode()).hexdigest()[:14]
            passages.append(dict(day=day,route_id=rid,vehicle_hash=hashed,run=run,seq=seq,at=row['provided_at'],at_kst=dt(row['provided_at']).isoformat(),near_stop_m=round(row['near_stop_m'],1)))
            for old in history:
                gap=seq-old['seq'];seconds=row['provided_at']-old['provided_at']
                if not 1<=gap<=12 or not 0<seconds<=1800:continue
                links=[byseq[rid][k] for k in range(old['seq']+1,seq+1)]
                dist=sum(s['segment_m'] for s in links)
                effective=dist/seconds*3.6
                if not .5<=effective<=80:
                    rejections['implausible_passage_speed']+=1;continue
                zones={zone(rid,k) for k in range(old['seq']+1,seq+1)}
                times.append(dict(day=day,weekday=dt(old['provided_at']).weekday(),hour=dt(old['provided_at']).hour,route_id=rid,
                    vehicle_hash=hashed,run=run,direction=row['direction'],from_seq=old['seq'],to_seq=seq,
                    from_stop=byseq[rid][old['seq']]['name'],to_stop=byseq[rid][seq]['name'],
                    from_at_kst=dt(old['provided_at']).isoformat(),to_at_kst=dt(row['provided_at']).isoformat(),seconds=seconds,
                    road_m=round(dist,1),effective_kmh=round(effective,3),zone=next(iter(zones)) if len(zones)==1 else 'mixed_corridors',
                    includes_unseparated_dwell=True,exact_arrival_times=False))
            history.append(row);history=history[-12:]
    writecsv('near_stop_passage_events.csv',passages)
    writecsv('vehicle_passage_time_samples.csv',times)
    samplegroups=defaultdict(list)
    for row in times:samplegroups[row['weekday'],row['hour'],row['route_id'],row['from_seq'],row['to_seq']].append(row)
    travel_cells={}
    for key,values in samplegroups.items():
        weekday,hour,rid,a,b=key;durations=[x['seconds'] for x in values];days=sorted({x['day'] for x in values})
        travel_cells[f'{weekday}:{hour}:{rid}:{a}:{b}']=dict(n=len(values),days=len(days),dates=days,
            median_seconds=statistics.median(durations),p10_seconds=q(durations,.1),p90_seconds=q(durations,.9),
            unit='near_stop_observation_time_difference_not_exact_trip_time',includes_unseparated_dwell=True,calibrated=False)

    anchors=[('100100250',4,5,'campus_entry'),('100100250',55,56,'campus_entry'),('100100251',36,37,'campus_entry'),
             ('100100253',4,5,'campus_entry'),('100100253',56,57,'campus_entry'),('120900011',11,12,'back_gate_reference'),
             ('120900012',11,12,'back_gate_reference'),('100100252',6,7,'external_gate_pickup'),('100100263',29,30,'external_gate_pickup'),
             ('100100521',69,70,'external_gate_pickup')]
    route_names={v['route_id']:v['route_name'] for v in raw};anchor_defs=[]
    for rid,a,b,kind in anchors:
        anchor_defs.append(dict(key=f'{rid}:{a}:{b}',route_id=rid,route=route_names[rid],before_seq=a,after_seq=b,
            before_stop=byseq[rid][a]['name'],after_stop=byseq[rid][b]['name'],direction=byseq[rid][b]['direction'],kind=kind,
            boundary_is_reference_not_surveyed_property_line=True))
    entry_groups=defaultdict(list)
    for row in readcsv(ROOT/'section_visits.csv'):
        for anchor in anchor_defs:
            if row['route_id']!=anchor['route_id']:continue
            if int(row['seq'])==anchor['before_seq']:stage='before'
            elif int(row['seq'])==anchor['after_seq']:stage='after'
            else:continue
            entry_groups[row['day'],int(row['hour']),anchor['key'],stage].append(row)
    entry_rows=[]
    for (day,hour,key,stage),values in sorted(entry_groups.items()):
        anchor=next(a for a in anchor_defs if a['key']==key);codes=Counter(v['grade'] for v in values)
        entry_rows.append(dict(day=day,hour=hour,key=key,stage=stage,route=anchor['route'],direction=anchor['direction'],
            boundary_kind=anchor['kind'],reference_stop=anchor[stage+'_stop'],n=len(values),valid_n=sum(codes[g] for g in ['3','4','5','6']),
            grade3=codes['3'],grade4=codes['4'],grade5=codes['5'],grade6=codes['6'],unavailable=codes['0'],unique_vehicles=len({v['vehicle_hash'] for v in values})))
    writecsv('entry_and_gate_crowd_hourly.csv',entry_rows)
    paired=[]
    for row in readcsv(ROOT/'paired_section_observations_with_positions.csv'):
        key=f"{row['route_id']}:{row['from_seq']}:{row['to_seq']}"
        if key in {a['key'] for a in anchor_defs}:paired.append(row)
    writecsv('same_vehicle_boundary_pairs.csv',paired)
    payload=dict(schema='snu_empirical_transport_candidates_v1',source_manifest_sha256=digest(ROOT/'manifest.json'),
        source_cutoff_kst=manifest['created_at'],provider_hourly=profiles,pooled_speed_reference=pooled,vehicle_passage_cells=travel_cells,
        occupancy_anchor_definitions=anchor_defs,entry_profiles=entry_rows,
        constraints=dict(grade_to_person_conversion=False,external_background_count_observed=False,source_days=manifest['dates'],
            include_source_day_only_before_query=True,do_not_mix_passage_dwell_with_road_speed=True,
            shuttle_observation_available=False,shuttle_shared_road_proxy_requires_geometry_match=True),
        calibrated=False,training_validation_split_available=False)
    dump('empirical_transport_candidates.json',payload)
    result=dict(status='PASS',source_archives_unchanged=True,provider_samples=len(provider),provider_raw_speed_rows=raw_counter['speed_rows'],
        provider_unusable=raw_counter['speed_unusable'],provider_hour_cells=len(profiles),reference_links=len(pooled),
        near_stop_events=len(passages),passage_time_samples=len(times),passage_cells=len(travel_cells),
        measured_cells_meeting_existing_five_samples_two_dates=sum(c['n']>=5 and c['days']>=2 for c in travel_cells.values()),
        boundary_anchors=len(anchor_defs),entry_hour_cells=len(entry_rows),same_vehicle_boundary_pairs=len(paired),rejections=dict(rejections),
        app_changed=False,public_model_changed=False)
    for f in manifest['files']:assert digest(ROOT/f['path'])==f['sha256']
    dump('verification.json',result);print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
