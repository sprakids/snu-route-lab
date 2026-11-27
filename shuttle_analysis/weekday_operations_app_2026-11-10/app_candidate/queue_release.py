"""Data-only contract for published FIFO queue models. Never executes model code."""
import hashlib
import json
import math
import re
from pathlib import Path
from datetime import datetime

from shuttle_timetable import KST

SCHEMA='snu_queue_release_v1'
ALGORITHM='latest-v5-all-shuttle-clock-fifo-v3'
OPERATIONS_ALGORITHM='latest-v5-all-shuttle-clock-fifo-v4'
RELEASE_PATTERN=re.compile(r'\d{12}',re.ASCII)
MAX_PAYLOAD=4_000_000

def encode(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')

def digest(raw):return hashlib.sha256(raw).hexdigest()

def release_name(at=None):
    return (at or datetime.now(KST)).astimezone(KST).strftime('%y%m%d%H%M%S')

def release_time(name):
    if not isinstance(name,str) or not RELEASE_PATTERN.fullmatch(name):raise ValueError('release_name')
    return datetime.strptime('20'+name,'%Y%m%d%H%M%S').replace(tzinfo=KST)

def stamp_model(data,at=None):
    """Keep the algorithm version separate from the user-facing release name."""
    data.pop('release',None)
    data['model']['algorithm_id']=OPERATIONS_ALGORITHM if data.get('city_operations') else ALGORITHM
    data['model']['id']=release_name(at)
    return data

def compatibility(data):
    # A data update cannot silently change the app's clock, topology or capacity.
    routes={}
    for rid,r in data['routes'].items():
        routes[rid]={k:r.get(k) for k in ('n','loop','offsets','anchor','capacity','profile_route_id','profile_index_map')}
        routes[rid]['stops']=[{k:s[k] for k in ('id','board_allowed')} for s in r['stops']]
    contract={'schema':data['schema'],'unit':data['unit'],
        'travel_clock_model':data['travel_clock_model'],'algorithm':ALGORITHM,'routes':routes}
    if data.get('city_wait'):
        city=data['city_wait'];contract['city_wait']={k:city[k] for k in ('schema','algorithm_id','network_sha256')}
        contract['city_wait']['services']={key:{k:s.get(k) for k in ('route_id','seq','stop_id','members')} for key,s in city['services'].items()}
    return digest(encode(contract))

def content_digest(data):
    value={k:v for k,v in data.items() if k!='release'}
    value['model']={k:v for k,v in value['model'].items() if k!='id'}
    return digest(encode(value))

def number(value,low=0,high=1e8):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError('invalid_number')

def integer(value,low,high):
    if type(value) is not int or not low<=value<=high:raise ValueError('invalid_integer')

def validate(data,expected_compatibility,*,check_profiles=False):
    # Serialize once to reject NaN/Infinity anywhere, including unused metadata.
    if len(encode(data))>MAX_PAYLOAD:raise ValueError('payload_size')
    if data.get('schema')!='all_student_shuttle_queue_v3' or data.get('unit')!='weighted_expected_trip_events':raise ValueError('schema')
    m=data['model'];release_time(m['id'])
    if m.get('algorithm_id') not in (ALGORITHM,OPERATIONS_ALGORITHM) or m.get('model_only') is not True or m.get('calibrated') is not False or data.get('observed_queue') is not False:raise ValueError('algorithm')
    if (m['algorithm_id']==OPERATIONS_ALGORITHM)!=bool(data.get('city_operations')):raise ValueError('operations_algorithm')
    if m['historical_beta']!=0 or m['live_beta']!=0:raise ValueError('city_pressure')
    if len(m['factor_bounds'])!=2:raise ValueError('factor_bounds')
    number(m['factor_bounds'][0],.1,1);number(m['factor_bounds'][1],1,3)
    number(m['live_fresh_seconds'],0,600);number(m['live_max_age_seconds'],m['live_fresh_seconds'],3600)
    number(m['live_decay_seconds'],1,86400)
    if compatibility(data)!=expected_compatibility:raise ValueError('incompatible_clock_or_stops')
    integer(m['step_seconds'],1,60)
    if 300%m['step_seconds']:raise ValueError('step')
    if not 1<=len(m['phases'])<=8 or not 1<=len(m['sensitivity'])<=3:raise ValueError('scenario_count')
    for p in m['phases']:number(p,0,1)
    for s in m['sensitivity']:number(s['demand'],.1,3);number(s['reserve'],0,.8)
    if not any(s['demand']==1 for s in m['sensitivity']):raise ValueError('central_scenario')
    if data.get('latest_simulation',{}).get('independent_status')!='PASS':raise ValueError('unverified_source')
    integer(data['course_end_events'],0,1_000_000)
    if not isinstance(data.get('limitations'),list) or not all(isinstance(s,str) for s in data['limitations']):raise ValueError('limitations')
    count=0
    for rid,r in data['routes'].items():
        n=r['n'];integer(n,1,80)
        if len(r['stops'])!=n or not 0<=r['anchor']<n:raise ValueError('stop_count')
        for key,width in (('flows',4),('ready_flows',4),('ready_packets',5)):
            for row in r.get(key,[]):
                if len(row)!=width:raise ValueError('row_width')
                day,index,at,mass=row[:4];integer(day,0,6);integer(index,0,n-1)
                number(at,0,172800 if key!='flows' else 2880);number(mass,0,100_000)
                if not r['stops'][index]['board_allowed']:raise ValueError('boarding_forbidden')
                if width==5 and row[4] is not None:number(row[4],at,172800)
                count+=1
        for key,rows in r['od'].items():
            day,index=map(int,key.split(':'));integer(day,0,6);integer(index,0,n-1)
            if not rows or len(rows)>n:raise ValueError('od')
            for delta,weight in rows:integer(delta,1,n);number(weight,0,1_000_000)
            if sum(v for _,v in rows)<=0:raise ValueError('od_mass')
        if r.get('profile_route_id'):
            primary=data['routes'][r['profile_route_id']]
            if primary.get('profile_route_id') or len(r['profile_index_map'])!=n:raise ValueError('profile_alias')
            for i in r['profile_index_map']:integer(i,0,primary['n']-1)
    if count>200_000:raise ValueError('row_count')
    if data.get('city_wait'):validate_city(data['city_wait'])
    if data.get('city_operations'):
        from city_operations import validate_operations
        raw=(Path(__file__).parent/'data/network.json').read_bytes()
        validate_operations(data['city_operations'],json.loads(raw),digest(raw))
        city=data.get('city_wait',{})
        if city.get('delay_scale_policy')!='absolute_audited_clock' or city.get('operation_revision')!=data['city_operations']['revision']:
            raise ValueError('operations_fifo_clock')
    if check_profiles:
        from automatic_queue import simulate
        for rid,r in data['routes'].items():
            if r.get('profile_route_id'):continue
            for day in range(5):
                profile=simulate({**r,'id':rid},day,m['phases'][0],1,.1,lambda i,t:1,m['step_seconds'])
                error=abs(profile['input_mass']-profile['boarded_mass']-profile['exited_mass']-profile['remaining_mass'])
                if error>1e-5 or profile['max_load']>profile['capacity']+1e-6:raise ValueError('mass_or_capacity')
    return data

def validate_city(city):
    if city.get('schema')!='city_conditional_fifo_v1' or city.get('algorithm_id')!='frozen_v5_city_compatible_fifo_v1':raise ValueError('city_algorithm')
    if city.get('independent_status')!='PASS' or city.get('external_background_passengers_included') is not False:raise ValueError('city_source')
    path=Path(__file__).parent/'data/network.json';raw=path.read_bytes();network=json.loads(raw)
    if digest(raw)!=city['network_sha256']:raise ValueError('city_network')
    routes={r['id']:r for r in network['routes']}
    if {s.get('route_id') for s in city['services'].values() if s.get('route_id')}!=set(routes):raise ValueError('city_route_scope')
    if city['bin_minutes']!=5 or city['start_minute']!=680 or city['end_minute']!=1390:raise ValueError('city_clock')
    for name in ('term_start','term_end'):datetime.strptime(city[name],'%Y-%m-%d')
    expected=set()
    for key,s in city['services'].items():
        number(s['reference_headway_seconds'],1,7200)
        if 'reference_headway_by_weekday' in s:
            if set(s['reference_headway_by_weekday'])!=set(map(str,range(5))):raise ValueError('city_reference_days')
            for seconds in s['reference_headway_by_weekday'].values():number(seconds,1,7200)
        if not s['members'] or len(s['members'])>8:raise ValueError('city_members')
        for rid,seq in s['members']:
            if rid not in routes or not any(p['seq']==seq and p['id']==s['stop_id'] for p in routes[rid]['stops']):raise ValueError('city_stop')
        for day in range(5):expected.add(f'{day}:{key}')
    if set(city['profiles'])!=expected:raise ValueError('city_profile_scope')
    count=0
    for rows in city['profiles'].values():
        previous=-1
        for row in rows:
            if len(row)!=5:raise ValueError('city_row')
            minute,seconds,skips,mass,censored=row
            integer(minute,680,1385);integer(censored,0,3);number(mass,0,1_000_000)
            if minute%5 or minute<=previous:raise ValueError('city_bins')
            previous=minute
            if censored:
                if seconds is not None or skips is not None:raise ValueError('city_censored')
            else:number(seconds,0,86400);number(skips,0,1000)
            count+=1
    if count>100_000:raise ValueError('city_rows')
