"""Scoped descriptive candidates and provenance, for separate-model review only."""
from collections import defaultdict, Counter
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
from analyze_saved import ROOT, STOPS, STOP, NAMES, summary, stamp, write_json, write_csv

CALIBRATION_DAYS=['2026-11-10','2026-11-11']
DESCRIPTIVE_DAYS=['2026-11-09',*CALIBRATION_DAYS]
SELECTED_STOPS={'100100250':18,'100100251':8,'100100252':7,'100100253':15,
                '100100263':30,'100100521':70,'120900011':29,'120900012':24}
SELECTED_LEGS={'100100250':(18,25),'100100251':(8,13),'100100252':(7,11),
              '100100253':(15,21),'100100263':(30,34),'100100521':(70,74),
              '120900011':(29,39),'120900012':(24,34)}
OUTBOUND_SECTIONS={'100100250':set(range(12,22)),'100100251':set(range(1,10)),
 '100100252':{7},'100100253':set(range(12,18)),'100100263':{30},'100100521':{70}}
PAIRS={'100100250':[(15,18),(18,20),(20,25)],'100100251':[(1,8),(8,9),(9,13)],
 '100100253':[(12,15),(15,17),(17,21)],'100100252':[(7,11)],'100100263':[(30,34)],'100100521':[(70,74)]}

def grade_summary(c):
    n=sum(c.values())
    return {'n':n,'counts':dict(c),'congested':c['5']+c['6'],
            'congested_fraction':(c['5']+c['6'])/n if n else None,
            'mean_grade':sum((int(g)-3)*v for g,v in c.items())/n if n else None}

def main():
    data=json.loads((ROOT/'observed_intervals.json').read_text(encoding='utf-8'))
    manifest=json.loads((ROOT/'download_manifest.json').read_text(encoding='utf-8'))
    hw=[];rides=[];adjacent=[];full_h=[]
    for r,s in SELECTED_STOPS.items():
        group=[x for x in data['headways'] if x['day'] in CALIBRATION_DAYS and x['route']==r and x['seq']==s and x['hour']==17]
        vals=[v for x in group for v in x['seconds']]
        hw.append({'route':r,'name':NAMES[r],'stop':STOP[(r,s)]['name'],'seq':s,'ars':STOP[(r,s)].get('ars'),
                   'direction':STOP[(r,s)].get('direction'),'hour':17,'dates':sorted({x['day'] for x in group}),
                   'per_day':{d:summary([v for x in group if x['day']==d for v in x['seconds']],headway=True) for d in CALIBRATION_DAYS},
                   **summary(vals,headway=True)})
    for r,(a,b) in SELECTED_LEGS.items():
        group=[x for x in data['travel'] if x['day'] in CALIBRATION_DAYS and x['route']==r and x['from_seq']==a and x['to_seq']==b and x['hour']==17]
        rides.append({'route':r,'name':NAMES[r],'from_seq':a,'to_seq':b,'from_stop':STOP[(r,a)]['name'],'to_stop':STOP[(r,b)]['name'],
          'hour':17,'dates':sorted({x['day'] for x in group}),**summary([v for x in group for v in x['seconds']])})
    for x in data['travel']:
        if x['day'] in CALIBRATION_DAYS and x['to_seq']==x['from_seq']+1:
            adjacent.append({**x,'from_stop':STOP.get((x['route'],x['from_seq']),{}).get('name'),
             'to_stop':STOP.get((x['route'],x['to_seq']),{}).get('name'),**summary(x['seconds'])})
    for x in data['headways']:
        if x['day'] in CALIBRATION_DAYS:full_h.append({**x,'stop':STOP.get((x['route'],x['seq']),{}).get('name'),**summary(x['seconds'],headway=True)})
    campus=defaultdict(Counter);cells=defaultdict(Counter);hours=defaultdict(Counter)
    for path in sorted((ROOT/'aggregates').glob('*.json')):
        if path.stem not in DESCRIPTIVE_DAYS:continue
        for x in json.loads(path.read_text(encoding='utf-8'))['rows']:
            r=x['route'];seq=int(x['section']);hour=int(x['slot'])//4
            if seq in OUTBOUND_SECTIONS.get(r,set()):
                period='15:00-19:00' if 15<=hour<19 else 'other_collection_hours'
                campus[(r,period)][x['grade']]+=x['n']
                if period=='15:00-19:00':cells[(r,seq)][x['grade']]+=x['n']
                hours[(r,hour)][x['grade']]+=x['n']
    congestion=[{'route':r,'name':NAMES[r],'period':p,**grade_summary(c)} for (r,p),c in sorted(campus.items())]
    campus_cells=[{'route':r,'name':NAMES[r],'seq':s,'stop':STOP[(r,s)]['name'],
                   'direction':STOP[(r,s)].get('direction'),**grade_summary(c)} for (r,s),c in sorted(cells.items())]
    # Paired observations of the same vehicle and inferred trip; this measures
    # ordinal changes across a corridor, not boarding/alighting passenger counts.
    vehicle=defaultdict(dict)
    with (ROOT/'deduplicated_grade_passages.csv').open(encoding='utf-8-sig') as f:
        for x in csv.DictReader(f):
            if x['day'] not in DESCRIPTIVE_DAYS:continue
            key=(x['day'],x['route'],x['vehicle'],int(x['trip']));s=int(x['seq'])
            vehicle[key].setdefault(s,{'at':float(x['at']),'grade':int(x['grade'])})
    paired=[]
    for r,pairs in PAIRS.items():
        for a,b in pairs:
            results=[];days=Counter();before=[];after=[]
            for (d,rid,vid,trip),items in vehicle.items():
                if rid!=r or a not in items or b not in items:continue
                pa,pb=items[a],items[b]
                if not(15<=stamp(pa['at']).hour<19 and 0<pb['at']-pa['at']<=1800):continue
                results.append(pb['grade']-pa['grade']);days[d]+=1;before.append(pa['grade']);after.append(pb['grade'])
            n=len(results)
            paired.append({'route':r,'name':NAMES[r],'from_seq':a,'to_seq':b,'from_stop':STOP[(r,a)]['name'],
              'to_stop':STOP[(r,b)]['name'],'n':n,'per_day':dict(days),
              'rise':sum(x>0 for x in results),'same':sum(x==0 for x in results),'fall':sum(x<0 for x in results),
              'mean_delta_grade':sum(results)/n if n else None,
              'congested_before':sum(x>=2 for x in before),'congested_after':sum(x>=2 for x in after)})
    record_index=json.loads((ROOT/'recording_index.json').read_text(encoding='utf-8'))
    summary_json=json.loads((ROOT/'analysis_summary.json').read_text(encoding='utf-8'))
    reconciled=[]
    for d in CALIBRATION_DAYS:
        official=next(x for x in record_index if x['day']==d)
        for rr in official['routes']:
            r=rr['route'];replayed=sum(len(x['seconds']) for x in data['headways'] if x['day']==d and x['route']==r)
            reconciled.append({'day':d,'route':r,'recorded_headway_n':rr['observed_stop_headways'],'replay_n':replayed,
                               'match':rr['observed_stop_headways']==replayed})
    assert all(x['match'] for x in reconciled),'stop passage reconstruction disagrees with saved summary'
    protocol={
      'schema':'saved_observation_calibration_review_v1','generated_at':datetime.now().isoformat(),
      'source':{'archive_manifest':'download_manifest.json','source_sha256':{x['day']:x.get('sha256') for x in manifest['days']},
       'provider_calls_triggered_by_analysis':0,'source_contract_url':'https://www.data.go.kr/data/15000332/openapi.do'},
      'scope':{'descriptive_dates':DESCRIPTIVE_DAYS,'preferred_current_detector_dates':CALIBRATION_DAYS,
       'why_not_1109_for_calibration':'recording logic changed during the day; replay gives15757 gaps versus stored11547',
       'time_zone':'Asia/Seoul','hours':'provider time; headways keyed by later passage hour, travel by first passage hour',
       'section_order':'provider sectOrd matched to stored route stop sequence; not a direct boarding event',
       'congestion_threshold':'known grade5 or6; unknown0 excluded, never treated as empty'},
      'sample_and_error_limits':[
       'A stop passage requires stopFlag=true and distance to recorded stop <=60m, with a previous provider update within120s.',
       'Passage time is first confirmed stop detection. True arrival can precede it by the detection gap; it is not an exact arrival/departure timestamp.',
       'Travel spans two detected stop events and may contain dwell/signal delay; it is not pure moving time and must not receive a second blanket dwell addition.',
       'Repeated provider timestamps are deduplicated; stop intervals and overlapping origin-destination legs are correlated across the same vehicle/trip/day.',
       'Missing a vehicle can inflate a measured headway. Gaps below15s and above3600s are excluded; this truncates the distribution and cannot rule out longer true gaps.',
       'Route dispatch gaps at a depot and observed stop passage gaps are different. Stop-flag runs cannot identify boarded/alighted counts.',
       'Only2 stable detector days exist. One weekday occurrence per date does not identify a weekday effect.',
       '11/11 has already been examined descriptively. A11/10-fit,11/11-evaluation is a date-split backtest, not a pristine untouched holdout.',
       'Observed headway wait E[H^2]/(2E[H]) assumes independent random arrivals and full service eligibility; it is not a student queue wait prediction.',
       'No numeric occupancy, remaining capacity or denied-boarding frequency can be recovered directly from ordinal congestion labels.',
       'No statistical confidence interval or model-accuracy improvement is established by these descriptive results.'
      ],
      'shuttle_gap':{'continuous_archives_available':False,'reason':'BUSIN latest shared cache is overwritten; no shuttle entries in daily raw or route_stats',
        'coordinates':'schematic x/y and stop-area intervals, not GPS; provider timestamp absent',
        'observed_user_report':{'date':'2026-11-10','route':'administration_to_snu_station','queue_join_minute':'15:23',
          'outside_queue_including_observer':67,'individual_queue_wait_seconds':189,'boarding_to_departure_seconds':30,
          'reported_capacity':44,'reported_batch_size':2,'exact_arrival_clock':None},
        'not_identified':['actual headway distribution','true departure timing','batch size prevalence','traffic-dependent completed shuttle trip times']},
      'missing_city_crowd':['120900011','120900012'],
      'application_boundary':'separate prototype only; operating V11, active route model and collector unchanged',
      'reconciliation':reconciled}
    write_json(ROOT/'calibration_contract.json',protocol)
    write_json(ROOT/'calibration_candidates.json',{'headways_17':hw,'rides_17':rides,
      'campus_outbound_congestion':congestion,'campus_peak_section_cells':campus_cells,'paired_grade_changes':paired,
      'campus_hourly':[{'route':r,'name':NAMES[r],'hour':h,**grade_summary(c)} for (r,h),c in sorted(hours.items())]})
    write_json(ROOT/'headway_samples_stable_dates.json',full_h)
    write_json(ROOT/'adjacent_segment_samples_stable_dates.json',adjacent)
    write_csv(ROOT/'headway_candidates_17.csv',[{k:v for k,v in x.items() if k not in ['dates','per_day']} for x in hw])
    write_csv(ROOT/'ride_candidates_17.csv',[{k:v for k,v in x.items() if k!='dates'} for x in rides])
    print(json.dumps({'headways_17':hw,'rides_17':rides,'campus_congestion':congestion,
                     'paired_grade_changes':paired,'reconciled':all(x['match'] for x in reconciled)},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
