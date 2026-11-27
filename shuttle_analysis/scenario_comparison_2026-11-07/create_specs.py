"""Freeze the user-authorized scenario inputs separately from observed data."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
historical = [55.7 / 99.9, 27.2 / 99.9, 17.0 / 99.9]
dorm = 5772 / 29613
scenarios = []

def add(name, label, mix, dorm_share=dorm):
    assert abs(sum(mix) - 1) < 1e-12 and min(mix) >= 0
    scenarios.append(dict(name=name, label=label, external_mix=mix,
                          dorm_share=dorm_share, immediate_trip_share=0.5))

add('historical_reference', '과거 방향비중 참고', historical)
add('equal_reference', '교외 세 방향 균등', [1/3] * 3)
for i, (key, label) in enumerate([('snu', '서울대입구'), ('nak', '낙성대'), ('daehak', '대학동 대표점')]):
    for sign, word in [(1, 'plus'), (-1, 'minus')]:
        changed = [x + sign * (0.10 if j == i else -0.05) for j, x in enumerate(historical)]
        add(f'{key}_{word}10pp', f'{label} {sign*10:+d}%p', changed)
add('historical_dorm10', '과거 방향비중·기숙사 10%', historical, 0.10)
add('historical_dorm30', '과거 방향비중·기숙사 30%', historical, 0.30)
spec = {
    'schema_version': 1,
    'authorization': 'User requested historical reference scenarios, selected dorm ratio, implementation collaboration and station sensitivity comparison on 2026-11-07.',
    'baseline': 'historical_reference',
    'source_evidence_file': '../collaboration/research_inputs.json',
    'historical_raw_percent': [55.7, 27.2, 17.0],
    'historical_normalization': 'Divide each published percentage by 99.9; do not alter raw evidence or claim current observed shares.',
    'external_mix_order': ['snu', 'nak', 'daehak'],
    'historical_scope': '2022-04 all transit trips both directions, not students-only or homeward-only; public repost text, issuer PDF unavailable.',
    'destination_mapping_limit': 'Historical Sillim including Daehak is represented by the model Daehak point; not an observed Daehak-only share.',
    'selected_dorm_numerator': 5772,
    'selected_dorm_denominator': 29613,
    'dorm_scope_limit': 'University-wide 2025 denominator and user-selected dorm count; not measured residence rate of current Gwanak course-takers.',
    'conditional_model': 'Common walking/route samples for every scenario; no crowding feedback, capacity or background riders.',
    'primary_metric': 'Mean modeled boarding-event weight per direction-specific stop and 5-minute bin; transfers counted at transfer stops.',
    'secondary_metrics': ['first boarding only', 'transfer boarding only', 'daily modeled boarding-event volume'],
    'time_scopes': {'all': [680, 1390], 'afternoon': [900, 1390]},
    'comparison_rule': 'Compare the maximum of mean five-minute bins within each stop/day/window; also retain same historical peak-bin changes.',
    'scenarios': scenarios,
}
(ROOT / 'scenario_specs.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'scenarios': len(scenarios), 'dorm_share': dorm, 'historical_external_mix': historical}, ensure_ascii=False))
