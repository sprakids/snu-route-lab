"""Independent20min and personal-threshold diagnostics, including sub20 P exceedance."""
from pathlib import Path
from collections import Counter
import argparse,gzip,hashlib,json,math
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');p.add_argument('--group',default='grid');p.add_argument('--output');a=p.parse_args();w=Path(a.candidate).resolve();out=Path(a.output).resolve() if a.output else w/f'{a.group}-wait-cause-ledger.json';assert not out.exists();cases=[]
    for r in read(w/f'{a.group}-validation.json')['results']:
        c=r['case'];day={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}[c['day']];path=Path(r['source_directory'])/f"audit-{c['scenario']}-{day}.json.gz";d=read(path)
        patience={t['id']:t['student_patience_seconds'] for t in d['legs']};counts=Counter();past=[];maximum=None;errors=[]
        for visit in d['wait_audit']:
            seconds=max(0.,visit['end']-visit['arrival']);weight=visit['weight'];limit=patience[visit['id']]
            if seconds>1200+1e-7:
                counts['over20_episode_weight']+=weight;counts['over20_'+visit['outcome']]+=weight
                counts['over20_within_personal_weight']+=weight if seconds<=limit+1e-7 else 0.
            if seconds>limit+1e-7:
                counts['past_personal_at_any_duration_weight']+=weight
                counts['past_personal_'+('over20' if seconds>1200+1e-7 else 'at_most20')+'_weight']+=weight
                counts['past_personal_'+('gate62' if visit['node']==62 else 'non_gate')+'_weight']+=weight
                past.append({'uid':visit['id'],'node':visit['node'],'arrival':visit['arrival'],'end':visit['end'],'wait_min':seconds/60,
                    'personal_limit_min':limit/60,'weight':weight,'outcome':visit['outcome'],'full_passes_seen':visit.get('full_passes_seen'),
                    'entry_forecast':visit.get('entry_forecast'),'student_flexible':visit.get('student_flexible')})
            if maximum is None or seconds>maximum['seconds']:maximum={'uid':visit['id'],'node':visit['node'],'seconds':seconds,'personal_limit_seconds':limit,'weight':weight,'outcome':visit['outcome']}
            pred=visit.get('entry_forecast')
            if visit['outcome']=='boarded' and pred and pred['first_wait_seconds'] is not None:
                error=visit['end']-pred['issued_at']-pred['first_wait_seconds'];errors.append((error,weight))
        mass=math.fsum(wt for error,wt in errors)
        accuracy={'boarding_only_weight':mass,'signed_mean_seconds':math.fsum(x*wt for x,wt in errors)/mass if mass else None,
            'mean_absolute_seconds':math.fsum(abs(x)*wt for x,wt in errors)/mass if mass else None,
            'actual_over_forecast_by10min_weight':math.fsum(wt for x,wt in errors if x>600),
            'scope':'Only boarding outcomes with an exported entry forecast; switches are censored, not counted as forecast errors. Gate exemption may have no entry forecast.'}
        row={'case':c,'source':str(path),'source_sha256':sha(path),'counts':dict(counts),'maximum_raw_visit':maximum,
            'largest_personal_exceedances':sorted(past,key=lambda x:x['wait_min']-x['personal_limit_min'],reverse=True)[:50],
            'personal_exceedance_rows_total':len(past),'entry_forecast_boarding_diagnostics':accuracy,
            'focus_diagnostics':d['policy_report'].get('focus_diagnostics',[]),'focus_cap':d['policy_report'].get('focus_diagnostic_cap'),
            'canonical_all_recorded_over20_weight':r['extended_diagnostics']['all_recorded_time_over20_episode_weight']}
        cases.append(row);print('WAIT_CAUSES',c['case'],dict(counts),flush=True)
    out.write_text(json.dumps({'cases':cases,'scope':'Weighted queue visits, not unique students. P-exceedances are counted regardless of20min. Canonical continuous-stop episodes remain separately available. All source ledgers retained.','production_writes':False},ensure_ascii=False,indent=2),encoding='utf8')
if __name__=='__main__':main()
