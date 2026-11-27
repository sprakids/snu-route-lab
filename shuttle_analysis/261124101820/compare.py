"""Compare initial and completed dorm trips with the same weekday/Daehak controls."""
import csv
import gzip
import json
import math
from collections import Counter
from pathlib import Path

from run import DAEHAK_SELECTION, HERE, base, load, load_v11

PREVIOUS = DAEHAK_SELECTION.parent / 'rates' / str(load(DAEHAK_SELECTION)['selected_percent'])
GROUPS = ('dorm_ug', 'dorm_grad', 'daehak')


def finished_modes(folder, case, destinations):
    with gzip.open(folder / f'audit-{case}.json.gz', 'rt', encoding='utf8') as stream:
        audit = json.load(stream)
    routes = {r[2]: r[11] for r in audit['events']}
    totals = {k: Counter() for k in GROUPS}
    for trip in audit['legs']:
        dest = destinations[str(trip['id'])]
        if dest not in totals:
            continue
        counts = totals[dest]
        rides = [routes[leg[6]] for leg in trip['legs'] if leg[0] == 3]
        counts['total'] += trip['weight']
        if trip['unserved']:
            counts['unserved'] += trip['weight']
        elif not rides:
            counts['walk_to_end'] += trip['weight']
        elif 'shuttle-daehak' in rides:
            counts['boarded_daehak_shuttle'] += trip['weight']
        else:
            counts['other_vehicle'] += trip['weight']
    return totals


def save_csv(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    destinations = load_v11()['destination_keys']
    mode_rows, waits, tails = [], [], []
    nodes = load(HERE / 'common.json.gz')['nodes']
    for day in '월화수목금':
        for service in ('regular', 'peak'):
            case = f'{service}-{base.DAYS[day]}'
            receipts = [next((folder / 'runs' / case).glob('attempt-*/result.json')) for folder in (PREVIOUS, HERE)]
            previous, revised = (load(file) for file in receipts)
            assert all(r['status'] == 'verified' and r['core']['status'] == 'PASS' for r in (previous, revised))
            assert load(receipts[0].parent/'departure_profile.json') == load(receipts[1].parent/'departure_profile.json')
            assert revised['invariants']['capacity_violations'] == 0 and revised['selection'] == previous['selection']
            for condition, file, result in zip(('기숙사 보정 전','기숙사 보정 후'), receipts, (previous,revised)):
                folder = file.parent
                waits.append(dict(조건=condition,요일=day,배차=service,최장대기_분=result['max_wait_min'],
                                  초과20분_가중사건=result['over20_weight'], 총하교=result['invariants']['input_weight'],
                                  미완료=result['invariants']['unserved_trip_weight'],
                                  대학동17시_잔여줄=result['candidate']['queue_after_1700'],
                                  대학동17시_차내=result['candidate']['onboard']))
                for key, stop in load(folder/'all_stop_waits.json').items():
                    if stop['over_20_minute_weight'] > 0:
                        tails.append(dict(조건=condition,요일=day,배차=service,정류장=nodes[int(key)]['name'],
                                          최장대기_분=stop['max_continuous_wait_min'], 가중사건=stop['over_20_minute_weight']))
                if service == 'regular':
                    groups = finished_modes(folder,case,destinations)
                    for group, counts in groups.items():
                        initial = (revised['dorm_initial'][group]['before' if file == receipts[0] else 'after']
                                   if group.startswith('dorm') else result['selection']['walk_only_fraction']*counts['total'])
                        if group.startswith('dorm'):
                            assert math.isclose(counts['total'],revised['dorm_initial'][group]['total'],abs_tol=1e-6)
                        assert math.isclose(sum(counts[k] for k in ('walk_to_end','boarded_daehak_shuttle','other_vehicle','unserved')),
                                            counts['total'],abs_tol=1e-6)
                        mode_rows.append(dict(조건=condition,요일=day,목적지=group,전체=counts['total'],첫선택_도보=initial,
                                              끝까지_미승차_도보=counts['walk_to_end'],대학동셔틀_이용=counts['boarded_daehak_shuttle']))
    save_csv(HERE/'요일별_기숙사_대학동_교통수단.csv', mode_rows)
    save_csv(HERE/'전체정류장_대기_비교.csv', waits)
    (HERE/'20분_초과_정류장.json').write_text(json.dumps(tails,ensure_ascii=False,indent=2),encoding='utf8')


if __name__ == '__main__':
    main()
