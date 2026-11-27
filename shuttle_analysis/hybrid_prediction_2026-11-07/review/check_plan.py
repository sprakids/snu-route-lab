"""Audit the supplied experiment plan only; never open test targets or keys."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone, timedelta
import json,hashlib

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'experiment_plan.json'
raw=SOURCE.read_bytes();plan=json.loads(raw)
snapshot=ROOT/'experiment_plan_review_snapshot.json'
if snapshot.exists():
    assert snapshot.read_bytes()==raw,'Plan changed: preserve the prior review and select a new review version explicitly'
else:
    snapshot.write_bytes(raw)
fields=['train_dates','tuning_dates','forward_test_dates','retrospective_test_dates']
groups={k:plan[k] for k in fields}
parse=lambda x:datetime.strptime(x,'%Y%m%d').date()
assert all(len(v)==len(set(v)) for v in groups.values())
assert all(set(groups[a]).isdisjoint(groups[b]) for i,a in enumerate(fields) for b in fields[i+1:])
frequencies={k:dict(sorted(Counter(parse(d).weekday() for d in v).items())) for k,v in groups.items()}
forward_after_development=min(map(parse,groups['forward_test_dates']))>max(map(parse,groups['train_dates']+groups['tuning_dates']))
assert forward_after_development
assert plan['hours_inclusive']==[12,22]
assert len(plan['class_features'])>0 and len(plan['background_feature'])>0
review={
    'status':'PLAN_REVIEW_ONLY_IMPLEMENTATION_NOT_YET_VERIFIED',
    'reviewed_at_kst':datetime.now(timezone(timedelta(hours=9))).isoformat(),
    'plan_sha256':hashlib.sha256(raw).hexdigest(),
    'date_counts':{k:len(v) for k,v in groups.items()},
    'date_sets_pairwise_disjoint':True,'within_split_dates_unique':True,
    'weekday_frequencies_monday0':frequencies,
    'forward_date_after_all_development_dates':forward_after_development,
    'retrospective_test_dates_are_before_some_training_dates':all(parse(d)<max(map(parse,groups['train_dates'])) for d in groups['retrospective_test_dates']),
    'test_target_files_read_by_this_review':False,'authentication_keys_read':False,'api_calls':0,
    'feature_asof_reported_in_plan':'20261106',
    'all_test_dates_before_reported_feature_asof':all(d<'20261106' for d in groups['forward_test_dates']+groups['retrospective_test_dates']),
    'owner_reported_test_access_policy':plan['test_access_policy'],
    'test_access_policy_enforcement_in_model_code_verified':False,
    'fitting_or_model_selection_executed_by_this_review':False,
    'required_preimplementation_clarifications':[
        'Ridge loss mean-vs-sum, train-only scaling, and transformation of original coefficient bounds',
        'Fit quadratic loss before clipping, or use an explicitly different solver/objective',
        'Build 1-hour lag before restricting target hours; center with target-cell training masks',
        'Freeze every evaluated model, preprocessing statistic, code identity and six-date prediction grid',
        'Qualify chronological forward target evaluation as a historical evaluation using later course features'
    ]}
(ROOT/'plan_checks.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(review,ensure_ascii=False,indent=2))
