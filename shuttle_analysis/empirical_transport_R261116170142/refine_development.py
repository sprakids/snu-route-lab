"""Preregistered local development refinement; never reads new13th-day labels."""
from copy import deepcopy
import json
from extract_observations import ROOT, load_network, extract, derive, write_json
from evaluate_candidate import compare, acceptance


def main():
    profile = json.loads((ROOT/'artifacts/profile.json').read_text(encoding='utf-8'))
    network = load_network()
    data = extract(ROOT.parent/'empirical_transport_261116162001/private/2026-11-12.jsons.gz', '2026-11-12', network)
    derived = derive(data, network)
    trials = []
    for label, ride_scale, gate_radius in [('local_bias_and_wider_gate', .975, 60),
                                          ('wider_gate_90', .975, 90),
                                          ('shorter_ride', .95, 60)]:
        target = ROOT/'development_runs'/(label+'.json')
        if target.exists():
            raise RuntimeError('Preserve completed development refinement; no duplicate run')
        profile['settings'].update(ride_duration_scale=ride_scale, gate_radius_minutes=gate_radius)
        report, rows = compare(profile, data, derived, network)
        write_json(target, report)
        gates = acceptance(report)
        trials.append({'label': label, 'settings': dict(profile['settings']), 'gates': gates, 'report': report})
        print(json.dumps({'trial': label, 'gates': gates,
            'mae': {k: m['candidate_mae'] for k, m in report['metrics'].items()},
            'bias': {k: m['candidate_bias'] for k, m in report['metrics'].items() if k != 'crowd'}}), flush=True)
    # Changes to ride and gate are separate. Select each only using its own
    # development MAE among preregistered passing settings; class rule unchanged.
    selected = deepcopy(profile['settings'])
    for name, key in [('ride', 'ride_duration_scale'), ('gate', 'gate_radius_minutes')]:
        good = [t for t in trials if t['gates'][name]]
        pool = good or trials
        chosen = min(pool, key=lambda t: t['report']['metrics'][name]['candidate_mae'])
        selected[key] = chosen['settings'][key]
    profile['settings'] = selected
    report, rows = compare(profile, data, derived, network)
    # Preserve the first trained profile under phase1. This is development only.
    write_json(ROOT/'artifacts/profile.json', profile)
    write_json(ROOT/'artifacts/development_comparison.json', report)
    write_json(ROOT/'artifacts/development_selection.json', {'model_id': profile['model_id'], 'development_date': '2026-11-12',
        'already_opened_date_not_untouched_validation': True, 'settings': selected,
        'component_development_gate': acceptance(report), 'operating_adoption_permitted': False,
        'phase1_preserved': 'development_runs/phase1', 'new_holdout13_opened': False})
    print(json.dumps({'final_settings': selected, 'development_gates': acceptance(report)}), flush=True)


if __name__ == '__main__':
    main()
