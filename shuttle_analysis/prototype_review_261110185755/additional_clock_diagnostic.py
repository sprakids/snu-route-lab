"""Preserve the failed gate-reference sensitivity instead of omitting it."""
from pathlib import Path
import hashlib,json,math
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'prototype_followup_261110185755'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    target=ROOT/'additional_clock_diagnostic.json';assert not target.exists()
    source=PARENT/'gate_reference_long_wait_reconstruction.json';details=read(source)
    report=read(PARENT/'runs/gate_reference-combined-regular-mon/attempt_01/independent_analysis.json')
    rows=[]
    for d in details:
        trip=d['trip'];leg=d['long_leg'];a,b=leg[1:3]
        rows.append({'uid':trip['id'],'weight':trip['weight'],'node':leg[4],'stop':d['stop']['name'],'ars':d['stop']['ars'],
                     'arrival_second':a,'leave_second':b,'continuous_wait_min':(b-a)/60,
                     'previous_changes':sum(h[0]<=a for h in trip['history']),
                     'full_passes':max(m['full_passes_seen'] for m in d['wait_audit']),
                     'voluntary_declines':len(d['declines']),'service_events':d['services'],
                     'early_recorded_review':d['reviews'][0] if d['reviews'] else None,
                     'last_recorded_review':d['reviews'][-1] if d['reviews'] else None})
    assert abs(math.fsum(r['weight'] for r in rows)-report['over20_weight'])<1e-7
    target.write_text(json.dumps({'status':'FAIL20_IN_ADDITIONAL_GATE_REFERENCE_CLOCK_SCENARIO',
        'primary_clock_distribution_was_registered_before_these_outcomes':True,
        'maximum_continuous_wait_min':report['maximum_continuous_wait_min'],'over20_weight':report['over20_weight'],
        'rows':rows,'source':str(source),'source_sha256':sha(source),
        'not_change_count_exhaustion':True,'not_a_user_observed20minute_wait':True,
        'not_a_universal20minute_guarantee':True,'no_clipping_or_forced_late_walk':True,
        'interpretation':'One full vehicle missed; later service chosen while continued waiting had lower generalized cost than walking. Model chronology and tastes, not independently verified real behavior.'},ensure_ascii=False,indent=2),encoding='utf8')
    print('ADDITIONAL_CLOCK_FAILURE_PRESERVED',report['maximum_continuous_wait_min'],report['over20_weight'])
if __name__=='__main__':main()
