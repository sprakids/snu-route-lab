"""Separate plotted-window queue peaks from pre-window initialization peaks."""
from pathlib import Path
import argparse,bisect,csv,gzip,hashlib,json
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(validation):
    validation=Path(validation);v=read(validation/'validation.json');lock=read(validation/'experiment_lock.json')
    target=ROOT/'queue_peaks_by_window.json';assert not target.exists()
    names={c['case'] for c in lock['all_weekday_main_cases']}
    nodes=read(validation/'frozen/prepared_capacity44_pair.json.gz')['prepared']['common']['nodes'];rows=[];proof=[]
    for r in v['results']:
        c=r['case']
        if c['case'] not in names:continue
        day={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}[c['day']]
        path=Path(r['source_directory'])/f'{c["scenario"]}-{day}.json.gz';data=read(path)
        for n,timeline in enumerate(data['queue_timeline']):
            times=[x[0] for x in timeline];k=bisect.bisect_right(times,40800)-1
            q0=timeline[k][1] if k>=0 else 0.;subset=[[40800,q0],*[x for x in timeline if 40800<x[0]<=83400]]
            primary=max(subset,key=lambda x:x[1]);alltime=max(timeline,key=lambda x:x[1],default=[None,0.])
            meta=nodes[n]
            rows.append({'case':c['case'],'weekday':c['day'],'scenario':c['scenario'],'node':n,'stop':meta['name'],'ars':meta.get('ars',''),
                         'window_max_queue':primary[1],'window_queue_peak_at':primary[0] if primary[1]>1e-7 else None,
                         'all_recorded_max_queue':alltime[1],'all_recorded_queue_peak_at':alltime[0] if alltime[1]>1e-7 else None})
        proof.append({'case':c['case'],'data':str(path),'data_sha256':sha(path)})
    assert len(rows)==990
    with (ROOT/'queue_peaks_by_window.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
    target.write_text(json.dumps({'status':'READ_ONLY_WINDOW_RECONCILIATION','primary_window':[40800,83400],'rows':rows,'proof':proof,
        'original_validation_max_queue_scope':'all recorded time; source data not overwritten',
        'window_entry_carryover_included':True,'unmeasured_real_queues_not_imputed_as_zero':True},ensure_ascii=False,indent=2),encoding='utf8')
    print('QUEUE_WINDOWS_RECONCILED',len(rows))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--validation',required=True);a=p.parse_args();main(a.validation)
