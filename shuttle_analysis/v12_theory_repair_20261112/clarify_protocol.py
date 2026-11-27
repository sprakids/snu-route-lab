"""Clarify inherited protocol prose without changing the frozen execution table."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json
ROOT=Path(__file__).resolve().parent
work=ROOT.parent/'261112132736';path=work/'experiment_lock.json'
lock=json.loads(path.read_bytes());target=work/'protocol_clarification.json';assert not target.exists()
value={'created_at':datetime.now(timezone(timedelta(hours=9))).isoformat(),
  'original_experiment_lock_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
  'original_frozen_table_changed':False,'registered_cases':len(lock['pilot_cases']),
  'actual_groups':{'origin_pilots':['repair-combined-regular-mon','repair-combined-regular-tue','ablation-free_origin-regular-mon'],
    'grid':'Ten main weekday/scenario cases; reuse completed same-case receipts'},
  'prose_correction':'The inherited selection_rule string mentions two Tuesday ablations. The immutable explicit pilot_cases and origin_pilots-started lists actually register ten main cases plus one Monday free-origin contrast. Tuesday free-origin is reused from261112132407. This clarification changes no case or outcome.',
  'field_report_use':'Four old queue reports informed diagnosis and structural model selection. No numerical preference/hazard coefficients were tuned to those points. Structural selection is still use of the data, so these reports are not independent holdout or evidence of validated accuracy.',
  'source_prior_scope':'Preserved initial mixture is an inherited scenario, not measured modal shares or confirmed student destinations.',
  'frozen_runtime_and_inputs_unchanged':True}
target.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8');print('PROTOCOL_CLARIFIED',len(lock['pilot_cases']))
