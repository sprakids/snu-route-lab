"""Reconcile the stronger time peak and observed Daehak-dong walk scenario."""
import csv
import json
import math
import sys
from pathlib import Path
from bisect import bisect_right

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / '261124095620'
CURVE = HERE.parent / '261124100719'
sys.path.insert(0, str(PREVIOUS))
from completed_modes import modes
from compare import DAYS, read_result
from run import load_v11


def read(path):
    return json.loads(path.read_bytes())


def save_csv(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def field_queues(folder):
    receipt, = (folder / 'runs/regular-mon').glob('attempt-*/result.json')
    timeline = read(receipt.parent / 'regular-mon.json')['queue_timeline']
    observations = [('설입행 행정관', 1, 60780, 53, 53), ('문화관', 59, 60900, 5, 5),
                    ('서울대학교 21128', 62, 61380, 33, 39)]
    rows = []
    for name, node, t0, low, high in observations:
        steps = timeline[node]
        times = [v[0] for v in steps]
        cuts = sorted({t0, t0 + 60, *(t for t in times if t0 < t < t0 + 60)})
        mean, error = 0., 0.
        for start, end in zip(cuts, cuts[1:]):
            idx = bisect_right(times, start) - 1
            count = steps[idx][1] if idx >= 0 else 0.
            duration = (end - start) / 60
            mean += duration * count
            error += duration * max(low - count, count - high, 0.)
        rows.append(dict(정류장=name, 시각=f'{t0//3600:02d}:{t0//60%60:02d}', 관측_하한=low,
                         관측_상한=high, 분내_평균줄=mean, 분내_기대절대오차=error))
    return rows


def main():
    selection = read(HERE / 'selection.json')
    chosen = HERE / 'rates' / str(selection['selected_percent'])
    settings = [('기존 R', PREVIOUS), ('하교확률만 수정', CURVE), ('두 변경 적용', chosen)]
    counts, field, checks = [], [], []
    destinations = load_v11()['destination_keys']
    with (PREVIOUS / '대학동_완료이동_수단별.csv').open(encoding='utf-8-sig') as stream:
        archived = {row['weekday']: row for row in csv.DictReader(stream) if row['eligible_conversion_percent'] == '60'}
    for label, folder in settings:
        field.extend(dict(조건=label, **row) for row in field_queues(folder))
        for day, did in DAYS.items():
            if folder == PREVIOUS:
                counts_day = {key: float(value) for key, value in archived[day].items()
                              if key not in ('weekday', 'eligible_conversion_percent')}
            else:
                counts_day = modes(folder, did, destinations)
            counts.append(dict(조건=label, 요일=day, **counts_day))
            for service in ('regular', 'peak'):
                case = f'{service}-{did}'
                result = read_result(folder, case)
                attempt, = (folder / 'runs' / case).glob('attempt-*/result.json')
                profile = read(attempt.parent / 'departure_profile.json')
                if folder == chosen:
                    control, = (CURVE / 'runs' / case).glob('attempt-*/departure_profile.json')
                    assert profile == read(control)
                inv = result['invariants']
                assert math.isclose(inv['input_weight'], inv['final_weight'], abs_tol=1e-6)
                assert inv['input_weight'] <= 30_000 and inv['capacity_violations'] == 0
                stops = read(attempt.parent / 'all_stop_waits.json')
                mass = math.fsum(row['waiting_episode_weight'] for row in stops.values())
                mean = math.fsum(row['waiting_episode_weight'] * row['mean_continuous_wait_min']
                                 for row in stops.values() if row['waiting_episode_weight']) / mass
                checks.append(dict(조건=label, 요일=day, 배차=service, 하교건수=inv['input_weight'],
                                   평균_정류장대기_분=mean, 최대_정류장대기_분=result['max_wait_min'],
                                   이십분초과_정류장대기_건수=result['over20_weight'],
                                   미완료=inv['unserved_trip_weight'], 정원초과=inv['capacity_violations'],
                                   대학동17시_잔여줄=result['candidate']['queue_after_1700']))
    save_csv(HERE / '대학동_완료이동_비교.csv', counts)
    save_csv(HERE / '평일_배차별_대기_비교.csv', checks)
    save_csv(HERE / '기존관측_요일시각_비교.csv', field)

    for label, _ in settings:
        cohort = [c for c in counts if c['조건'] == label]
        denominator = sum(c['daehak_trip_mass'] for c in cohort)
        print(label, 'walk/PM', sum(c['walk_pm_no_boarding'] for c in cohort) / denominator,
              'shuttle', sum(c['boarded_daehak_shuttle'] for c in cohort) / denominator)


if __name__ == '__main__':
    main()
