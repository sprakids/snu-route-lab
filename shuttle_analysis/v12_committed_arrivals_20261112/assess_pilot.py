"""Fixed pilot budgets and explicit preservation of late walking preference."""
from pathlib import Path
import argparse,ast,csv,hashlib,json,math
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'261112171315'
PRIMARY={'20261109-1653-admin-snu-queue-01','20261109-1703-snu-gate-queue-01','20261110-1523-admin-snu-queue-wait-01'}
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def score(rs):
    rs=[r for r in rs if r['observation_id'] in PRIMARY];assert len(rs)==3
    return math.fsum(float(r['expected_absolute_distance_to_count_or_interval'])/((float(r['observed_low'])+float(r['observed_high']))/2) for r in rs)/3
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve();out=w/'pilot-assessment.json';assert not out.exists()
    d=read(w/'observations-diagnostics.json');v=read(w/'observations-validation.json')
    own=[r for r in rows(w/'observations-field-comparison.csv') if r['model']==w.name and r['scenario']=='regular']
    old=[r for r in rows(PARENT/'grid-field-comparison.csv') if r['model']==PARENT.name and r['scenario']=='regular']
    before=score(old);after=score(own);comparisons=[]
    for r in own:
        b=next(b for b in old if b['observation_id']==r['observation_id'])
        comparisons.append({'id':r['observation_id'],'before_mean':float(b['uniform_minute_mean']),'after_mean':float(r['uniform_minute_mean']),
          'before_error':float(b['expected_absolute_distance_to_count_or_interval']),'after_error':float(r['expected_absolute_distance_to_count_or_interval'])})
    baseline=read(PARENT/'grid-validation.json')['results'];travel=[]
    for r in v['results']:
        b=next(b for b in baseline if all(b['case'][k]==r['case'][k] for k in ('day','scenario','seed','operations')))
        q=r['extended_diagnostics']['finished_trip_quantiles']['total_min'];oldq=b['extended_diagnostics']['finished_trip_quantiles']['total_min']
        travel.append({'day':r['case']['day'],'mean_delta':q['mean']-oldq['mean'],'p99_delta':q['p99']-oldq['p99'],'maximum_before':oldq['maximum'],'maximum_after':q['maximum']})
    c=read(w/'config.json');oldc=read(PARENT/'config.json')
    changed={k for k in set(c)|set(oldc) if c.get(k)!=oldc.get(k)}
    assert changed<= {'release_id','version_family','forecast_committed_arrivals','committed_arrivals_information','later_walking_preference'},changed
    unchanged_files=['preferences.py','hazard.py','physics.py','prepare.py','capacity.py','operations.py']
    for n in unchanged_files:assert sha(w/n)==sha(PARENT/n),n
    methods=['generalized','alternative_choices','maybe_switch','commit_switch','initial_choice','legacy_accept_boarding']
    def functions(path):return {n.name:ast.dump(n,include_attributes=False) for n in ast.walk(ast.parse(path.read_text(encoding='utf8'))) if isinstance(n,ast.FunctionDef)}
    x,y=functions(w/'policy.py'),functions(PARENT/'policy.py')
    for name in methods:assert x[name]==y[name],name
    maximum=max(r['extended_diagnostics']['all_recorded_time_max_continuous_wait_min'] for r in v['results'])
    invariants=d['all_invariant_audits_pass'] and d['all_continuous_waits_under20'] and d['unserved_trip_weight']<1e-7
    budgets=after<=before*1.1+1e-9 and all(r['mean_delta']<=.5 and r['p99_delta']<=1. for r in travel)
    result={'status':'VIABLE_FOR_FULL_GRID' if invariants and budgets else 'PILOT_REVIEW_BUDGET_FAILED','release_id':w.name,
      'parent':PARENT.name,'invariants_pass':invariants,'review_budgets_pass':budgets,'primary_loss_before':before,'primary_loss_after':after,
      'field_comparisons':comparisons,'travel_comparisons':travel,'maximum_all_recorded_continuous_wait_min':maximum,
      'preference_and_physics_files_unchanged':unchanged_files,'policy_methods_unchanged':methods,'config_changed_keys':sorted(changed),
      'parameter_fitting_this_round':False,'inherited_alpha':c['cohort_release_lag_scale'],'pristine_field_validation':False,'production_writes':False}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(result,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
