"""Check the preserved initial-mode gate separately from already-released reviews."""
from pathlib import Path
import argparse,importlib,json,sys,ast
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');a=p.parse_args();w=Path(a.candidate).resolve();out=w/'loyalty-invariant-check.json';assert not out.exists();sys.path.insert(0,str(w))
    from test_student_strategy import StudentStrategy
    from fixtures import leg
    from preferences import Prediction
    helper=StudentStrategy();checks=[]
    c,b,policy,s,events=helper.setup();s['stages']=[leg('shuttle-X')]
    for vehicle in policy.test_fleet:vehicle['rid']='shuttle-X'
    policy.student_initialize(s)
    policy.predict=lambda *a,**k:Prediction(350.,wait=300.,first_wait=300.)
    assert not policy.maybe_switch(s,50.,'queue_recheck') and not s['student_flexible'] and s['queued'];checks.append('initial_shuttle_stays_loyal_below_personal_threshold')
    policy.predict=lambda *a,**k:Prediction(3050.,wait=3000.,first_wait=3000.)
    assert not policy.maybe_switch(s,50.,'queue_recheck') and s['student_flexible'] and s['queued'] and not s['history'];checks.append('long_forecast_releases_eligibility_without_forced_exit')
    pred=Prediction(350.,wait=300.,first_wait=300.);assert policy.student_review_context(s,50.,pred)[0];checks.append('released_eligibility_survives_lower_wait_forecast')
    policy.predict=lambda *a,**k:pred
    assert not policy.maybe_switch(s,50.,'queue_recheck') and s['queued'] and not s['history'];checks.append('continued_wait_is_a_valid_choice_after_release')
    text=(w/'behavioral_policy.py').read_text(encoding='utf8')
    assert text.count("state['student_flexible']=True")==1
    function=next(x for x in ast.walk(ast.parse(text)) if isinstance(x,ast.FunctionDef) and x.name=='maybe_switch')
    assignment=next(i for i,x in enumerate(function.body) if isinstance(x,ast.Assign) and "student_flexible" in ast.unparse(x) and ast.unparse(x.value)=='True')
    assert any(isinstance(x,ast.If) and ast.unparse(x.test)=='not stressed' and any(isinstance(z,ast.Return) and ast.unparse(z.value)=='False' for z in ast.walk(x)) for x in function.body[:assignment])
    checks.append('single_positive_release_assignment_is_guarded_by_eligibility_context')
    out.write_text(json.dumps({'status':'PASS','checks':checks,'scope':'Initial loyalty and allowed-review guard checks; does not reconstruct every unexported first-release timestamp','production_writes':False},ensure_ascii=False,indent=2),encoding='utf8');print('LOYALTY_GUARD_CHECKS_PASS',len(checks),flush=True)
if __name__=='__main__':main()
