"""Freeze first, then read exactly one protected day. Retuning requires a new day."""
from collections import Counter
from datetime import datetime
from pathlib import Path
import argparse
import csv
import gzip
import hashlib
import importlib.util
import json
import subprocess

from extract_observations import ROOT, KST, load_network, extract, derive, write_json, digest
from evaluate_candidate import compare, acceptance

DAY = '2026-11-12'


def frozen_files():
    return sorted(list(ROOT.glob('*.py')) + list((ROOT/'baseline_app').glob('*.py')) +
                  list((ROOT/'baseline_app/data').glob('*.json')) +
                  [ROOT/'artifacts/profile.json', ROOT/'artifacts/development_selection.json'])


def freeze():
    target = ROOT/'artifacts/frozen_protocol.json'
    if target.exists() or (ROOT/'private'/f'{DAY}.jsons.gz').exists():
        raise RuntimeError('Protocol already frozen or labels already present; preserve and create a child revision')
    protocol = {'model_id': 'R261116162001', 'frozen_at': datetime.now(KST).isoformat(),
                'training': ['2026-11-10'], 'development_already_explored': ['2026-11-11'],
                'first_unopened_holdout': DAY, 'leave_unopened': ['2026-11-13', '2026-11-14', '2026-11-15'],
                'scope': 'city observed stop opportunities, passage times, ordinal grades; no observed shuttle/student queue truth',
                'source_qualification': {'unique_provider_rows_min': 10000, 'confirmed_stop_events_per_route_min': 20, 'city_routes_required': 8},
                'extraction': {'stop_distance_m': 60, 'previous_provider_gap_max_s': 120, 'source_age_max_s': 150,
                               'dedup': 'route,vehicle,provider timestamp; stop event once per trip/section',
                               'headway_range_s': [15, 3600], 'joint_headway_range_s': [0, 3600],
                               'ride_max_s': 1800, 'ride_max_stop_steps': 12,
                               'grade': '3..6 to ordinal0..3; provider0 unknown; one target per trip/section/horizon'},
                'metrics': ['paired MAE and bias', 'cluster macro MAE', 'crowd congestion miss rate', 'empirical coverage'],
                'acceptance': 'development AND holdout: coverage>=0.1; lower MAE, macro MAE no worse. Headway also beats registered H/2. Crowd also beats persistence and does not increase congested miss rate, with >=20 positives.',
                'no_retuning_after_opening': True, 'operating_promotion_authorized': False,
                'hashes': {str(p.relative_to(ROOT)): digest(p) for p in frozen_files()}}
    write_json(target, protocol)
    print(json.dumps({'frozen': str(target), 'sha256': digest(target), 'files': len(protocol['hashes']), 'holdout': DAY}))


def verify_freeze():
    p = json.loads((ROOT/'artifacts/frozen_protocol.json').read_text(encoding='utf-8'))
    changed = [name for name, sha in p['hashes'].items() if digest(ROOT/name) != sha]
    if changed:
        raise RuntimeError('Frozen candidate changed; cannot score this as its holdout: '+','.join(changed))
    return p


def fetch():
    verify_freeze()
    dest = ROOT/'private'/f'{DAY}.jsons.gz'
    if dest.exists():
        raise RuntimeError('Do not overwrite an opened holdout archive')
    helper = ROOT.parent/'weekly_empirical_readiness_20261116/check_recording_inventory.py'
    spec = importlib.util.spec_from_file_location('readonly_saved_credentials', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    c = module.credentials()
    # The only endpoint permitted here exports existing saved data. Authentication
    # stays on stdin, outside process arguments, console output and artifacts.
    config = ('url="'+c['url'].rstrip('/')+'/export?day='+DAY+'"\n'
              'header="Authorization: Bearer '+c['token']+'"\n')
    r = subprocess.run(['curl.exe', '--config', '-', '--silent', '--show-error', '--fail',
                        '--max-time', '55', '--connect-timeout', '10'],
                       input=config.encode(), capture_output=True, timeout=60)
    if r.returncode:
        raise RuntimeError('Saved archive export failed; curl exit '+str(r.returncode))
    if not r.stdout.startswith(b'\x1f\x8b'):
        raise RuntimeError('Saved export is not gzip; no labels evaluated')
    # Successful fetch is the beginning of holdout opening, permanently recorded.
    write_json(ROOT/'artifacts/holdout_opening.json', {'opened_at': datetime.now(KST).isoformat(),
               'day': DAY, 'sha256': hashlib.sha256(r.stdout).hexdigest(), 'bytes': len(r.stdout),
               'saved_export_requests': 1, 'new_provider_polls': 0,
               'other_new_days_opened': [], 'frozen_protocol_sha256': digest(ROOT/'artifacts/frozen_protocol.json')})
    dest.write_bytes(r.stdout)
    print(json.dumps({'saved_day': DAY, 'bytes': len(r.stdout), 'new_provider_polls': 0, 'protected_days_13_to_15_opened': False}))


def evaluate():
    protocol = verify_freeze()
    target = ROOT/'artifacts/holdout_comparison.json'
    if target.exists():
        raise RuntimeError('Holdout already evaluated; preserve its result')
    network = load_network()
    data = extract(ROOT/'private'/f'{DAY}.jsons.gz', DAY, network)
    counts = Counter(p['r'] for p in data['passages'])
    qualified = data['quality']['unique_provider_rows'] >= 10000 and len(counts) == 8 and min(counts.values()) >= 20
    write_json(ROOT/'artifacts/holdout_source_quality.json', {'qualified': qualified, 'quality': data['quality'], 'stop_events_per_route': dict(counts)})
    if not qualified:
        raise RuntimeError('Preregistered source quality gate failed; do not select another date based on score')
    profile = json.loads((ROOT/'artifacts/profile.json').read_text(encoding='utf-8'))
    report, rows = compare(profile, data, derive(data, network), network)
    report['source_sha256'] = data['source_sha256']
    report['frozen_protocol_sha256'] = digest(ROOT/'artifacts/frozen_protocol.json')
    write_json(target, report)
    dev = json.loads((ROOT/'artifacts/development_selection.json').read_text(encoding='utf-8'))['component_development_gate']
    tested = acceptance(report)
    review = {k: dev[k] and tested[k] for k in dev}
    write_json(ROOT/'artifacts/review_gate.json', {'model_id': profile['model_id'], 'development_gate': dev,
               'heldout_gate': tested, 'eligible_for_review_only': review, 'operating_model_replaced': False,
               'user_approval_required_for_V11_replacement': True, 'additional_untouched_days': protocol['leave_unopened']})
    for name, values in rows.items():
        if not values:
            continue
        with (ROOT/'private'/f'{DAY}_{name}_predictions.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(values[0]))
            writer.writeheader()
            writer.writerows(values)
    print(json.dumps({'holdout_completed': DAY, 'eligible_for_review_only': review, 'operating_model_replaced': False,
                      'metrics': {k: {n: v for n, v in m.items() if n not in ['by_route', 'registered_half_headway', 'persistence_comparison']}
                                  for k, m in report['metrics'].items()}}, ensure_ascii=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['freeze', 'fetch', 'evaluate', 'verify'])
    args = parser.parse_args()
    {'freeze': freeze, 'fetch': fetch, 'evaluate': evaluate, 'verify': verify_freeze}[args.action]()
