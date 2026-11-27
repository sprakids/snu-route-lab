"""Separate heterogeneous tolerance from artificial20min clipping; no runtime fit."""
from pathlib import Path
import argparse,gzip,json,collections,math
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');p.add_argument('--group',default='grid');a=p.parse_args();w=Path(a.candidate).resolve();out=w/(a.group+'-wait-threshold-diagnosis.json');assert not out.exists()
    results=read(w/(a.group+'-validation.json'))['results'];cases=[];days={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}
    for r in results:
        c=r['case'];audit=read(Path(r['source_directory'])/f"audit-{c['scenario']}-{days[c['day']]}.json.gz");patience={};counts=collections.Counter();maximum=None;past=[]
        for t in audit['legs']:
            v=t['student_patience_seconds'];uid=t['id']
            if uid in patience:assert abs(patience[uid]-v)<1e-9
            patience[uid]=v
        for m in audit['wait_audit']:
            seconds=max(0.,m['end']-m['arrival']);weight=m['weight']
            if seconds>1200+1e-7:
                counts['over20_episode_weight']+=weight;counts['over20_'+m['outcome']]+=weight
                counts['over20_enroute_episode_weight']+=weight if m.get('enroute_intercept') else 0.
                label='within_personal_patience' if seconds<=patience[m['id']]+1e-7 else 'past_personal_patience'
                counts[label+'_episode_weight']+=weight
                if label=='past_personal_patience':past.append({'uid':m['id'],'node':m['node'],'arrival':m['arrival'],'end':m['end'],'wait_seconds':seconds,'personal_patience_seconds':patience[m['id']],'outcome':m['outcome'],'weight':weight,'full_passes':m.get('full_passes')})
            if maximum is None or seconds>maximum['seconds']:maximum={'uid':m['id'],'node':m['node'],'seconds':seconds,'personal_patience_seconds':patience[m['id']],'outcome':m['outcome'],'weight':weight}
        cases.append({'case':c,'counts':dict(counts),'maximum_raw_wait_visit':maximum,'past_personal_patience_visits':past,'opportunities':audit['walking_opportunities_report']})
        print('WAIT_THRESHOLDS',c['case'],dict(counts),flush=True)
    out.write_text(json.dumps({'cases':cases,'scope':'Weighted queue visits, not unique students; departure threshold is elapsed plus forecast, not forced exit. The integrated same-stop audit remains controlling for continuous20min totals.','new_outcomes_opened':False},ensure_ascii=False,indent=2),encoding='utf8')
if __name__=='__main__':main()
