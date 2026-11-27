"""Count how Daehak-dong trips actually finished under the two initial-choice settings."""
import csv
import gzip
import json
import math
from collections import Counter

from compare import DAYS, HERE, PREVIOUS, read_result
from run import load_v11


def modes(folder, did, destinations):
    case = f'regular-{did}'
    checked = read_result(folder, case)
    receipt, = (folder / 'runs' / case).glob('attempt-*/result.json')
    with gzip.open(receipt.parent / f'audit-{case}.json.gz', 'rt', encoding='utf8') as stream:
        audit = json.load(stream)
    vehicle_routes = {event[2]: event[11] for event in audit['events']}
    totals = Counter()
    for trip in audit['legs']:
        if destinations[str(trip['id'])] != 'daehak':
            continue
        # Split groups carry disjoint weights in the V11 completed-trip ledger.
        rides = [vehicle_routes[leg[6]] for leg in trip['legs'] if leg[0] == 3]
        if trip['unserved']:
            category = 'unserved'
        elif not rides:
            category = 'walk_pm_no_boarding'
        elif 'shuttle-daehak' in rides:
            category = 'boarded_daehak_shuttle'
        else:
            category = 'boarded_other_services_only'
        totals[category] += trip['weight']
    denominator = checked['selection']['destination_mass']
    assert math.isclose(math.fsum(totals.values()), denominator, abs_tol=1e-6)
    return {'daehak_trip_mass': denominator, **{
        key: totals[key] for key in ('walk_pm_no_boarding', 'boarded_daehak_shuttle',
                                     'boarded_other_services_only', 'unserved')}}


def main():
    destinations = load_v11()['destination_keys']
    rows = []
    for rate, folder in [(50, PREVIOUS), (60, HERE)]:
        for day, did in DAYS.items():
            counts = modes(folder, did, destinations)
            rows.append(dict(weekday=day, eligible_conversion_percent=rate, **counts))
    with (HERE / '대학동_완료이동_수단별.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for rate in (50, 60):
        period = [row for row in rows if row['eligible_conversion_percent'] == rate]
        total = math.fsum(row['daehak_trip_mass'] for row in period)
        print(rate, 'walk/PM', math.fsum(row['walk_pm_no_boarding'] for row in period) / total,
              'Daehak shuttle', math.fsum(row['boarded_daehak_shuttle'] for row in period) / total, flush=True)


if __name__ == '__main__':
    main()
