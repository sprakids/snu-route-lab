"""Reconstruct continuous same-stop waits from saved final weighted v7 paths only."""
import csv,gc,gzip,hashlib,json,math
from collections import defaultdict
from pathlib import Path

WORK=Path(__file__).resolve().parent
SOURCE=WORK.parent/'simulation_viewer_2026-11-07/gate_access_calibration_2026-11-09/candidates/alpha_075'
DAYS={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}
START=680*60;END=1390*60;THRESHOLD=1200.;EPS=1e-6
def read(p):return json.loads(gzip.decompress(p.read_bytes()))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def writecsv(name,rows):
    with (WORK/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def blocks(legs):
    current=None
    for leg in legs:
        if leg[0]!=1:
            if current is not None:yield current;current=None
            continue
        node=leg[4];start=leg[1];end=min(END,leg[2])
        if current is not None and current[0]==node and abs(current[2]-start)<EPS:
            current[2]=end;current[3]+=1
        else:
            if current is not None:yield current
            current=[node,start,end,1]
    if current is not None:yield current

def newstat():return {'incident_weight':0.,'affected_trip_weight':0.,'final_packet_block_rows':0,
    'maximum_continuous_wait_seconds':0.,'excess_over_20_person_minutes':0.,'same_stop_merged_long_incident_weight':0.}
def main():
    WORK.mkdir(exist_ok=True);bundle=read(SOURCE/'prepared.json.gz');nodes=bundle['prepared']['common']['nodes']
    sources={str(SOURCE/'prepared.json.gz'):sha(SOURCE/'prepared.json.gz')}
    summaries=[];stoprows=[];verification=[]
    for day,code in DAYS.items():
        source=SOURCE/f'audit-peak-{code}.json.gz';sources[str(source)]=sha(source);a=read(source)
        aggregate={s:newstat() for s in ('all_saved','display_window_1120_2310')}
        bystop=defaultdict(newstat);visits=defaultdict(set);allvisits=defaultdict(set)
        raw_weight=0.;weighted_final=0.
        for row in a['legs']:
            uid=row['id'];w=row['weight'];weighted_final+=w
            raw_weight+=sum(w for leg in row['legs'] if leg[0]==1)
            affected=set();affected_stops=set()
            for node,start,end,segments in blocks(row['legs']):
                duration=end-start
                if duration<=THRESHOLD+EPS:continue
                for scope,left in [('all_saved',-math.inf),('display_window_1120_2310',START)]:
                    excess=max(0.,end-max(start+THRESHOLD,left))
                    if excess<=EPS:continue
                    stat=aggregate[scope];local=bystop[(scope,node)]
                    for target in (stat,local):
                        target['incident_weight']+=w;target['final_packet_block_rows']+=1
                        target['maximum_continuous_wait_seconds']=max(target['maximum_continuous_wait_seconds'],duration)
                        target['excess_over_20_person_minutes']+=w*excess/60
                        if segments>1:target['same_stop_merged_long_incident_weight']+=w
                    key=(uid,node,round(start,6));visits[scope,node].add(key);allvisits[scope].add(key)
                    affected.add(scope);affected_stops.add((scope,node))
            for scope in affected:aggregate[scope]['affected_trip_weight']+=w
            for key in affected_stops:bystop[key]['affected_trip_weight']+=w
        expected=math.fsum(p[3] for p in bundle['prepared']['plans'][day])
        assert abs(weighted_final-expected)<1e-5
        assert abs(raw_weight-math.fsum(r['weight'] for r in a['wait_audit']))<1e-5
        for scope,stat in aggregate.items():
            stat.update(weekday=day,scope=scope,original_particle_visits=len(allvisits[scope]),
                input_trip_weight=expected,affected_trip_share=stat['affected_trip_weight']/expected)
            summaries.append(stat)
            assert abs(sum(v['incident_weight'] for (s,n),v in bystop.items() if s==scope)-stat['incident_weight'])<1e-5
        for (scope,node),stat in bystop.items():
            meta=nodes[node]
            stoprows.append({'weekday':day,'scope':scope,'node':node,'name':meta['name'],
                'ars':meta.get('ars'),'stop_id':meta.get('stop_id'),'route':meta.get('route'),
                **stat,'original_particle_visits':len(visits[scope,node])})
        verification.append({'weekday':day,'final_weight':weighted_final,'input_weight':expected,
            'raw_segment_mass':raw_weight,'audit_segment_mass':math.fsum(r['weight'] for r in a['wait_audit'])})
        print(code,json.dumps(aggregate,ensure_ascii=False),flush=True)
        del a;gc.collect()
    assert all(sha(Path(p))==h for p,h in sources.items())
    writecsv('weekday_summary.csv',summaries);writecsv('by_stop_weekday.csv',stoprows)
    output={'summary':summaries,'sources':sources,'reconciliations':verification,
       'definition':{'continuous':'adjacent same-node wait legs merge; any walk/ride breaks continuity',
         'threshold_seconds':1200,'comparison':'strictly greater, tolerance 1e-6 seconds',
         'unit':'weighted trip-event wait incidents; affected trips are not unique students',
         'original_particle_visits':'distinct synthetic uid/node/entry, not people',
         'final_packet_block_rows':'raw final split block rows, not independent people or visits',
         'window':'display scope counts blocks whose over-20-min exposure intersects 11:20-23:10; duration itself is not reset at 11:20',
         'censoring':'unserved at 23:10 clipped, excludes one-second display sentinel'},
       'checks':{'final_and_initial_mass_match':True,'raw_wait_segment_mass_matches':True,'node_incidents_reconcile':True,
          'source_hashes_unchanged':True,'new_simulation_runs':0,'source_model_edits':0,'deployments':0}}
    (WORK/'analysis.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8')
    print('PASS all saved weekdays, mass and censoring checks; no simulator imports or new runs')

if __name__=='__main__':main()
