"""Compare the two departure curves on the same timetable, fleet and weekly demand."""
import csv
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / '261124095620'
DAYS = dict(zip('월화수목금', ('mon', 'tue', 'wed', 'thu', 'fri')))


def read(path):
    return json.loads(path.read_bytes())


def attempt(folder, case):
    result, = (folder / 'runs' / case).glob('attempt-*/result.json')
    return result.parent


def save_csv(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def clock(minute):
    return f'{minute // 60:02d}:{minute % 60:02d}'


def compare_demand(day, before, after):
    old_rows = before['rate_by_class_end']
    new_rows = after['rate_by_class_end']
    assert len(old_rows) == len(new_rows)
    grouped = {}
    for old, new in zip(old_rows, new_rows, strict=True):
        minute = old['end_minute']
        assert minute == new['end_minute'] and old['enrollment'] == new['enrollment']
        expected_rate = .5 + 3 * (old['probability'] - .5)
        assert 0 <= new['probability'] <= 1 and math.isclose(expected_rate, new['probability'])
        bucket = grouped.setdefault(minute // 30 * 30, [0, 0., 0.])
        bucket[0] += new['enrollment']
        bucket[1] += old['immediate_trip_mass']
        bucket[2] += new['immediate_trip_mass']
    assert math.isclose(before['total_trip_mass'], after['total_trip_mass'], abs_tol=1e-7)
    assert math.isclose(sum(v[2] for v in grouped.values()), after['total_trip_mass'], abs_tol=1e-7)
    assert after['total_trip_mass'] <= 30_000
    return [dict(요일=day, 종료구간_시작=clock(t), 종료구간_끝_미포함=clock(t+30),
                 수강인원=n, 기존_하교확률=a/n if n else None, 수정_하교확률=b/n if n else None,
                 기존_하교건수=a, 수정_하교건수=b) for t, (n, a, b) in sorted(grouped.items())]


def stop_waits(folder):
    stops = read(folder / 'all_stop_waits.json')
    weight = math.fsum(v['waiting_episode_weight'] for v in stops.values())
    mean = math.fsum(v['mean_continuous_wait_min'] * v['waiting_episode_weight']
                     for v in stops.values() if v['waiting_episode_weight']) / weight
    return dict(mean=mean, longest=max(v['max_continuous_wait_min'] for v in stops.values()),
                over20=math.fsum(v['over_20_minute_weight'] for v in stops.values()))


def main():
    demand, services, day_profiles = [], [], {}
    for day, did in DAYS.items():
        for service in ('regular', 'peak'):
            case = f'{service}-{did}'
            old_folder, new_folder = (attempt(root, case) for root in (PREVIOUS, HERE))
            before, after = (read(folder / 'departure_profile.json') for folder in (old_folder, new_folder))
            if service == 'regular':
                demand.extend(compare_demand(day, before, after))
                day_profiles[day] = after
            else:
                assert day_profiles[day] == after
            old, new = (read(folder / 'result.json') for folder in (old_folder, new_folder))
            for run in (old, new):
                assert run['status'] == 'verified' and run['core']['status'] == 'PASS'
                assert run['capacity'] == 44 and run['selection']['target'] == .60
                assert run['invariants']['capacity_violations'] == 0
                assert math.isclose(run['invariants']['final_weight'], after['total_trip_mass'], abs_tol=1e-6)
            a, b = (stop_waits(folder) for folder in (old_folder, new_folder))
            services.append(dict(요일=day, 배차=service, 하교건수=after['total_trip_mass'],
                                 기존_한정류장_평균대기_분=a['mean'], 수정_한정류장_평균대기_분=b['mean'],
                                 기존_최장대기_분=a['longest'], 수정_최장대기_분=b['longest'],
                                 기존_20분초과_대기사건=a['over20'], 수정_20분초과_대기사건=b['over20'],
                                 미완료_이동=new['invariants']['unserved_trip_weight'],
                                 기존_대학동17시_잔여줄=old['candidate']['queue_after_1700'],
                                 수정_대학동17시_잔여줄=new['candidate']['queue_after_1700'],
                                 수정_대학동17시_차내=new['candidate']['onboard']))
    save_csv(HERE / '요일별_30분_하교확률_비교.csv', demand)
    save_csv(HERE / '요일별_배차별_대기_비교.csv', services)
    print('verified', len(services), 'weekday/service cases')


if __name__ == '__main__':
    main()
