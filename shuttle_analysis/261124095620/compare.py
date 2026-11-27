"""Compare weekday simulations with only the initial Daehak-dong walk choice changed."""
import csv
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / '261124094834'
DAYS = dict(zip('월화수목금', ('mon', 'tue', 'wed', 'thu', 'fri')))


def load(path):
    return json.loads(path.read_bytes())


def read_result(folder, case):
    matches = sorted((folder / 'runs' / case).glob('attempt-*/result.json'))
    if len(matches) != 1:
        raise ValueError(f'Expected one complete run at {folder.name}/{case}')
    result = load(matches[0])
    assert result['status'] == 'verified' and result['core']['status'] == 'PASS'
    assert result['capacity'] == result['candidate']['capacity'] == 44
    return result


def compare():
    rows = []
    for day, did in DAYS.items():
        for service in ('regular', 'peak'):
            case = f'{service}-{did}'
            old, new = (read_result(folder, case) for folder in (PREVIOUS, HERE))
            prior, current = old['selection'], new['selection']
            assert (prior['target'], current['target']) == (.5, .6)
            assert old['invariants']['input_weight'] == new['invariants']['input_weight']
            assert current['destination_mass'] == prior['destination_mass']
            assert math.isclose(current['eligible_mass'], prior['eligible_mass'])
            delta = current['converted_mass'] - prior['converted_mass']
            assert delta > 0
            for key, sign in [('walk_only_fraction', 1), ('first_daehak_shuttle_fraction', -1)]:
                assert math.isclose((current[key] - prior[key]) * current['destination_mass'], sign * delta)

            row = {'weekday': day, 'service': service, 'daily_trip_mass': new['invariants']['input_weight'],
                   'destination_mass': current['destination_mass'], 'eligible_mass': current['eligible_mass'],
                   'additional_walk_mass': delta}
            for suffix, result in [('50', old), ('60', new)]:
                selection = result['selection']
                event = result['candidate']
                for key in ('realized_fraction', 'first_daehak_shuttle_fraction', 'walk_only_fraction'):
                    row[f'{key}_{suffix}'] = selection[key]
                for key in ('queue_after_1700', 'ready_left', 'onboard'):
                    row[f'{key}_{suffix}'] = event[key]
                for key in ('max_wait_min', 'over20_weight'):
                    row[f'{key}_{suffix}'] = result[key]
            row['unserved_trip_weight'] = new['invariants']['unserved_trip_weight']
            row['capacity_violations'] = new['invariants']['capacity_violations']
            row['fifo_checks'] = new['core']['checks']['fifo_events']
            assert row['daily_trip_mass'] <= 30_000 and math.isclose(
                row['daily_trip_mass'], new['invariants']['final_weight'], abs_tol=1e-6)
            assert new['core']['checks']['queue_samples'] > 0
            rows.append(row)
    with (HERE / '요일별_도보전환_비교.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    regular = [row for row in rows if row['service'] == 'regular']
    mass = math.fsum(row['destination_mass'] for row in regular)
    average = {f'{mode}_{rate}': math.fsum(row['destination_mass'] * row[f'{mode}_{rate}'] for row in regular) / mass
               for mode in ('walk_only_fraction', 'first_daehak_shuttle_fraction') for rate in ('50', '60')}
    summary = dict(weekdays_once=average, destination_week_mass=mass,
                   additional_week_walk_mass=math.fsum(row['additional_walk_mass'] for row in regular),
                   max_wait_new=max(row['max_wait_min_60'] for row in rows),
                   cases_with_over20=[row['weekday'] + '/' + row['service'] for row in rows if row['over20_weight_60'] > 0],
                   cases_with_unserved=sum(row['unserved_trip_weight'] > 0 for row in rows),
                   capacity_violations=sum(row['capacity_violations'] for row in rows),
                   verified_cases=len(rows), monday_regular=regular[0])
    (HERE / 'comparison.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    compare()
