"""Expose building-release delay and full class-end-to-destination burden."""
from pathlib import Path
import argparse,csv,gzip,hashlib,json,math
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def quant(rows):
    total=math.fsum(w for t,w in rows);ordered=sorted(rows)
    def q(frac):
        running=0.
        for t,w in ordered:
            running+=w
            if running>=frac*total:return t
        return ordered[-1][0]
    return {'mean':math.fsum(t*w for t,w in rows)/total,'p50':q(.5),'p90':q(.9),'p95':q(.95),'p99':q(.99),'maximum':ordered[-1][0]}
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();work=Path(a.candidate).resolve()
    target=work/'class-end-journey-comparison.csv';assert not target.exists()
    lineage=read(work/'frozen/class_release_map.json.gz');allrows=[];sources={}
    for model in ('261116010854',work.name):
        base=ANALYSIS/model;v=read(base/'grid-validation.json')
        for r in v['results']:
            case=r['case'];did={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}[case['day']]
            path=Path(r['source_directory'])/f"audit-{case['scenario']}-{did}.json.gz";assert sha(path)==r['audit_sha256']
            sources[str(path)]=sha(path);audit=read(path);waits=[];totals=[];mass=unfinished=0.
            for trip in audit['legs']:
                event=lineage['events'][(trip['parent_id']-1)//48];assert event['weekday']==case['day']
                end=event['class_end_seconds'];lag=(trip['start']-end)/60;assert lag>=0
                mass+=trip['weight'];waits.append((lag,trip['weight']))
                if trip['unserved']:unfinished+=trip['weight']
                else:
                    assert abs(trip['finish_time']-trip['legs'][-1][2])<1e-5
                    totals.append(((trip['finish_time']-end)/60,trip['weight']))
            for metric,values in [('class_end_to_departure_min',waits),('class_end_to_destination_min',totals)]:
                allrows.append({'model':model,'weekday':case['day'],'scenario':case['scenario'],'metric':metric,
                  'scenario_trip_weight':mass,'unserved_trip_weight':unfinished,**quant(values)})
            print('CLASS_END_METRICS',model,case['case'],flush=True)
    assert len(allrows)==40
    with target.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(allrows[0]));w.writeheader();w.writerows(allrows)
    (work/'class-end-metrics-manifest.json').write_text(json.dumps({'report':target.name,'rows':len(allrows),
      'lineage_sha256':sha(work/'frozen/class_release_map.json.gz'),'audits':sources,
      'note':'Finished weighted scenario journeys, not measured student trips; includes synthetic in-building release lag. Cases remain separate.'},ensure_ascii=False,indent=2),encoding='utf8')
if __name__=='__main__':main()
