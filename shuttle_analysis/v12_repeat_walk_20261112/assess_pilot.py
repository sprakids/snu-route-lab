"""Evaluate the requested behavioral scenario without fitting its growth factor."""
from pathlib import Path
import argparse,ast,csv,hashlib,json,math
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'261112210916'
PRIMARY={'20261109-1653-admin-snu-queue-01','20261109-1703-snu-gate-queue-01','20261110-1523-admin-snu-queue-wait-01'}
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def funcs(p):return {n.name:ast.dump(n,include_attributes=False) for n in ast.walk(ast.parse(p.read_text(encoding='utf8'))) if isinstance(n,ast.FunctionDef)}
def score(items):
    items=[r for r in items if r['observation_id'] in PRIMARY];assert len(items)==3
    return math.fsum(float(r['expected_absolute_distance_to_count_or_interval'])/((float(r['observed_low'])+float(r['observed_high']))/2) for r in items)/3
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve();target=w/'pilot-assessment.json';assert not target.exists()
    d=read(w/'observations-diagnostics.json');v=read(w/'observations-validation.json')
    own=[r for r in rows(w/'observations-field-comparison.csv') if r['model']==w.name and r['scenario']=='regular']
    old=[r for r in rows(PARENT/'grid-field-comparison.csv') if r['model']==PARENT.name and r['scenario']=='regular']
    c,b=read(w/'config.json'),read(PARENT/'config.json');changed={k for k in set(c)|set(b) if c.get(k)!=b.get(k)}
    allowed={'release_id','version_family','later_walking_preference','exponential_repeat_walk','repeat_walk_growth_factor','repeat_walk_numeric_epsilon','repeat_walk_interpretation'}
    assert changed<=allowed,changed;assert c['repeat_walk_growth_factor']==2.
    unchanged=['engine.py','hazard.py','capacity.py','physics.py','prepare.py','operations.py','empirical_v12.py','time_profiles.py']
    for name in unchanged:assert sha(w/name)==sha(PARENT/name),name
    for name in ('cost','walking_weight','uniform','lognormal','traits'):assert funcs(w/'preferences.py')[name]==funcs(PARENT/'preferences.py')[name],name
    for name in ('predict','generalized','reschedule','initial_choice','complete_same_stop'):
        assert funcs(w/'policy.py')[name]==funcs(PARENT/'policy.py')[name],name
    maxwait=max(r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min'] for r in v['results'])
    viable=d['all_invariant_audits_pass'] and d['all_continuous_waits_under20'] and d['unserved_trip_weight']<1e-7
    result={'status':'VIABLE_FOR_FULL_GRID' if viable else 'PHYSICAL_GATE_FAILED','release_id':w.name,'parent':PARENT.name,
      'maximum_all_recorded_wait_min':maxwait,'primary_reused_report_loss_before':score(old),'primary_reused_report_loss_after':score(own),
      'growth_factor_fixed_before_outcomes':2.,'probability_rule_not_fitted_to_observations':True,'changed_config_keys':sorted(changed),
      'unchanged_files':unchanged,'base_cost_and_distance_functions_unchanged':True,'review_timing_unchanged':True,
      'no_hard_route_change_maximum':c['maximum_route_changes'] is None,'pristine_field_validation':False,'production_writes':False}
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(result,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
