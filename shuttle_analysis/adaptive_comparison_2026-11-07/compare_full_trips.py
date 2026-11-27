"""Compare full weighted trip histories, including queue leavers, on fixed cohorts."""
from pathlib import Path
from collections import Counter
import csv,gzip,hashlib,json,math
import numpy as np

ROOT=Path(__file__).resolve().parent
VIEWER=ROOT.parent/'simulation_viewer_2026-11-07'
DAYS={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}
START,END=40800.,83400.
FIELDS=['weight','wait_seconds_sum','shuttle_wait_seconds_sum','city_wait_seconds_sum',
        'walk_seconds_sum','ride_seconds_sum','restricted_elapsed_seconds_sum','completed_weight',
        'complete_class_seconds_sum','complete_depart_seconds_sum','changed_weight','late_arrival_weight','unserved_weight']
F={n:i for i,n in enumerate(FIELDS)}

def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def writecsv(name,rows):
    with (ROOT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    prepared_path=VIEWER/'capacity_model/prepared.json.gz'
    event_path=ROOT.parent/'scenario_comparison_2026-11-07/simulation_outputs/input_snapshot/course_endings_current.json'
    prep=read(prepared_path)
    events=[e for e in read(event_path) if e['included_main'] and e['weekday'] in DAYS and e['end_minute']<=1390]
    allplans=[p for ps in prep['plans'].values() for p in ps]
    assert len(allplans)==len(events)*48==297648
    n=max(p[0] for p in allplans)+1;meta={};weights=np.zeros(n)
    for day,plans in prep['plans'].items():
        for p in plans:
            e=events[(p[0]-1)//48]
            assert e['weekday']==day and str(e['building'])==p[1]
            c=e['end_minute']*60.;assert 60-1e-5<=p[4]-c<=480+1e-5
            meta[p[0]]={'weekday':day,'group':p[2],'building':p[1],'class_end':c,'depart':p[4],
                'initial_shuttle':any(x['rid'].startswith('shuttle') for x in p[6]),
                'section_id':e['section_id'],'source_row':e['source_excel_row']}
            weights[p[0]]=p[3]
    assert set(meta)==set(range(1,n))
    source_files=[prepared_path,event_path];arrays={};checks=[];crosschecks=[]
    for scenario in ['regular','peak']:
        for policy,folder in [('before',VIEWER/'capacity_model/speed_40_65'),('after',VIEWER/'adaptive_model')]:
            result=np.zeros((n,len(FIELDS)))
            for day,did in DAYS.items():
                path=folder/f'audit-{scenario}-{did}.json.gz';source_files.append(path);audit=read(path)
                expected_ids=[p[0] for p in prep['plans'][day]]
                fragment_wait_sum=0.;wait_record_sum=0.
                for s in audit['legs']:
                    uid=s['id'];w=s['weight'];m=meta[uid];legs=s['legs']
                    assert m['weekday']==day
                    wait=shuttle=city=walk=ride=0.
                    for l in legs:
                        duration=l[2]-l[1];assert duration>=-1e-8
                        if l[0]==1:
                            observed=max(0.,min(l[2],END)-min(max(l[1],m['depart']),END))
                            wait+=observed
                            if l[4]>=0:shuttle+=observed
                            else:city+=observed
                        elif l[0]==0:walk+=duration
                        elif l[0] in (2,3):ride+=duration
                    r=result[uid];r[F['weight']]+=w;r[F['wait_seconds_sum']]+=w*wait
                    r[F['shuttle_wait_seconds_sum']]+=w*shuttle;r[F['city_wait_seconds_sum']]+=w*city
                    r[F['walk_seconds_sum']]+=w*walk;r[F['ride_seconds_sum']]+=w*ride
                    elapsed=(min(legs[-1][2],END) if not s['unserved'] else END)-m['class_end']
                    # A class finishing at the very last display instant departs
                    # later; that group is excluded from the primary window.
                    r[F['restricted_elapsed_seconds_sum']]+=w*max(0.,elapsed)
                    if s['unserved']:r[F['unserved_weight']]+=w
                    else:
                        end=legs[-1][2];r[F['completed_weight']]+=w
                        r[F['complete_class_seconds_sum']]+=w*(end-m['class_end'])
                        r[F['complete_depart_seconds_sum']]+=w*(end-m['depart'])
                        if end>END:r[F['late_arrival_weight']]+=w
                        # Independently sum the component durations, including the
                        # unchanged class-end-to-building-exit delay.
                        whole=sum(l[2]-l[1] for l in legs)
                        assert abs(whole-(end-m['depart']))<1e-5
                    if s.get('history'):r[F['changed_weight']]+=w
                    fragment_wait_sum+=w*shuttle
                # A second source representation is used only to validate queue
                # exposure, not to define the trip population or count boardings.
                for a in audit['waits']:
                    wait_record_sum+=a[3]*max(0.,min(a[2],END)-min(a[1],END))
                assert abs(fragment_wait_sum-wait_record_sum)<1e-4,(scenario,policy,day,fragment_wait_sum,wait_record_sum)
                ids=np.array(expected_ids)
                error=float(np.max(np.abs(result[ids,F['weight']]-weights[ids])))
                assert error<1e-6
                checks.append({'scenario':scenario,'policy':policy,'weekday':day,'particle_mass_max_error':error,
                    'shuttle_exposure_difference_weighted_seconds':abs(fragment_wait_sum-wait_record_sum)})
            arrays[scenario,policy]=result
    def aggregate(scenario,ids,**labels):
        ids=np.array(ids,dtype=int);wb=weights[ids].sum()
        b=arrays[scenario,'before'][ids];a=arrays[scenario,'after'][ids]
        complete=(np.abs(b[:,F['completed_weight']]-weights[ids])<1e-7)&(np.abs(a[:,F['completed_weight']]-weights[ids])<1e-7)
        cw=weights[ids][complete].sum()
        row={**labels,'scenario':scenario,'weight':float(wb),'original_particle_count':len(ids),
             'common_complete_weight':float(cw),'common_complete_share_pct':float(cw/wb*100) if wb else None}
        def value(mat,name,denom=wb):return float(mat[:,F[name]].sum()/denom) if denom else None
        for key,mat in [('before',b),('after',a)]:
            for col,raw in [('wait_all_min','wait_seconds_sum'),('shuttle_wait_all_min','shuttle_wait_seconds_sum'),
                            ('city_wait_all_min','city_wait_seconds_sum'),('restricted_total_min','restricted_elapsed_seconds_sum')]:
                v=value(mat,raw);row[f'{col}_{key}']=v/60 if v is not None else None
            for col in ['unserved_weight','changed_weight','late_arrival_weight']:row[f'{col}_{key}']=float(mat[:,F[col]].sum())
            row[f'unserved_share_pct_{key}']=row[f'unserved_weight_{key}']/wb*100 if wb else None
            cm=mat[complete]
            for col,raw in [('total_common_min','complete_class_seconds_sum'),('departure_total_common_min','complete_depart_seconds_sum'),
                            ('wait_common_min','wait_seconds_sum'),('walk_common_min','walk_seconds_sum'),('ride_common_min','ride_seconds_sum')]:
                row[f'{col}_{key}']=float(cm[:,F[raw]].sum()/cw/60) if cw else None
        for col in ['wait_all_min','shuttle_wait_all_min','city_wait_all_min','restricted_total_min',
                    'total_common_min','departure_total_common_min','wait_common_min','walk_common_min','ride_common_min']:
            x,y=row[f'{col}_before'],row[f'{col}_after'];row[f'{col}_saved']=x-y if x is not None and y is not None else None
            row[f'{col}_saved_pct']=(x-y)/x*100 if x is not None and y is not None and x>0 else None
        if cw:
            differences=(a[complete,F['complete_class_seconds_sum']]-b[complete,F['complete_class_seconds_sum']])/weights[ids][complete]
            row['improved_original_particle_weight']=float(weights[ids][complete][differences < -1].sum())
            row['worsened_original_particle_weight']=float(weights[ids][complete][differences > 1].sum())
            row['unchanged_original_particle_weight']=float(weights[ids][complete][np.abs(differences)<=1].sum())
            egress_before=row['total_common_min_before']-row['departure_total_common_min_before']
            egress_after=row['total_common_min_after']-row['departure_total_common_min_after']
            assert abs(egress_before-egress_after)<1e-7
            for key in ['before','after']:
                assert abs(row[f'departure_total_common_min_{key}']-sum(row[f'{c}_common_min_{key}'] for c in ['wait','walk','ride']))<1e-7
        else:
            for k in ['improved_original_particle_weight','worsened_original_particle_weight','unchanged_original_particle_weight']:row[k]=0.
        return row
    hourly=[];daily=[];pooled=[]
    scopes={'snu_all':lambda m:m['group']=='snu',
            'snu_initial_shuttle':lambda m:m['group']=='snu' and m['initial_shuttle'],
            'all_destinations':lambda m:True}
    for origin in ['all','301_302']:
        for scope,predicate in scopes.items():
            eligible=[i for i,m in meta.items() if predicate(m) and (origin=='all' or m['building'] in ('301','302'))
                      and START<=m['class_end']<=END]
            for scenario in ['regular','peak']:
                for day in DAYS:
                    all_day=[i for i in eligible if meta[i]['weekday']==day]
                    for h in range(11,23):
                        ids=[i for i in all_day if h*3600<=meta[i]['class_end']<(h+1)*3600]
                        hourly.append(aggregate(scenario,ids,origin=origin,scope=scope,weekday=day,class_end_hour=h))
                    for period,lo,hi in [('all',START,END+.001),('peak15_19',54000,68400)]:
                        daily.append(aggregate(scenario,[i for i in all_day if lo<=meta[i]['class_end']<hi],
                            origin=origin,scope=scope,weekday=day,period=period))
                for h in range(11,23):
                    ids=[i for i in eligible if h*3600<=meta[i]['class_end']<(h+1)*3600]
                    pooled.append(aggregate(scenario,ids,origin=origin,scope=scope,weekday='월~금',class_end_hour=h))
    # Reconcile day-hour weighted numerators with the daily result independently.
    for row in daily:
        if row['period']!='all':continue
        sub=[r for r in hourly if all(r[k]==row[k] for k in ['origin','scope','weekday','scenario'])]
        assert abs(sum(x['weight'] for x in sub)-row['weight'])<1e-6
        for suffix in ['before','after']:
            if row['weight']:
                rebuilt=sum(x['wait_all_min_'+suffix]*x['weight'] for x in sub if x['weight'])/row['weight']
                assert abs(rebuilt-row['wait_all_min_'+suffix])<1e-8
            if row['common_complete_weight']:
                rebuilt=sum((x['total_common_min_'+suffix] or 0)*x['common_complete_weight'] for x in sub)/row['common_complete_weight']
                assert abs(rebuilt-row['total_common_min_'+suffix])<1e-8
    writecsv('요일_시간대별_전후비교.csv',hourly);writecsv('요일별_전후비교.csv',daily);writecsv('시간대별_월금합산_전후비교.csv',pooled)
    save(ROOT/'reviewed_results.json',{'daily':daily,'hourly':hourly,'pooled':pooled})
    manifest={str(p.relative_to(ROOT.parent)):sha(p) for p in source_files}
    verification={'status':'PASS','cohort':'same original weighted particles, grouped by unchanged class-end time',
        'class_end_mapping_all_particles':len(meta),'class_end_events':len(events),'hourly_rows':len(hourly),'daily_rows':len(daily),
        'source_hashes':manifest,'checks':checks,'primary_window_class_end_seconds':[START,END],
        'wait_definition':'All shuttle/city waiting legs through 23:10, including abandoned queues, divided by original cohort mass; unfinished waits are censored.',
        'total_definition':'Class end to SNU representative destination, among original particles whose whole weighted mass completes in BOTH policies.',
        'restricted_total_definition':'All original flows; min(arrival,23:10)-class end; unfinished flows followed to23:10. Lower-bound elapsed time, not completed travel time.',
        'observed_student_validation':False,'simulation_rerun':False}
    save(ROOT/'verification.json',verification)
    for row in daily:
        if row['origin']=='all' and row['scope']=='snu_all' and row['period']=='all':
            print(json.dumps({k:row[k] for k in ['scenario','weekday','weight','wait_all_min_before','wait_all_min_after',
                'total_common_min_before','total_common_min_after','common_complete_share_pct','unserved_weight_before','changed_weight_after']},ensure_ascii=False))
    print('PASS',len(hourly),'hourly rows',len(daily),'daily rows')

if __name__=='__main__':main()
