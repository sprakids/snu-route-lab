"""Freeze the child before reading13 November; never retune against that day."""
from collections import Counter
from datetime import datetime
import argparse
import csv
import hashlib
import importlib.util
import json
import subprocess
import time

from extract_observations import ROOT, KST, load_network, extract, derive, write_json, digest
from evaluate_candidate import compare, acceptance

DAY = '2026-11-13'


def freeze():
    dest = ROOT/'artifacts/frozen_protocol.json'
    if dest.exists() or (ROOT/'private'/f'{DAY}.jsons.gz').exists():
        raise RuntimeError('Candidate frozen or labels opened; preserve and create a child')
    source = json.loads((ROOT/'parent_preservation.json').read_text(encoding='utf-8'))
    paths = [*ROOT.glob('*.py'), *(ROOT/'baseline_app').glob('*.py'), *(ROOT/'baseline_app/data').glob('*.json'),
             ROOT/'artifacts/profile.json', ROOT/'artifacts/development_selection.json',
             ROOT/'artifacts/development_comparison.json']
    external = {**source['parent_hashes']}
    raw = ROOT.parent/'collected_data_review_2026-11-12/raw'
    for day in ['2026-11-10', '2026-11-11']:
        external[str(raw/(day+'.jsons.gz'))] = digest(raw/(day+'.jsons.gz'))
    existing = ROOT.parent/'empirical_transport_261116162001/private/2026-11-12.jsons.gz'
    external[str(existing)] = digest(existing)
    value = {'model_id': 'R261116170142', 'parent_model_id': 'R261116162001',
             'frozen_at': datetime.now(KST).isoformat(), 'training_dates': ['2026-11-10', '2026-11-11'],
             'development_date_already_opened': '2026-11-12', 'first_unopened_holdout': DAY,
             'leave_unopened': ['2026-11-14', '2026-11-15'],
             'source_gate': {'city_routes': 8, 'minimum_unique_vehicle_timestamps': 10000, 'minimum_stop_events_per_route': 20},
             'comparison': 'same targets: direct parentR162001, same-two-day-data v1, local legacy, grade persistence',
             'same_binary_rule_all_arms': 'published numeric ordinal estimate>=1.5; truth>=2',
             'acceptance': {'all': 'coverage>=10%; MAE lower than direct parent; cluster macro MAE no worse',
                            'timing': 'absolute bias no more than parent+1sec; headway also beats registeredH/2',
                            'crowd': '>=20 positive and>=20 negative labels; MAE also beats persistence; FNR no worse than parent AND persistence; FPR within+2pp of BOTH; positive-grade MAE no more than persistence+.02'},
             'real_time_priority': 'fresh observed ETA/grade/current section speed first',
             'causal_online_inputs': 'passage seen<=min(query,asof); completed ride end<=known_at<=min(query,asof); no future endpoint used',
             'unknown_and_shuttle': 'provider grade0 excluded; no ordinal-to-seats conversion; no shuttle historical accuracy claimed',
             'operating_adoption_authorized': False, 'no_retuning_after_opening': True,
             'hashes': {str(p.relative_to(ROOT)): digest(p) for p in sorted(paths)}, 'external_hashes': external}
    write_json(dest, value)
    print(json.dumps({'frozen': True, 'model': value['model_id'], 'files': len(value['hashes']),
                      'protocol_sha256': digest(dest), 'holdout': DAY}))


def verify():
    doc = json.loads((ROOT/'artifacts/frozen_protocol.json').read_text(encoding='utf-8'))
    changed = [n for n, sha in doc['hashes'].items() if digest(ROOT/n) != sha]
    changed += [n for n, sha in doc['external_hashes'].items() if digest(n) != sha]
    if changed:
        raise RuntimeError('Frozen code/data or parent changed: '+','.join(changed))
    return doc


def fetch():
    verify()
    dest, partial = ROOT/'private'/f'{DAY}.jsons.gz', ROOT/'private'/f'{DAY}.jsons.gz.part'
    if dest.exists() or partial.exists():
        raise RuntimeError('Preserve existing/partial download; no duplicate fetch')
    helper = ROOT.parent/'weekly_empirical_readiness_20261116/check_recording_inventory.py'
    spec = importlib.util.spec_from_file_location('private_saved_collector', helper)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    c = module.credentials()
    config = ('url="'+c['url'].rstrip('/')+'/export?day='+DAY+'"\n'
              'header="Authorization: Bearer '+c['token']+'"\n')
    start = time.monotonic()
    result = subprocess.run(['curl.exe', '--config', '-', '--silent', '--show-error', '--fail',
                             '--max-time', '180', '--connect-timeout', '10', '--output', str(partial)],
                            input=config.encode(), capture_output=True, timeout=185)
    receipt = {'day': DAY, 'curl_exit': result.returncode, 'elapsed_seconds': time.monotonic()-start,
               'finished_at': datetime.now(KST).isoformat(), 'bytes': partial.stat().st_size if partial.exists() else 0,
               'saved_export_requests': 1, 'new_provider_polls': 0, 'labels_parsed': False}
    write_json(ROOT/'artifacts/export_receipt.json', receipt)
    if result.returncode:
        raise RuntimeError('Saved export failed; preserve receipt/partial; curl exit'+str(result.returncode))
    with partial.open('rb') as stream:
        if stream.read(2) != b'\x1f\x8b':
            raise RuntimeError('Unexpected saved archive; preserved without parsing')
    assert partial.resolve().is_relative_to(ROOT.resolve()) and dest.resolve().is_relative_to(ROOT.resolve())
    partial.rename(dest)
    write_json(ROOT/'artifacts/holdout_opening.json', {'day': DAY, 'opened_at': datetime.now(KST).isoformat(),
        'sha256': digest(dest), 'bytes': dest.stat().st_size, 'protocol_sha256': digest(ROOT/'artifacts/frozen_protocol.json'),
        'other_new_days_opened': [], 'new_provider_polls': 0})
    print(json.dumps({'saved_day': DAY, 'bytes': dest.stat().st_size, 'new_provider_polls': 0}))


def evaluate():
    doc = verify()
    target = ROOT/'artifacts/holdout_comparison.json'
    if target.exists():
        raise RuntimeError('No repeated holdout selection; preserve existing evaluation')
    network = load_network()
    data = extract(ROOT/'private'/f'{DAY}.jsons.gz', DAY, network)
    count = Counter(p['r'] for p in data['passages'])
    qualified = data['quality']['unique_provider_rows'] >= 10000 and len(count) == 8 and min(count.values()) >= 20
    write_json(ROOT/'artifacts/holdout_source_quality.json', {'qualified': qualified, 'quality': data['quality'], 'route_events': dict(count)})
    if not qualified:
        raise RuntimeError('Preregistered source qualification failed; do not choose a different day based on score')
    profile = json.loads((ROOT/'artifacts/profile.json').read_text(encoding='utf-8'))
    report, rows = compare(profile, data, derive(data, network), network)
    report.update(source_sha256=data['source_sha256'], frozen_protocol_sha256=digest(ROOT/'artifacts/frozen_protocol.json'))
    write_json(target, report)
    dev = json.loads((ROOT/'artifacts/development_selection.json').read_text(encoding='utf-8'))['component_development_gate']
    tested = acceptance(report)
    approved = {k: dev[k] and tested[k] for k in dev}
    write_json(ROOT/'artifacts/final_component_policy.json', {'model_id': profile['model_id'], 'stage': 'R_development',
        'development_gate': dev, 'heldout_gate': tested, 'shadow_enabled_components': [k for k in approved if approved[k]],
        'shadow_disabled_components': [k for k in approved if not approved[k]], 'operating_enabled_components': [],
        'operating_V11_replaced': False, 'minimum28days_validated': False, 'automatic_promotion': False,
        'protected_dates_unopened': doc['leave_unopened']})
    for name, values in rows.items():
        if not values:
            continue
        with (ROOT/'private'/f'{DAY}_{name}_predictions.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(values[0]));writer.writeheader();writer.writerows(values)
    print(json.dumps({'holdout': DAY, 'shadow_components': approved,
        'metrics': {k: {n: m.get(n) for n in ['candidate_mae', 'baseline_mae', 'mae_improvement_fraction',
                    'candidate_bias', 'baseline_bias', 'candidate_congestion_miss_rate', 'persistence_congestion_miss_rate',
                    'candidate_false_positive_rate', 'persistence_false_positive_rate']}
                    for k, m in report['metrics'].items()}, 'operating_model_changed': False}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser();p.add_argument('action', choices=['freeze', 'verify', 'fetch', 'evaluate']);a=p.parse_args()
    {'freeze': freeze, 'verify': verify, 'fetch': fetch, 'evaluate': evaluate}[a.action]()
