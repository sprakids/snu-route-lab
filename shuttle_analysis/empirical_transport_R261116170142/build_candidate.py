"""Train on stable11/10-11; tune only on the previously opened11/12."""
from copy import deepcopy
import json
import time
from extract_observations import ROOT, load_network, extract, derive, write_json, digest
from empirical_transport import make_profile
from evaluate_candidate import compare, acceptance

MODEL = 'R261116170142'
PARENT = ROOT.parent/'empirical_transport_261116162001'
RAW = ROOT.parent/'collected_data_review_2026-11-12/raw'


def main():
    dest = ROOT/'artifacts/profile.json'
    if dest.exists():
        raise RuntimeError('Preserve existing trained profile; use a child candidate')
    network = load_network();training = []
    for day in ['2026-11-10', '2026-11-11']:
        data = extract(RAW/(day+'.jsons.gz'), day, network)
        training.append((data, derive(data, network)))
        print(json.dumps({'training_day': day, 'unique_rows': data['quality']['unique_provider_rows']}), flush=True)
    profile = make_profile([d for e, d in training], [e for e, d in training], MODEL,
                           digest(ROOT/'baseline_app/data/network.json'))
    write_json(ROOT/'artifacts/training_quality.json', {e['day']: e['quality'] for e, d in training})
    data = extract(PARENT/'private/2026-11-12.jsons.gz', '2026-11-12', network)
    derived = derive(data, network)
    trials = []
    for cost in [1., 2., 3.]:
        profile['settings'] = {'recent_weight': .35, 'miss_cost': cost, 'congested_memory_floor': True}
        report, rows = compare(profile, data, derived, network)
        gates = acceptance(report)
        trial = {'miss_cost': cost, 'gates': gates, 'crowd': report['metrics']['crowd']}
        trials.append(trial)
        write_json(ROOT/'development_runs'/f'cost_{int(cost)}.json', report)
        print(json.dumps({'development_cost': cost, 'gates': gates,
                          'mae': {k: v.get('candidate_mae') for k, v in report['metrics'].items()},
                          'miss': report['metrics']['crowd'].get('candidate_congestion_miss_rate'),
                          'false_positive': report['metrics']['crowd'].get('candidate_false_positive_rate')}), flush=True)
    eligible = [t for t in trials if t['gates']['crowd']]
    selected = min(eligible or trials, key=lambda t: (t['crowd']['candidate_congestion_miss_rate'],
                   t['crowd']['candidate_mae'], t['miss_cost']))
    profile['settings'] = {'recent_weight': .35, 'miss_cost': selected['miss_cost'], 'congested_memory_floor': True}
    write_json(dest, profile)
    selected_report = json.loads((ROOT/'development_runs'/f"cost_{int(selected['miss_cost'])}.json").read_text(encoding='utf-8'))
    write_json(ROOT/'artifacts/development_comparison.json', selected_report)
    write_json(ROOT/'artifacts/development_selection.json', {'model_id': MODEL, 'development_date': '2026-11-12',
        'already_opened_date_not_untouched_validation': True, 'settings': profile['settings'],
        'component_development_gate': selected['gates'], 'operating_adoption_permitted': False,
        'selection': 'Among passing candidates minimize missed congestion, then ordinal MAE, then false-negative multiplier.'})
    print(json.dumps({'selected_cost': selected['miss_cost'], 'development_gates': selected['gates'],
                      'new_holdout13_opened': False}), flush=True)


if __name__ == '__main__':
    main()
