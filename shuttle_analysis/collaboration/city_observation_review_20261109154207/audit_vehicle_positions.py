"""Verify saved bus positions and attach them to the existing paired review.

Read-only with respect to the collector, source archives, original comparison
CSVs, and model. No new upstream API calls or collection schedule changes.
"""
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter
import csv
import gzip
import hashlib
import json
import math

ROOT=Path(__file__).resolve().parent
KST=timezone(timedelta(hours=9))
FIELDS=['lat','lon','id','route_id','section_order','provided_at','captured_at','at_stop','crowd_code']


def distance(a,b):
    dy=math.radians(a[0]-b[0])
    dx=math.radians(a[1]-b[1])*math.cos(math.radians((a[0]+b[0])/2))
    return round(math.hypot(dx,dy)*6371000,1)


def main():
    manifest=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
    stops=json.loads((ROOT/'route_stops.json').read_text(encoding='utf-8'))
    byseq={rid:{int(s['seq']):s for s in rows} for rid,rows in stops.items()}
    lookup={};counts=[];pos_conflicts=0;variants={};spreads={}
    for spec in manifest['files']:
        if not spec['path'].startswith('collector-'):
            continue
        path=ROOT/spec['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==spec['sha256']
        rows=[v for line in gzip.decompress(path.read_bytes()).splitlines() for v in json.loads(line).get('vehicles',[])]
        present={k:sum(k in v and v[k] is not None for v in rows) for k in FIELDS}
        valid=sum(isinstance(v.get('lat'),(int,float)) and isinstance(v.get('lon'),(int,float)) and 33<=v['lat']<=39 and 124<=v['lon']<=132 for v in rows)
        counts.append(dict(day=spec['day'],rows=len(rows),nonmissing=present,valid_coordinate_range_rows=valid))
        for v in sorted(rows,key=lambda x:x['captured_at']):
            hashed=hashlib.sha256(v['id'].encode()).hexdigest()[:14]
            key=spec['day'],v['route_id'],hashed,v['provided_at']
            if key not in lookup:
                lookup[key]=v
                variants[key]={(v['lat'],v['lon'])}
                spreads[key]=0.0
            else:
                old=lookup[key]
                pos_conflicts+=(old['lat'],old['lon'])!=(v['lat'],v['lon'])
                variants[key].add((v['lat'],v['lon']))
                spreads[key]=max(spreads[key],distance((old['lat'],old['lon']),(v['lat'],v['lon'])))
    assert all(r['rows']==r['valid_coordinate_range_rows'] and all(n==r['rows'] for n in r['nonmissing'].values()) for r in counts)
    source=ROOT/'paired_section_observations.csv'
    original_digest=hashlib.sha256(source.read_bytes()).hexdigest()
    with source.open(encoding='utf-8-sig') as handle:
        rows=list(csv.DictReader(handle))
    extra=['from_lat','from_lon','to_lat','to_lon','from_at_stop','to_at_stop','from_position_lag_seconds','to_position_lag_seconds',
           'from_distance_to_reference_stop_m','to_distance_to_reference_stop_m',
           'from_position_variant_count','to_position_variant_count','from_position_spread_m','to_position_spread_m']
    for row in rows:
        for side in ['from','to']:
            at=int(datetime.fromisoformat(row[side+'_time_kst']).timestamp())
            key=row['day'],row['route_id'],row['vehicle_hash'],at
            observation=lookup[key]
            assert str(observation['section_order'])==row[side+'_seq']
            assert observation['crowd_code']==row[side+'_grade']
            stop=byseq[row['route_id']][int(row[side+'_seq'])]
            row[side+'_lat']=observation['lat']
            row[side+'_lon']=observation['lon']
            row[side+'_at_stop']=observation['at_stop']
            row[side+'_position_lag_seconds']=round(observation['captured_at']-observation['provided_at'],3)
            row[side+'_distance_to_reference_stop_m']=distance((observation['lat'],observation['lon']),(stop['lat'],stop['lon']))
            row[side+'_position_variant_count']=len(variants[key])
            row[side+'_position_spread_m']=spreads[key]
    target=ROOT/'paired_section_observations_with_positions.csv'
    with target.open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,list(rows[0]));writer.writeheader();writer.writerows(rows)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original_digest
    for spec in manifest['files']:
        assert hashlib.sha256((ROOT/spec['path']).read_bytes()).hexdigest()==spec['sha256']
    result=dict(status='PASS',snapshot_created_at=manifest['created_at'],scope='supplied snapshot, not a fresh export of the continuing live collector',
        original_vehicle_rows=sum(x['rows'] for x in counts),days=counts,duplicate_provider_position_conflict_rows=pos_conflicts,
        provider_keys_with_position_variants=sum(len(v)>1 for v in variants.values()),
        maximum_position_spread_from_first_capture_m=max(spreads.values()),
        position_selection_rule='earliest captured position for each provider key, with variant count/spread preserved',
        paired_rows_with_coordinates=len(rows),coordinate_endpoint_joins_verified=len(rows)*2,
        output=target.name,output_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        added_columns=extra,source_comparison_unchanged=True,collector_modified=False,new_provider_calls=0,
        source_definition_url='https://www.data.go.kr/data/15000332/openapi.do',
        limitations=['Coordinates are provider positions, not independently ground-truthed GPS.',
                     'Broad coordinate range checks do not prove stop passage or positional accuracy.',
                     'Reference-stop distances are derived straight-line distances, not measured boarding locations.',
                     'Stored at_stop False does not retain a separate raw-field availability flag.',
                     'Grade changes indicate ordinal net occupancy signals, not passenger boardings or unmet queue demand.'])
    (ROOT/'vehicle_position_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['status','original_vehicle_rows','paired_rows_with_coordinates','coordinate_endpoint_joins_verified','collector_modified','new_provider_calls']}))


if __name__=='__main__':
    main()
