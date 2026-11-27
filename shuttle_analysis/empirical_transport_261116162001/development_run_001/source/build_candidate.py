"""Fit only 11/10. Use already-explored 11/11 for development gating."""
from datetime import datetime
from pathlib import Path
import hashlib
import json

from extract_observations import ROOT, KST, load_network, extract, derive, write_json, digest
from empirical_transport import make_profile
from evaluate_candidate import compare, acceptance

MODEL = 'R261116162001'
RAW = ROOT.parent / 'collected_data_review_2026-11-12/raw'


def main():
    profile_path = ROOT/'artifacts/profile.json'
    if profile_path.exists():
        raise RuntimeError('Preserve existing candidate. Make a child revision instead of overwriting.')
    network = load_network()
    train = extract(RAW/'2026-11-10.jsons.gz', '2026-11-10', network)
    derived = derive(train, network)
    profile = make_profile(derived, train, MODEL, digest(ROOT/'baseline_app/data/network.json'))
    write_json(profile_path, profile)
    write_json(ROOT/'artifacts/training_quality.json', train['quality'])
    print(json.dumps({'model': MODEL, 'training_quality': train['quality'],
                      'profile_rows': {k: len(profile[k]) for k in ['headways', 'rides', 'transitions', 'gate_events', 'persistence']}}), flush=True)
    dev = extract(RAW/'2026-11-11.jsons.gz', '2026-11-11', network)
    result, rows = compare(profile, dev, derive(dev, network), network)
    write_json(ROOT/'artifacts/development_comparison.json', result)
    choices = {'model_id': MODEL, 'development_date': '2026-11-11',
               'already_explored_date_not_untouched_validation': True,
               'component_development_gate': acceptance(result),
               'operating_adoption_permitted': False}
    write_json(ROOT/'artifacts/development_selection.json', choices)
    print(json.dumps({'development_metrics': {k: {n: v for n, v in m.items() if n not in ['by_route', 'registered_half_headway', 'persistence_comparison']}
                                             for k, m in result['metrics'].items()}, 'selection': choices}, ensure_ascii=True))


if __name__ == '__main__':
    main()
