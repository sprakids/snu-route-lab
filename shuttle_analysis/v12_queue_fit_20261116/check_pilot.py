"""Apply the declared pilot criteria to main conditions, never cherry-pick variants."""
from pathlib import Path
import argparse,csv,json,math
def read(p):return json.loads(p.read_bytes())
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve();out=w/'pilot-decision-v2.json';assert not out.exists()
    v=read(w/'pilot-validation.json');b=read(w/'pilot-behavior-validation.json');base=read(w.parent/'261115160710/grid-validation.json')['results']
    field=list(csv.DictReader((w/'pilot-field-comparison.csv').open(encoding='utf-8-sig')));main=[x for x in v['results'] if not x['case']['case'].startswith('ablation')];assert len(main)==2
    names={r['case']['case'] for r in main};owned=[x for x in field if x['model']==w.name and x['case'] in names];assert len(owned)==4
    err='expected_absolute_distance_to_count_or_interval';old_total=new_total=0.;comparisons=[]
    for x in owned:
        old=next(z for z in field if z['model']=='261115160710' and z['scenario']==x['scenario'] and z['observation_id']==x['observation_id'])
        old_total+=float(old[err]);new_total+=float(x[err]);comparisons.append({'observation':x['observation_id'],'old_mean':float(old['uniform_minute_mean']),'new_mean':float(x['uniform_minute_mean']),'old_error':float(old[err]),'new_error':float(x[err]),'minute':x['reported_minute']})
    gate=next(x for x in comparisons if x['minute']=='17:03')
    old_over=new_over=0.;unserved=0.;means=[]
    for r in main:
        old=next(x for x in base if x['case']['day']==r['case']['day'] and x['case']['scenario']==r['case']['scenario'])
        old_over+=old['extended_diagnostics']['all_recorded_time_over20_episode_weight'];new_over+=r['extended_diagnostics']['all_recorded_time_over20_episode_weight']
        unserved+=r['unserved_trip_weight'];means.append(r['extended_diagnostics']['finished_trip_quantiles']['total_min']['mean']-old['extended_diagnostics']['finished_trip_quantiles']['total_min']['mean'])
    physical=all(r['status']=='PASS_INTERNAL_INVARIANTS' for r in v['results']);behavior=b['status']=='PASS_STUDENT_BEHAVIOR_GATES'
    passed=physical and behavior and unserved<1e-7 and new_total<old_total and gate['new_error']<gate['old_error']
    d={'status':'PROCEED_MAIN_GRID' if passed else 'PILOT_NOT_ACCEPTED','physical':physical,'behavior':behavior,'main_cases':2,'registered_diagnostics':2,
       'reused_four_observation_error_sum_before':old_total,'reused_four_observation_error_sum_after':new_total,'relative_error_reduction':1-new_total/old_total,
       'gate_comparison':gate,'all_observations':comparisons,'over20_weight_before':old_over,'over20_weight_after':new_over,'relative_over20_reduction':1-new_over/old_over,
       'mean_journey_delta_minutes':means,'unserved_weight':unserved,'not_independent_field_validation':True,'production_writes':False}
    assert abs(d['reused_four_observation_error_sum_after']-math.fsum(x['new_error'] for x in comparisons))<1e-7
    d['supersedes_output_labels_only']='v1 used duplicate after keys; criterion calculations were correct. Original artifact and log retained; no model was repeated.'
    out.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8');print('PILOT_DECISION',d,flush=True)
    assert passed
if __name__=='__main__':main()
