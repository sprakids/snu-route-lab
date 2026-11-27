"""Read preserved evidence and write V12 metadata only. No fit or deployment."""
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile
import zlib

HERE=Path(__file__).resolve().parent
REVIEW=HERE.parent
ANALYSIS=REVIEW.parent
KST=timezone(timedelta(hours=9))

def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(name,value):
    (HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda:f.read(4*1024*1024),b''):h.update(data)
    return h.hexdigest()
def evidence(p):
    p=Path(p)
    return {'path':str(p.relative_to(ANALYSIS)).replace('\\','/'),'bytes':p.stat().st_size,'sha256':digest(p)}
def csv_rows(p,encoding='utf-8-sig'):
    with p.open(encoding=encoding,newline='') as f:return list(csv.DictReader(f))
def profile_metadata(p):
    d=load(p)
    return {k:v for k,v in d.items() if k not in ['segments','profiles']}

def build_history():
    board=ANALYSIS/'seoul_boardings_2026-11-10'
    old=ANALYSIS/'historical_validation_2026-11-06'
    td=ANALYSIS/'tdata_calibration_2026-11-07'
    cards=ANALYSIS/'tdata_campus_cards_2026-11-10'
    quality=load(board/'collection_quality.json')
    raw_days=[]
    for p in sorted((td/'collected').glob('*/target_routes.json')):
        rows=load(p);receipt=p.parent/'collection_receipt.json'
        dates=sorted({str(x.get('stdrDe')) for x in rows});routes=Counter(str(x['routeId']) for x in rows)
        value={'folder_date':p.parent.name,'internal_reference_dates':dates,'rows':len(rows),'route_rows':dict(routes),**evidence(p)}
        if receipt.exists():
            doc=load(receipt)
            value['collection_receipt']=evidence(receipt)
            value['receipt_status']={k:v for k,v in doc.items() if k in ['status','started_at','completed_at','end_proved_by_empty_page','date']}
        raw_days.append(value)
    normalized=csv_rows(td/'observations/hourly_observations.csv')
    norm_dates=Counter(x['date'] for x in normalized)
    normalized_nulls={k:sum(x[k]=='' for x in normalized) for k in ['sum_load','average','maximum','runs']}
    monthly=csv_rows(board/'outputs/campus_hourly_monthly_202610_long.csv')
    daily=csv_rows(board/'outputs/campus_daily_20261013_20261109_available.csv')
    duplicate_card_rows=[]
    for x in monthly:
        if x['stop_sequence']=='999':duplicate_card_rows.append({k:x[k] for k in ['month','route_no','stop_id','stop_sequence','hour_kst','monthly_boardings','monthly_alightings']})
    archive=cards/'archives/TAIMS_20261109.zip'
    card_receipt=load(cards/'archives/TAIMS_20261109.zip.receipt.json')
    zip_evidence=evidence(archive)
    assert zip_evidence['sha256']==card_receipt['sha256']
    table_meta=[]
    with zipfile.ZipFile(archive) as z:
        for zi in z.infolist():
            entry={'member':zi.filename,'uncompressed_bytes':zi.file_size,'compressed_bytes':zi.compress_size,'crc32':f'{zi.CRC:08x}'}
            preview=cards/(zi.filename+'.preview')
            if preview.exists():
                raw=preview.read_bytes()
                assert len(raw)==zi.file_size and (zlib.crc32(raw)&0xffffffff)==zi.CRC
                try:text=raw.decode('utf-8-sig');encoding='utf-8-sig'
                except UnicodeDecodeError:text=raw.decode('cp949');encoding='cp949'
                reader=csv.DictReader(io.StringIO(text));rows=list(reader)
                entry.update(fields=reader.fieldnames,row_count=len(rows),reference_dates=dict(Counter(x.get('STDR_DE') for x in rows)),
                             date_check_scope='complete preserved member preview; size and CRC match archive',encoding=encoding,
                             preview=evidence(preview))
            else:
                # Only the date fields and schema are retained; no person/card IDs.
                with z.open(zi) as f:
                    lines=[f.readline() for _ in range(101)]
                text=b''.join(lines).decode('ascii',errors='replace')
                reader=csv.DictReader(io.StringIO(text));rows=list(reader)
                entry.update(fields=reader.fieldnames,sampled_rows=len(rows),
                    reference_dates_in_sample=dict(Counter(x.get('STDR_DE') for x in rows)),
                    ride_calendar_dates_in_sample=dict(Counter((x.get('RIDE_DTM') or '')[:8] for x in rows)),
                    date_check_scope='first100 rows only; whole member dates and campus extract not verified')
            table_meta.append(entry)
    assets=[]
    assets.append({'id':'seoul-monthly-hourly-boardings','provider':'Seoul Open Data OA-12913',
      'source_url':'https://data.seoul.go.kr/dataList/OA-12913/S/1/datasetView.do',
      'source_files':[evidence(old/'sources/boardings_hourly_202610.csv'),evidence(old/'sources/download_receipt.json')],
      'usable_files':[evidence(board/'outputs'/name) for name in ['campus_hourly_monthly_202610.csv','campus_hourly_monthly_202610_long.csv','nearby_8_routes_hourly_monthly_202610.csv']],
      'event_period':{'month':'202610','hour_bins':list(range(24))},
      'unit':'calendar-month aggregate boarding/alighting events per route, stop occurrence and hour; all riders',
      'scope':{'campus_long_rows':len(monthly),'campus_route_stop_occurrences':124,'campus_physical_stops':44,'nearby_8_route_occurrences':37,
               'zones':['campus_core','campus_annex','outside_context'],'boundary':'project stop_scope.json; not legal campus boundary',
               'direction':'stop_sequence/current route ID join, retain repeated occurrences; name is not a key'},
      'availability':{'registered_date':'20261103','provider_exact_publication_time':None,'acquisition_receipt':'historical_validation_2026-11-06/sources/download_receipt.json'},
      'direct_demand_input':False,'supported_use':['hourly boarding/alighting allocation prior','post-hoc comparison using matched route-stop-hour month aggregation'],
      'not_identified':['date-by-hour events','weekday-by-hour observed counts','queue arrivals','unique students','waiting time','denied boardings'],
      'cautions':['Monthly totals mix weekdays/weekends/holidays; do not divide into exact dates as observed truth.',
                  'Boardings are served demand after capacity constraints, not offered arrivals.',
                  '5528 stop_sequence999 is an unmatched anomalous occurrence; preserve source but exclude from main calibration.',
                  'A full October aggregate was not available before its publication; retrospectively using it in an October forecast is leakage.']})
    assets.append({'id':'seoul-daily-boardings','provider':'Seoul Open Data OA-12912',
      'source_url':'https://data.seoul.go.kr/dataList/OA-12912/S/1/datasetView.do',
      'source_files':[evidence(p) for p in sorted((board/'sources').glob('daily_route_*.csv'))]+[evidence(board/'sources/daily_all_routes_202610.csv'),evidence(board/'sources/daily_all_routes_202610.receipt.json')],
      'usable_files':[evidence(board/'outputs'/name) for name in ['campus_daily_20261013_20261109_available.csv','nearby_8_routes_daily_20261013_20261109_available.csv']],
      'event_period':{'requested_start':quality['requested_start'],'requested_end':quality['requested_end'],
                      'available_dates':quality['available_dates'],'missing_dates':quality['missing_dates']},
      'unit':'calendar-date boarding/alighting event totals per route and stop occurrence, all24 hours and all riders',
      'scope':{'campus_rows':len(daily),'campus_physical_stops':44,'nearby_rows':quality['daily']['nearby_8_route_rows'],
               'direction':'mapped stop_sequence retains direction/occurrence; anomalous999 excluded from main analysis'},
      'availability':{'project_collection_time':quality.get('collected_at'),'provider_exact_publication_time':None,
                      'field_warning':'등록일자 is distinct from 사용일자; neither identifies actual intraday service availability'},
      'direct_demand_input':False,'supported_use':['daily/weekday total reference','day-scale allocation constraint with separate student/background assumptions'],
      'not_identified':['hour/minute counts','initial onboard load','queue arrival time','individual trip OD','waiting time'],
      'cautions':['Missing10/27 and11/7..9 are not zeros.','Combining with monthly hourly shares creates an estimated date-hour table, not measured date-hour events.',
                  'Daily versus monthly overlapping totals share the same upstream card source and are not independent validation.']})
    assets.append({'id':'tdata-hourly-segment-sums-raw','provider':'T-data API1025 TaimsTpssA18RouteSection/1.0',
      'source_url':'https://t-data.seoul.go.kr/dataprovide/trafficdataviewopenapi.do?data_id=1025',
      'source_files':raw_days,'event_period':{'available_dates':[x['folder_date'] for x in raw_days],'date_count':len(raw_days)},
      'unit':'hourly segment sum load over passing vehicles; published hour attribution not independently confirmed',
      'scope':{'routes':['5511','5513','5516','관악02-1','관악02-2'],'segments_per_date':259,'hours':list(range(24)),
               'directions':'both, preserved by(routeId,staSn,fromStaId,toStaId)'},
      'availability':{'provider_exact_publication_time':None,'project_acquisition':'per-date collection receipts; not the event date'},
      'direct_demand_input':False,'supported_use':['historical corridor demand-pattern prior','matched hourly onboard-sum observation operator'],
      'not_identified':['per-vehicle occupancy','available seats','boarding/alighting OD','queue length','individual waiting time'],
      'cautions':['259 links repeated across hours/dates are correlated; section totals count a rider across multiple sections.',
                  'Raw preservation covers26 dates; the original normalized calibration CSV covers10 dates only. Do not silently reuse its date range for all raw data.',
                  'Card daily10/27 is absent in OA12912 but segment10/27 exists in API1025: they are different source grains, not a contradiction.']})
    assets.append({'id':'tdata-normalized-calibration','source_files':[evidence(td/'observations/hourly_observations.csv'),evidence(td/'observations/current_links.csv'),evidence(td/'observations/quality_audit.json'),evidence(td/'analysis_plan.json')],
      'event_period':{'dates':sorted(norm_dates),'rows_per_date':dict(norm_dates)},'unit':'same hourly segment sum load, normalized and matched to route occurrences',
      'rows':len(normalized),'null_counts':normalized_nulls,
      'scope':{'campus_origin_rule':'provisional bounding rectangle37.444..37.468,126.944..126.962; not official boundary','primary_hours':[12,22]},
      'availability':{'transformation_date':'2026-11-07','provider_exact_publication_time':None},
      'direct_demand_input':False,'supported_use':['existing source-aligned aggregate comparison','recompute in a new candidate with preserved keys'],
      'cautions':['average/maximum/runs are all missing in this10-date normalized table; do not divide sum_load by an invented run count.',
                  '10/26..30 were already used in exploratory evaluation; not fresh holdout data.']})
    ext=ANALYSIS/'route_expansion_2026-11-07'
    assets.append({'id':'tdata-extra-three-routes','source_files':[evidence(ext/'cached_history_new_routes.json'),evidence(ext/'history_extension_verification.json'),evidence(ext/'independent_history_verification.json')],
      'event_period':{'dates':load(ANALYSIS/'app/data/weekday_history_extension.json')['history_dates']},
      'unit':'hourly segment sum load, three additional routes extracted from preserved citywide pages',
      'scope':{'routes':['5515','5528','6515'],'directions':'retain route and exact ordered link endpoints'},
      'availability':{'project_extraction_date':'2026-11-07','provider_exact_publication_time':None},
      'direct_demand_input':False,'supported_use':['additional-route background pattern','matched onboard-sum comparison'],
      'cautions':['No new API request is needed; these are cached observations, not independent validation of the same API source.']})
    for name in ['weekday_history.json','weekday_history_extension.json']:
        p=ANALYSIS/'app/data'/name
        assets.append({'id':name.removesuffix('.json').replace('_','-'),'source_files':[evidence(p)],
           'metadata':profile_metadata(p),'unit':'model-estimated weekday hourly segment sum load',
           'availability':{'model_build_date':'2026-11-07','exact_build_timestamp':None},
           'direct_demand_input':False,'supported_use':['existing shrunken weekday prior'],
           'cautions':['Derived prediction, not new observed passengers or occupancy. Do not count it as another independent source alongside its training data.']})
    assets.append({'id':'tdata-card-raw-archive','provider':'T-data TAIMS20006 public files',
      'source_files':[zip_evidence,evidence(cards/'archives/TAIMS_20261109.zip.receipt.json'),evidence(cards/'catalogue_manifest_v2.json')],
      'event_period':{'file_label_date':'20261109','internal_date_evidence':table_meta,
                      'requested_event_range':{'start':'20261013','end':'20261109'},
                      'fully_downloaded_citywide_archives':1,'requested_range_fully_acquired':False},
      'unit':'reference tables plus transaction/leg records; not yet an aggregate campus demand input',
      'scope':{'citywide_archive_present':True,'campus_extract_completed':False,'all_trip_member_rows_scanned':False},
      'availability':{'download_completed_at':card_receipt['completed_at'],'provider_exact_publication_time':None},
      'direct_demand_input':False,'supported_use':['possible future privacy-preserving campus boarding/alighting/travel aggregation after schema/date validation'],
      'cautions':['Filename11/9 is not event date. Whole reference members show11/5; transaction sampling is explicitly partial.',
                  'Catalogue inspection of23 reference tables is not23 downloaded daily trip datasets.',
                  'Do not publish individual card identifiers, exact linked person trips or unaggregated records.',
                  'No new download or full1.8GB transaction-member scan was done for this inventory.']})
    preserve=[board/'collection_quality.json',board/'verification.json',td/'observations/hourly_observations.csv',
              ANALYSIS/'app/data/weekday_history.json',ANALYSIS/'app/data/weekday_history_extension.json',
              ANALYSIS/'collector/worker.mjs']
    return {'schema':'v12_historical_data_inventory_v1','created_at':datetime.now(KST).isoformat(),
       'mode':'metadata-only read of preserved originals; no new historical downloads, model fits, source edits or deployments',
       'datasets':assets,'source_preservation_checks':[evidence(p) for p in preserve],
       'time_semantics':{'source_event_time':'boarding service date/month or provider bus dataTm, as applicable',
          'detection_time':'city-bus first confirmed at-stop provider observation, not exact arrival/departure',
          'captured_time':'HTTP acquisition/captured_at; not necessarily source event time',
          'available_time':'publication/receipt time when known; missing publication timestamps remain unknown',
          'dependence':'same rider across links, same vehicle across stops, same upstream source across extracts and profiles are not independent observations'},
       'global_boundary':'No aggregate sum or ordinal grade is converted into individual occupancy, offered arrivals, available seats or exact passenger waits.'}

def build_full_flags():
    cells=defaultdict(lambda:Counter());totals=defaultdict(Counter);reconciliation=[]
    for path in sorted((REVIEW/'raw').glob('*.gz')):
        day=path.name[:10];progress={}
        with gzip.open(path,'rt',encoding='utf-8') as stream:
            for line in stream:
                record=json.loads(line)
                for v in record.get('vehicles',[]):
                    r=v.get('route_id');vid=v.get('id');at=v.get('provided_at');seq=v.get('section_order')
                    if not r or not vid or not at or not str(seq).isdigit() or int(seq)<1:continue
                    if datetime.fromtimestamp(at,KST).date().isoformat()!=day:continue
                    seq=int(seq);pk=(r,vid);p=progress.get(pk)
                    if p and at<=p['at']:continue
                    fresh=not p or seq!=p['seq'] or seq<p['seq'] or at-p['at']>1800
                    recorded=False if fresh else p['availability_recorded']
                    if fresh:totals[(day,r)]['vehicle_section_passages']+=1
                    if not recorded and v.get('full_known') is True:
                        d=datetime.fromtimestamp(at,KST);grade=str(v.get('crowd_code','0'));grade=grade if grade in ['3','4','5','6'] else 'unknown'
                        c=cells[(day,r,seq,d.hour*4+d.minute//15,grade)];c['known']+=1;c['full']+=v.get('full') is True
                        totals[(day,r)]['known']+=1;totals[(day,r)]['full']+=v.get('full') is True;recorded=True
                    progress[pk]={'seq':seq,'at':at,'availability_recorded':recorded}
        official=load(REVIEW/'recording'/(day+'.json'))
        for r in official['routes']:
            got=totals[(day,r['route'])]
            reconciliation.append({'day':day,'route':r['route'],'reconstructed_known':got['known'],'stored_known':r['known_full_flag_observations'],
              'reconstructed_full':got['full'],'stored_full':r['full_flag_observations'],
              'match':got['known']==r['known_full_flag_observations'] and got['full']==r['full_flag_observations']})
    rows=[{'day':d,'route':r,'section':s,'slot_15min':slot,'api_grade':g,'known_full_flag_passages':c['known'],'full_true_passages':c['full']}
          for (d,r,s,slot,g),c in sorted(cells.items())]
    with (HERE/'full_flags_by_day_route_section_slot.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    result={'schema':'v12_full_flag_availability_v1','source':'preserved raw city-bus archives only',
      'deduplication':'at most first known full flag per same vehicle inferred passage; repeated provider timestamps skipped; new trip on decreasing section or gap>1800s',
      'totals':[{'day':d,'route':r,**c} for (d,r),c in sorted(totals.items())],
      'reconciliation':reconciliation,'all_stable_detector_day_counts_match':all(x['match'] for x in reconciliation if x['day'] in ['2026-11-10','2026-11-11']),
      'grades':{'raw_api_crowd_code':{'0':'unknown, never empty','3':'spare','4':'normal','5':'congested','6':'very_congested'},
        'deduplicated_grade_passages_csv_grade':{'0':'API3 spare','1':'API4 normal','2':'API5 congested','3':'API6 very_congested'},
        'csv_mapping_rule':'normalized_grade=API_grade-3 only when API_grade is3,4,5,6; API0 is excluded, not normalized0'},
      'cautions':['Before full_known was added, full=false cannot establish a known not-full observation.',
                   'full_known=true/full=false means provider reported not-full; it is not an exact remaining capacity count.',
                   'full=true is a vehicle state, not observed denied boarding, queue length or an exact passenger count.',
                   'Do not treat full flags repeated across sections or the same vehicle as independent person samples.',
                   'No shuttle occupancy flag is present; missing town-bus congestion grades remain missing even if a full flag exists.']}
    assert result['all_stable_detector_day_counts_match']
    save('full_flag_availability.json',result)
    return result

def build_holdout():
    sys.path.insert(0,str(REVIEW));from fetch_saved import credentials,fetch
    now=datetime.now(KST);day=now.date().isoformat()
    # Metadata only: do not export/read new-day outcome labels.
    recording=json.loads(fetch(credentials(),'/recording?day='+day))
    save('current_day_recording_metadata.json',{'checked_at':now.isoformat(),'endpoint':'authenticated saved /recording', 'response':recording})
    last_inspected='2026-11-11'
    value={'schema':'v12_followup_holdout_rule_v1','declared_at':now.isoformat(),'last_inspected_completed_live_date':last_inspected,
      'new_completed_date_available_at_check':False,'reason':'KST11/12 collection day is not complete; saved recording currently has no routes',
      'current_day':day,'current_day_recording_route_count':len(recording.get('routes',[])),
      'first_candidate_date':'2026-11-12','earliest_review_after':'2026-11-13T00:00:00+09:00',
      'rules':['No alarm, scheduled job, collector control or automatic download was created.',
        'Freeze V12 code, fitted parameters, inputs, route mappings, support thresholds and error metrics before opening the held-out day labels.',
        'Only a completed KST service day after11/11 may qualify; evaluate route/time coverage and documented collector failures before examining prediction errors.',
        'If11/12 is incomplete or otherwise rejected for predeclared source quality reasons, record the reason and use the first subsequent completed qualifying day; never select a day by model score.',
        '11/10 remains the existing segment fit date;11/11 is already explored date-split post-hoc evaluation, not pristine holdout.',
        'After a held-out result is examined, do not tune to it and reuse it as untouched validation. Reserve a later date for the next iteration.',
        'Seoul bus labels do not provide shuttle queue or per-person waiting-time truth; those outcomes remain separately NOT_EVALUABLE.']}
    if now.date().isoformat()!='2026-11-12' or recording.get('routes'):
        value['reason']='Current-day metadata only; date still must be completed before qualification. No raw outcome labels were read.'
    save('future_holdout_rule.json',value)
    return value

def main():
    inventory=build_history();save('inventory.json',inventory)
    flags=build_full_flags();holdout=build_holdout()
    for entry in inventory['source_preservation_checks']:
        assert digest(ANALYSIS/entry['path'])==entry['sha256']
    save('verification.json',{'verified_at':datetime.now(KST).isoformat(),'source_preservation_hashes_match':True,
       'historical_dataset_count':len(inventory['datasets']),'stable_full_flags_reconcile':flags['all_stable_detector_day_counts_match'],
       'new_outcome_raw_read':False,'new_historical_network_downloads':0,'model_or_collector_changes':False,
       'outputs':[evidence(p) for p in HERE.glob('*.json') if p.name!='verification.json']})
    print(json.dumps({'datasets':len(inventory['datasets']),'tdata_original_dates':len(inventory['datasets'][2]['source_files']),
      'full_flags_stable_days_match':flags['all_stable_detector_day_counts_match'],'holdout_candidate':holdout['first_candidate_date']},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
