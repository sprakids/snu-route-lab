"""Compare matched observations, V12 one-setting variants, and passenger flows."""
import argparse
from collections import Counter
from pathlib import Path
from statistics import mean

from score_versions import Curve, OUT, OBS, ROOT, V12, VERSIONS, read, records, save_json, seconds, transit


def field_changes():
    data = records(OUT / 'queue.csv')
    results = {}
    for service in ('regular', 'peak'):
        pairs = {}
        for row in data:
            if row['service'] == service and row['version'] in ('V11', 'V12'):
                pairs.setdefault(row['observation'], {})[row['version']] = row
        changes = {}
        for key, pair in pairs.items():
            before = float(pair['V11']['expected_abs_error'])
            after = float(pair['V12']['expected_abs_error'])
            changes[key] = dict(v11_mae=before, v12_mae=after, reduction=before-after)
        assert len(changes) == 7
        total = sum(r['reduction'] for r in changes.values())
        for row in changes.values():
            row['share_of_net_decrease_pct'] = 100 * row['reduction'] / total
        results[service] = changes
    return results


def field_variants(extra_runs):
    cases = {}
    identities = {}
    for variant in ('candidate', 'parallel', 'berth_only'):
        observations = {}
        cases[variant] = {'observations': observations, 'days': {}}
        for day in ('mon', 'tue', 'wed'):
            root = V12 / 'runs' if day == 'tue' or variant == 'candidate' else extra_runs
            summary = read(root / variant / f'peak-{day}' / 'summary.json')
            cases[variant]['days'][day] = {k: summary[k] for k in (
                'daily', 'identity', 'departure_identity', 'stay_additional_minutes',
                'unserved', 'capacity_violations', 'over20_weight')}
            assert summary['day'] == day and summary['condition'] == variant and summary['service'] == 'peak'
            assert summary['unserved'] == summary['capacity_violations'] == 0
            assert summary['identity'] == identities.setdefault(day, summary['identity'])
            if variant == 'parallel':
                assert summary['departure_identity'] == cases['candidate']['days'][day]['departure_identity']
            for key, row in summary['observations'].items():
                if row['kind'] == 'outside':
                    observations[key] = dict(mean=row['mean'], mae=row['expected_abs_error'])
        assert len(observations) == 7
        cases[variant]['mae'] = mean(r['mae'] for r in observations.values())
    return cases


def flows():
    results = {}
    for version in ('V11', 'V12'):
        folder = VERSIONS[version]
        view = folder / ('viewer-data' if version == 'V12' else 'public_data')
        node = read(view / 'common.json.gz')['hot_nodes']['admin_snu']
        values = results[version] = {}
        for day, clock in [('tue', '15:23'), ('wed', '16:00')]:
            key = 'peak-' + day
            archive = folder / 'runs' / 'candidate' / key if version == 'V12' else folder
            waits = [w for w in read(archive / f'audit-{key}.json.gz')['wait_audit'] if w['node'] == node]
            minute = seconds(clock)
            start = minute - 300
            def exposure(t):
                # Fraction of the observation minute after this arrival or exit.
                return min(1, max(0, (minute + 60 - t) / 60)) if t >= start else 0
            stock = sum(w['weight'] for w in waits if w['arrival'] < start <= w['end'])
            arrivals = sum(w['weight'] * exposure(w['arrival']) for w in waits)
            boarded = sum(w['weight'] * exposure(w['end']) for w in waits if w['outcome'] == 'boarded')
            left = sum(w['weight'] * exposure(w['end']) for w in waits if w['outcome'] != 'boarded')
            level = stock + arrivals - boarded - left
            check = next(r for r in records(OUT / 'queue.csv') if r['version'] == version
                         and r['service'] == 'peak' and r['clock'] == clock)
            assert abs(level - float(check['mean'])) < .01
            values[day] = dict(clock=clock, initial_queue=stock, arrivals=arrivals, boarded=boarded,
                               other_exits=left, mean_queue=level)
    return results


def departure_only_diagnostic():
    """Hold realized arrivals, bus assignments, and departures fixed; move boarding to departure."""
    data = V12 / 'viewer-data'
    node = read(data / 'common.json.gz')['hot_nodes']['admin_snu']
    field = [r for r in records(OUT / 'queue.csv') if r['version'] == 'V12'
             and r['service'] == 'peak' and r['stop'] == 'admin_snu']
    results = {}
    for day in ('mon', 'tue', 'wed'):
        replay = read(data / f'peak-{day}.json.gz')
        queue = Curve(replay['queue_timeline'][node])
        onboard = Curve(replay['onboard_wait_timeline'][node])
        for row in (r for r in field if r['day'] == day):
            a = seconds(row['clock'])
            times = sorted({a, *(t for t in queue.times + onboard.times if a < t < a + 60)})
            delayed = Curve([[t, queue.at(t) + onboard.at(t)] for t in times])
            results[row['observation']] = delayed.stats(a, a + 60, (float(row['observed_min']), float(row['observed_max'])))
    return results


def card_changes():
    observed = Counter()
    names = {}
    for row in records(OBS / '교내정류장별_5분_승차대조.csv'):
        hour = int(row['시작시각'][:2])
        if row['V12_승차지지원'] == '1' and 15 <= hour < 19:
            sid = row['승차정류장ID']
            names[sid] = row['승차정류장명']
            observed[sid, hour] += int(row['교외하차_카드승객수'])
    assert len(observed) == 152 and observed.total() == 4463
    scope = read(ROOT / 'seoul_boardings_2026-11-10/stop_scope.json')['stops']
    campus = {s['stop_id'] for s in scope if s['zone'] in ('campus_core', 'campus_annex')}
    stops = {sid: {'name': name} for sid, name in names.items()}
    for version in ('V11', 'V12'):
        root = VERSIONS[version]
        view = root / ('viewer-data' if version == 'V12' else 'public_data')
        archive = root / 'runs/candidate/peak-thu' if version == 'V12' else root
        counts = transit(read(archive / 'audit-peak-thu.json.gz'), read(view / 'common.json.gz'),
                         set(names), campus)[-1]
        for sid in names:
            stops[sid][version] = {
                'hourly': [counts[sid, h] for h in range(15, 19)],
                'mae': mean(abs(counts[sid, h] - observed[sid, h]) for h in range(15, 19))}
            stops[sid]['observed'] = [observed[sid, h] for h in range(15, 19)]
        expected = read(OUT / 'scores.json')[version]['peak']['transit']['card_38_stops_x_4_hours']['mae']
        assert abs(mean(row[version]['mae'] for row in stops.values()) - expected) < 1e-6
    return stops


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('extra_runs', type=Path, help='Directory of the alternate Monday and Wednesday runs')
    args = parser.parse_args()
    changes = field_changes()
    variants = field_variants(args.extra_runs)
    for key, row in variants['candidate']['observations'].items():
        assert abs(row['mae'] - changes['peak'][key]['v12_mae']) < 1e-6
    save_json(OUT / 'v11_v12_attribution.json', dict(
        field_changes=changes, variants=variants, flow_5min=flows(),
        board_at_departure_fixed_trips=departure_only_diagnostic(), card_by_stop=card_changes()))
