"""Read saved R10 evidence only. No simulation, calibration or production writes."""
from pathlib import Path
from datetime import datetime, timezone
import csv, gzip, hashlib, json, math

ROOT = Path(__file__).resolve().parent
ANALYSIS = ROOT.parent
REVIEW = ANALYSIS / 'prototype_review_261110193823'
VALIDATION = ANALYSIS / 'prototype_validation_261110194553'

def load(path):
    return json.loads(path.read_bytes())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def clock(seconds):
    return f'{int(seconds // 3600):02}:{int(seconds // 60) % 60:02}:{seconds % 60:05.2f}'

def describe(trip):
    legs = trip['legs']
    components = {str(kind): math.fsum(leg[2] - leg[1] for leg in legs if leg[0] == kind) / 60
                  for kind in {leg[0] for leg in legs}}
    total = (trip['finish_time'] - trip['start']) / 60
    assert abs(math.fsum(components.values()) - total) < 1e-6
    visits = []
    for leg in legs:
        if leg[0] != 1:
            continue
        if visits and visits[-1][0] == leg[4] and abs(visits[-1][2] - leg[1]) < 1e-5:
            visits[-1][2] = leg[2]
        else:
            visits.append([leg[4], leg[1], leg[2]])
    return {'synthetic_id': trip['id'], 'parent_id': trip['parent_id'], 'trip_weight': trip['weight'],
            'start': clock(trip['start']), 'finish': clock(trip['finish_time']), 'total_min': total,
            'route_changes': len(trip['history']), 'stop_wait_visits': len(visits),
            'maximum_continuous_stop_wait_min': max((b - a) / 60 for _, a, b in visits),
            'walk_min': components.get('0', 0), 'cumulative_wait_min': components.get('1', 0),
            'ride_min': components.get('3', 0), 'history': trip['history'],
            'scope': 'Simulated weighted trip, not an observed student; station/hub destination, not individual home arrival.'}

def main():
    target = ROOT / 'diagnostic.json'
    assert not target.exists(), 'Preserve prior diagnostic results.'
    review = load(REVIEW / 'review.json')
    validation = load(VALIDATION / 'validation.json')
    assert sha(VALIDATION / 'validation.json') == review['validation_sha256']
    for name in ('engine.py', 'policy.py', 'preferences.py', 'hazard.py'):
        assert sha(Path(review['candidate']) / name) == validation['runtime_code_sha256'][name]
    case = next(r for r in validation['results'] if r['case']['day'] == '수' and r['case']['scenario'] == 'peak')
    audit_path = Path(case['source_directory']) / 'audit-peak-wed.json.gz'
    assert sha(audit_path) == case['audit_sha256']
    audit = json.loads(gzip.decompress(audit_path.read_bytes()))
    finished = [r for r in audit['legs'] if not r['unserved']]
    worst = max(finished, key=lambda r: r['finish_time'] - r['start'])
    afternoon = max((r for r in finished if r['start'] >= 15 * 3600),
                    key=lambda r: r['finish_time'] - r['start'])
    named = list(csv.DictReader((REVIEW / 'named_stop_queue_review.csv').open(encoding='utf-8-sig')))
    assert len(named) == 40
    above40 = sum(float(r['window_max_queue']) > 40 for r in named)
    assert above40 == review['named_stop_reference40_cells_exceeded_in_primary_window']
    known = load(REVIEW / 'known_queue_diagnostic.json')
    diagnostic_rows = [r for r in known['rows'] if r['scenario'] == 'regular' and r['model'] in ('V11', 'prototype_V8')]
    assert len(diagnostic_rows) == 8
    error_key = 'expected_absolute_distance_to_count_or_interval'
    worse = 0
    for obs in known['observations']:
        pair = {r['model']: r for r in diagnostic_rows if r['observation_id'] == obs['id']}
        assert len(pair) == 2
        worse += pair['prototype_V8'][error_key] > pair['V11'][error_key]
    assert worse == 4
    over90 = math.fsum(r['weight'] for r in finished if (r['finish_time'] - r['start']) / 60 > 90)
    weight = math.fsum(r['weight'] for r in finished)
    result = {'created_at': datetime.now(timezone.utc).isoformat(), 'analysis': 'Pre-improvement issue diagnosis of saved R10',
              'simulation_reruns': 0, 'model_writes': False, 'production_writes': False,
              'sources': {str(path): sha(path) for path in (REVIEW / 'review.json', REVIEW / 'known_queue_diagnostic.json',
                         VALIDATION / 'validation.json', audit_path)},
              'main_validation': {k: review[k] for k in ('maximum_continuous_wait_min', 'over20_episode_weight',
                                 'unserved_trip_weight', 'empirical_status')},
              'known_queue_diagnostics': diagnostic_rows, 'known_queue_reports_worse_than_v11': worse,
              'known_reports_are_independent_holdout': False,
              'named_reference40': {'cells': len(named), 'above40': above40, 'is_measured_hard_limit': False},
              'wed_peak_worst_all_recorded_departures': describe(worst),
              'wed_peak_worst_departures_after_1500': describe(afternoon),
              'wed_peak_over90_min': {'trip_weight': over90, 'total_input_trip_weight': weight,
                                     'percentage': 100 * over90 / weight},
              'interpretation': 'Repeated changes and long journey tails are verified model outcomes. Their attribution to cost shape, random-choice redraws, information sharing or supply errors remains a hypothesis, not a completed causal test.'}
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print('PASS_READONLY_DIAGNOSIS', 'known_reports_worse', worse, 'reference40_cells', above40,
          'worst_changes', len(worst['history']), 'afternoon_total_min', describe(afternoon)['total_min'])

if __name__ == '__main__':
    main()
