"""Development-only shrinkage toward the preserved parent gate distribution."""
import json
from copy import deepcopy
from extract_observations import ROOT, load_network, extract, derive, write_json
from evaluate_candidate import compare, acceptance


def main():
    profile = json.loads((ROOT/'artifacts/profile.json').read_text(encoding='utf-8'))
    parent = json.loads((ROOT.parent/'empirical_transport_261116162001/artifacts/profile.json').read_text(encoding='utf-8'))
    profile['gate_parent_prior'] = {k: parent[k] for k in ['schema', 'model_id', 'dates', 'gate_events', 'network_sha256']}
    profile['gate_parent_prior'].update(headways=[], rides=[], transitions=[], grade_counts=[])
    profile['settings']['gate_new_weight'] = 1.
    network = load_network()
    data = extract(ROOT.parent/'empirical_transport_261116162001/private/2026-11-12.jsons.gz', '2026-11-12', network)
    report, rows = compare(profile, data, derive(data, network), network)
    choices = []
    # Choose the mixture in development only. Compare exactly the same sampled
    # hours as the parent; no new-day score or outcome enters this selection.
    for alpha in [.25, .5, .75, 1.]:
        mixed = deepcopy(rows)
        for row in mixed['gate']:
            row['candidate'] = round(alpha*row['candidate']+(1-alpha)*row['baseline'])
        from evaluate_candidate import metric
        m = metric(mixed['gate'])
        candidate = {**report, 'metrics': {**report['metrics'], 'gate': {**report['metrics']['gate'], **m}}}
        gate = acceptance(candidate)['gate']
        choices.append({'alpha': alpha, 'metrics': m, 'passes': gate})
    selected = min([x for x in choices if x['passes']] or choices, key=lambda x: x['metrics']['candidate_mae'])
    profile['settings']['gate_new_weight'] = selected['alpha']
    # Re-run actual unrounded distribution mixture once. This is the final
    # development score, not the rounded-cache approximation used for screening.
    report, rows = compare(profile, data, derive(data, network), network)
    write_json(ROOT/'development_runs/gate_prior_screening.json', choices)
    write_json(ROOT/'development_runs/gate_prior_exact.json', report)
    write_json(ROOT/'artifacts/profile.json', profile)
    write_json(ROOT/'artifacts/development_comparison.json', report)
    write_json(ROOT/'artifacts/development_selection.json', {'model_id': profile['model_id'], 'development_date': '2026-11-12',
        'already_opened_date_not_untouched_validation': True, 'settings': profile['settings'],
        'component_development_gate': acceptance(report), 'operating_adoption_permitted': False,
        'phase1_preserved': 'development_runs/phase1', 'new_holdout13_opened': False})
    print(json.dumps({'selected_new_gate_weight': selected['alpha'], 'screening': choices,
                      'final_development_gates': acceptance(report)}), flush=True)


if __name__ == '__main__':
    main()
