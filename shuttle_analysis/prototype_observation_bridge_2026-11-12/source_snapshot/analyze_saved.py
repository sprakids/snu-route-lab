"""Describe saved observations; do not fit, promote, or modify any model."""
from collections import Counter, defaultdict, deque
import csv
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
STOPS = json.loads((ROOT.parent / 'collector/route_stops.json').read_text(encoding='utf-8'))
NAMES = dict(zip(['100100250','100100251','100100252','100100253','100100263','100100521','120900011','120900012'],
                ['5511','5513','5515','5516','5528','6515','관악02-1','관악02-2']))
STOP = {(r, int(s['seq'])):s for r, values in STOPS.items() for s in values}

def stamp(at): return datetime.fromtimestamp(at, KST)
def q(values, p):
    a = sorted(values)
    return a[max(0, math.ceil(len(a)*p)-1)] if a else None
def summary(values, headway=False):
    if not values:return {'n':0}
    mean = statistics.mean(values)
    result = {'n':len(values),'mean_seconds':mean,'median_seconds':q(values,.5),
            'p10_seconds':q(values,.1),'p90_seconds':q(values,.9),
            'min_seconds':min(values),'max_seconds':max(values),
            'cv':statistics.pstdev(values)/mean if mean else None}
    if headway:result['random_arrival_wait_seconds']=sum(x*x for x in values)/(2*sum(values)) if sum(values) else None
    return result
def distance(v,s):
    return math.hypot((v['lon']-s['lon'])*math.cos(v['lat']*math.pi/180)*111195,
                      (v['lat']-s['lat'])*111195)
def write_json(path,d):path.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def write_csv(path,rows):
    rows=list(rows)
    if not rows:return
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

def analyze():
    aggregates=[]
    for p in sorted((ROOT/'aggregates').glob('*.json')):
        day=p.stem
        for x in json.loads(p.read_text(encoding='utf-8')).get('rows',[]):
            aggregates.append({'day':day,**x})
    daily_grade=defaultdict(Counter);route_grade=defaultdict(Counter);hour_grade=defaultdict(Counter);section_grade=defaultdict(Counter)
    for x in aggregates:
        r=x['route'];h=int(x['slot'])//4;g=x['grade'];n=x['n'];seq=int(x['section'])
        daily_grade[x['day']][g]+=n
        if x['day']>='2026-11-09':
            route_grade[r][g]+=n;hour_grade[(r,h)][g]+=n;section_grade[(r,seq,h)][g]+=n
    quality=[];headways=defaultdict(list);travels=defaultdict(list);transitions=defaultdict(Counter)
    dwell=defaultdict(list);passages=[];traffic_rows=[]
    rebuilt_grade=defaultdict(Counter)
    for path in sorted((ROOT/'raw').glob('*.gz')):
        day=path.name[:10];seen=set();progress={};last_passage={};stop_history=defaultdict(list)
        dwell_start={};valid_ages=[];poll_ages=[];rows_by_route=defaultdict(Counter);vehicle_ids=defaultdict(set)
        per_route_polls=defaultdict(list);errors=Counter();count=0;total=0;duplicate=0;missing=0;seq_reset=0;previous_trip={}
        with gzip.open(path,'rt',encoding='utf-8') as stream:
            for line in stream:
                record=json.loads(line);count+=1
                route_records=record.get('route_records') or [record]
                for rr in route_records:
                    rid=rr.get('route_id')
                    if rr.get('error'):errors[(rid,str(rr['error']))]+=1
                    if rid:per_route_polls[rid].append(rr.get('at',record['at']))
                    tf=rr.get('traffic')
                    if tf and rid:
                        for seq, point in tf.get('sections',{}).items():
                            traffic_rows.append({'day':day,'route':rid,'hour':stamp(tf['fetched_at']).hour,
                              'seq':int(seq),'speed_kmh':point['speed_kmh']})
                for v in record.get('vehicles',[]):
                    total+=1;r=v.get('route_id');vid=v.get('id');at=v.get('provided_at')
                    if r not in NAMES or not vid or not at or not str(v.get('section_order','')).isdigit():missing+=1;continue
                    seq=int(v['section_order']);captured=v.get('captured_at',record['at']);age=captured-at;poll_ages.append(age)
                    key=(r,vid,at)
                    if key in seen:duplicate+=1;continue
                    seen.add(key);vehicle_ids[r].add(vid);rows_by_route[r]['unique_vehicle_times']+=1
                    rows_by_route[r]['grade_'+str(v.get('crowd_code','missing'))]+=1
                    rows_by_route[r]['full_known']+=v.get('full_known') is True
                    rows_by_route[r]['full_true']+=v.get('full_known') is True and v.get('full') is True
                    valid_ages.append(age)
                    pk=(r,vid);previous=progress.get(pk)
                    if stamp(at).date().isoformat()!=day or (previous and at<=previous['at']):continue
                    fresh=not previous or seq!=previous['seq'] or at-previous['at']>1800
                    reset=bool(previous and (seq<previous['seq'] or at-previous['at']>1800))
                    trip=previous_trip.get(pk,0)+int(reset);previous_trip[pk]=trip
                    if reset:seq_reset+=1;stop_history[pk]=[]
                    grade=str(v.get('crowd_code','0'));known=grade in ['3','4','5','6']
                    if fresh and known:
                        rebuilt_grade[day][grade]+=1
                        passages.append((day,r,vid,trip,seq,at,int(grade)-3))
                    if fresh and previous and not reset and known and previous['grade'] in ['3','4','5','6']:
                        seconds=at-previous['at'];step=seq-previous['seq']
                        if 0<step<=3 and 0<seconds<=180:
                            transitions[(day,r,previous['seq'],seq,stamp(at).hour)][int(grade)-int(previous['grade'])]+=1
                    stop=STOP.get((r,seq));prior=v.get('previous_observation')
                    near=bool(stop and distance(v,stop)<=60)
                    checked=bool(v.get('at_stop') and near and prior and 0<at-prior.get('provided_at',0)<=120)
                    if checked and not any(p['seq']==seq for p in stop_history[pk]):
                        lp=last_passage.get((r,seq));gap=at-lp['at'] if lp else 0
                        if lp and lp['vid']!=vid and 15<=gap<=3600:
                            headways[(day,r,seq,stamp(at).hour)].append(gap)
                        if not lp or at>lp['at']:last_passage[(r,seq)]={'at':at,'vid':vid}
                        for p in stop_history[pk]:
                            seconds=at-p['at'];fr=STOP.get((r,p['seq']))
                            if fr and seq>p['seq'] and seq-p['seq']<=12 and 0<seconds<=1800:
                                meters=distance({'lat':stop['lat'],'lon':stop['lon']},fr)
                                if seconds>=meters/(100/3.6):travels[(day,r,p['seq'],seq,stamp(p['at']).hour)].append(seconds)
                        stop_history[pk].append({'seq':seq,'at':at});stop_history[pk]=stop_history[pk][-12:]
                    # Stop-flag run only: an interval-censored GPS proxy, not boarding dwell truth.
                    dk=(r,vid,seq)
                    if v.get('at_stop') and near:
                        if dk not in dwell_start:dwell_start[dk]=(at,at)
                        else:dwell_start[dk]=(dwell_start[dk][0],at)
                    for old in [x for x in dwell_start if x[:2]==pk and (x[2]!=seq or not v.get('at_stop') or not near)]:
                        start,end=dwell_start.pop(old)
                        if 0<end-start<=600:dwell[(day,r,old[2])].append(end-start)
                    progress[pk]={'seq':seq,'at':at,'grade':grade}
        qs={'day':day,'archive_batches':count,'raw_vehicle_rows':total,'exact_repeat_vehicle_timestamp_rows':duplicate,
             'unique_vehicle_timestamps':len(seen),'invalid_key_rows':missing,'sequence_or_gap_resets':seq_reset,
             'source_age_unique_seconds':summary(valid_ages),'source_age_poll_seconds':summary(poll_ages),
             'source_age_unique_over_90s':sum(a>90 for a in valid_ages),'source_age_unique_over_600s':sum(a>600 for a in valid_ages),
             'errors':[{'route':r,'error':e,'n':n} for (r,e),n in errors.items()],
             'routes':[{ 'route':r,'name':NAMES[r],'vehicles':len(vehicle_ids[r]),**rows_by_route[r],
               'archived_route_responses':len(per_route_polls[r]),
               'first_captured':stamp(min(per_route_polls[r])).isoformat() if per_route_polls[r] else None,
               'last_captured':stamp(max(per_route_polls[r])).isoformat() if per_route_polls[r] else None}
              for r in NAMES]}
        quality.append(qs)
        print('processed',day,'rows',total,'unique',len(seen),'stop_intervals',sum(len(v) for k,v in headways.items() if k[0]==day),flush=True)
    headway_rows=[{'day':d,'route':r,'name':NAMES[r],'seq':s,'stop':STOP.get((r,s),{}).get('name'),'ars':STOP.get((r,s),{}).get('ars'),
                 'hour':h,**summary(v,headway=True)} for (d,r,s,h),v in sorted(headways.items())]
    travel_rows=[{'day':d,'route':r,'name':NAMES[r],'from_seq':a,'to_seq':b,'from_stop':STOP.get((r,a),{}).get('name'),
                 'to_stop':STOP.get((r,b),{}).get('name'),'hour':h,**summary(v)} for (d,r,a,b,h),v in sorted(travels.items())]
    write_csv(ROOT/'headways_by_day_route_stop_hour.csv',headway_rows)
    write_csv(ROOT/'travel_by_day_route_segment_hour.csv',travel_rows)
    write_csv(ROOT/'deduplicated_grade_passages.csv',({'day':d,'route':r,'vehicle':v,'trip':t,'seq':s,'at':a,'grade':g} for d,r,v,t,s,a,g in passages))
    write_json(ROOT/'observed_intervals.json',{'headways':[{'day':d,'route':r,'seq':s,'hour':h,'seconds':v} for (d,r,s,h),v in sorted(headways.items())],
              'travel':[{'day':d,'route':r,'from_seq':a,'to_seq':b,'hour':h,'seconds':v} for (d,r,a,b,h),v in sorted(travels.items())]})
    route_summary=[]
    for r in NAMES:
        g=route_grade[r];n=sum(g.values())
        route_summary.append({'route':r,'name':NAMES[r],'valid_grade_passages_weekdays':n,'counts':dict(g),
          'congested_fraction':(g['5']+g['6'])/n if n else None,
          'unique_vehicle_times_all_days':sum(x.get('unique_vehicle_times',0) for day in quality for x in day['routes'] if x['route']==r),
          'full_known_all_days':sum(x.get('full_known',0) for day in quality for x in day['routes'] if x['route']==r),
          'full_true_all_days':sum(x.get('full_true',0) for day in quality for x in day['routes'] if x['route']==r)})
    section_rows=[]
    for (r,s,h),g in sorted(section_grade.items()):
        n=sum(g.values());stop=STOP.get((r,s),{})
        section_rows.append({'route':r,'name':NAMES[r],'seq':s,'stop':stop.get('name'),'ars':stop.get('ars'),
         'direction':stop.get('direction'),'hour':h,'n':n,'congested':g['5']+g['6'],'congested_fraction':(g['5']+g['6'])/n,
         'mean_ordinal_grade':sum((int(k)-3)*v for k,v in g.items())/n})
    write_csv(ROOT/'grades_by_route_section_hour_weekdays.csv',section_rows)
    write_csv(ROOT/'grade_transitions.csv',({'day':d,'route':r,'name':NAMES[r],'from_seq':a,'to_seq':b,'hour':h,'delta_grade':delta,'n':n}
           for (d,r,a,b,h),c in sorted(transitions.items()) for delta,n in c.items()))
    write_csv(ROOT/'provider_section_speeds.csv',traffic_rows)
    write_json(ROOT/'analysis_summary.json',{'quality':quality,'daily_grade_counts':{d:dict(c) for d,c in daily_grade.items()},
      'route_summary':route_summary,'hour_grade_counts':[{'route':r,'hour':h,'counts':dict(c)} for (r,h),c in sorted(hour_grade.items())],
      'rebuilt_raw_grade_counts_first_known_on_passage':{d:dict(c) for d,c in rebuilt_grade.items()},
      'headway_interval_count':sum(map(len,headways.values())),'travel_interval_count':sum(map(len,travels.values())),
      'method':{'time_zone':'Asia/Seoul','weekdays':['2026-11-09','2026-11-10','2026-11-11'],
        'headway_definition':'distinct observed vehicle stop passages, stopFlag true, GPS within 60m, previous provider observation <=120s; gaps15..3600s',
        'headway_warning':'observed stop passage intervals; missed passages can inflate them; not depot dispatch headway or passenger wait',
        'grades_definition':'saved collector deduplicated vehicle-section passage labels, not passengers; section order is not a measured boarding event',
        'raw_replay_difference':'first observed known label per section; late-known grade and pre-deployment state can differ from packed aggregates',
        'dwell_warning':'stop flag duration is interval-censored and cannot identify boarding/alighting time or passenger counts',
        'no_model_modified':True}})
    print(json.dumps({'route_summary':route_summary,'headway_intervals':sum(map(len,headways.values())),
        'travel_intervals':sum(map(len,travels.values()))},ensure_ascii=False),flush=True)

if __name__=='__main__':analyze()
