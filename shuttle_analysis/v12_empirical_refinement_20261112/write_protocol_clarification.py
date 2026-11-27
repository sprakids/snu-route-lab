"""Add scope clarification without altering frozen runtime or earlier protocols."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parent
for stamp in (tuple(sys.argv[1:]) or ('261112165437','261112165438','261112170547','261112170548')):
    work=ROOT.parent/stamp;target=work/'protocol_clarification.json';assert not target.exists()
    names=['config.json','experiment_lock.json','future_evaluation_plan.json']
    value={'release_id':stamp,'purpose':'Clarify metadata; original frozen files unchanged',
      'queue_calibration_dates':['2026-11-09','2026-11-10'],'monday_date_inferred':True,
      'bus_evidence_fitting_date':'2026-11-10','already_explored_bus_evidence_date':'2026-11-11',
      'primary_observation_ids':['20261109-1653-admin-snu-queue-01','20261109-1703-snu-gate-queue-01','20261110-1523-admin-snu-queue-wait-01'],
      'secondary_observation_id':'20261109-1655-culture-city-queue-01',
      'calibrated_parameter':'cohort_release_lag_scale only; effective timing, not identified building egress',
      'unchanged_coefficients':'Preference, hazard, crowding and walking factors not numerically fitted in this round',
      'comparison_parent_scope':'132736 comparison includes load projection plus walking factors plus timing. Alpha-only contrast uses164617.',
      'future_rule_scope':'Earlier prohibition on fitting four reports means no hidden preference/hazard fitting and no pristine holdout claim. This explicit release-time calibration is authorized and declared separately. No further fitting after new-date outcomes are opened.',
      'source_hashes':{name:hashlib.sha256((work/name).read_bytes()).hexdigest() for name in names},
      'future_eligible_completed_date':'2026-11-12','new_day_outcomes_opened':False,'production_writes':False}
    target.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
    print('CLARIFIED',stamp)
