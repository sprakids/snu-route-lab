"""Lower-bound diagnostic from existing exported decisions, not new field data."""
from pathlib import Path
import gzip,json,math,hashlib
ROOT=Path(__file__).resolve().parent;ANALYSIS=ROOT.parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
rows=[]
for model in ['261116105704','261116112731','261116120358']:
    f=ANALYSIS/model
    source=read(f/('grid-validation.json' if model=='261116105704' else 'pilot-validation.json'))
    for r in source['results']:
        c=r['case']
        if c['scenario']!='regular' or c['day'] not in ('월','화') or c['case'].startswith('ablation'):continue
        p=Path(r['source_directory'])/f"audit-regular-{'mon' if c['day']=='월' else 'tue'}.json.gz"
        assert hashlib.sha256(p.read_bytes()).hexdigest()==r['audit_sha256']
        a=read(p);cfg=a['prototype_config'];decisions=a['behavior_decisions'];short=[]
        for d in decisions:
            expected=d.get('student_expected_queue_wait_seconds')
            denial=(d.get('student_mode_before')=='city' and d['full_passes']>=cfg['city_denial_trigger'] and d.get('student_predicted_additional_passes',0)>=cfg['city_additional_pass_trigger'])
            old_known=d.get('perceived_old_eta',d.get('old_eta')) is not None
            if old_known and expected is not None and expected<d['student_patience_seconds']-1e-5 and not denial:
                short.append(d)
        rows.append({'model':model,'case':c['case'],'source_sha256':r['audit_sha256'],
            'physical_switch_event_weight':math.fsum(d['weight'] for d in decisions),
            'below_current_pressure_lower_bound_event_weight':math.fsum(d['weight'] for d in short),
            'within_two_minutes_at_this_stop_event_weight':math.fsum(d['weight'] for d in short if d['continuous_wait_seconds']<=120),
            'examples':[{k:d.get(k) for k in ['time','uid','origin','target','weight','continuous_wait_seconds','full_passes','student_patience_seconds','student_expected_queue_wait_seconds','student_predicted_additional_passes','change_count_before']} for d in short[:4]]})
out=ROOT/'unpressured-switch-diagnosis.json';assert not out.exists()
out.write_text(json.dumps({'scope':'Existing completed simulations only. Lower bound with a forecastable incumbent, sub-P expected current wait and no actual-denial trigger. Not observed student counts or proof of causal total-time effect.',
    'cases':rows,'production_writes':False},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps([{k:v for k,v in r.items() if k not in ('examples','source_sha256')} for r in rows],ensure_ascii=False),flush=True)
