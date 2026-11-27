"""Compare a research run with both official versions on identical field and card observations."""
import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from math import isclose
from pathlib import Path
from statistics import mean

from score_versions import OUT, OBS, ROOT, V12, VERSIONS, read, records, transit


@dataclass(frozen=True)
class Score:
    predicted: float
    error: float


def scalar(predicted, observed):
    return Score(predicted, abs(predicted - observed))


def direction(a, b):
    if isclose(a, b, abs_tol=1e-6, rel_tol=0):
        return 0
    return 1 if a > b else -1


def compare_errors(v11, v12, research):
    if research is None or v12 is None:
        return '비교 불가'
    delta = direction(research.error, v12.error)
    if v11 is None:
        return {-1: 'V12 기준 개선', 0: 'V12 기준 유지', 1: 'V12 기준 악화'}[delta]
    before = direction(v12.error, v11.error)
    old_gap = direction(research.error, v11.error)
    if before < 0:
        if delta <= 0:
            return '개선 유지' if delta == 0 else '추가 개선'
        return {-1: '개선 일부 반납', 0: '개선 전부 반납', 1: '개선 반납 후 V11 초과'}[old_gap]
    if before > 0:
        if delta >= 0:
            return '기존 악화 지속' if delta == 0 else '기존 악화 확대'
        return '기존 악화 일부 회복' if old_gap > 0 else 'V11 수준 이상 회복'
    return {-1: '새 개선', 0: '유지', 1: '새 악화'}[delta]


def case_dir(roots, variant, service, day):
    key = f'{service}-{day}'
    for root in roots:
        path = root / variant / key
        if (path / 'summary.json').is_file():
            return path
    raise FileNotFoundError(f'{variant}/{key}/summary.json')


def check_controls(summary, reference, variant, service, day):
    assert (summary['day'], summary['service'], summary['condition']) == (day, service, variant)
    assert isclose(summary['daily'], reference['daily'], rel_tol=0, abs_tol=1e-6)
    # The identity includes the initial route. A route-choice intervention may change it.
    if variant in ('parallel', 'berth_only'):
        assert summary['identity'] == reference['identity']
    if variant == 'parallel':
        assert summary['departure_identity'] == reference['departure_identity']


def row(variant, service, metric, key, observed, unit, v11, v12, research):
    result = dict(연구조건=variant, 배차=service, 항목=metric, 관측=key, 실측=observed, 단위=unit)
    for label, value in [('V11', v11), ('V12', v12), ('R', research)]:
        result[label+'예측'] = value.predicted if value else None
        result[label+'오차'] = value.error if value else None
    for label, a, b in [('V12-V11', v12, v11), ('R-V12', research, v12), ('R-V11', research, v11)]:
        result[label+'오차차이'] = a.error - b.error if a and b else None
    result['판정'] = compare_errors(v11, v12, research)
    return result


def field_rows(roots, variant, service, original, claim, clocked):
    rows = []
    summaries = {}
    for day in ('mon', 'tue', 'wed'):
        s = read(case_dir(roots, variant, service, day) / 'summary.json')
        reference = read(V12 / 'runs/candidate' / f'{service}-{day}' / 'summary.json')
        check_controls(s, reference, variant, service, day)
        summaries[day] = s
    for r in original:
        if r['version'] != 'V12' or r['service'] != service:
            continue
        key = r['observation']
        prev = next(z for z in original if z['version']=='V11' and z['service']==service and z['observation']==key)
        current = summaries[r['day']]['observations'][key]
        lo, hi = float(r['observed_min']), float(r['observed_max'])
        assert current['kind'] == 'outside' and current['observed'] == [lo, hi] and current['matched']
        expected = str(int(lo)) if lo == hi else f'{lo:g}~{hi:g}'
        old = Score(float(prev['mean']), float(prev['expected_abs_error']))
        base = Score(float(r['mean']), float(r['expected_abs_error']))
        model = Score(current['mean'], current['expected_abs_error'])
        rows.append(row(variant, service, '바깥줄 분내 MAE', key, expected, '명', old, base, model))
        # The minute mean can look close even when the line fluctuates widely.
        def mean_gap(score):
            return Score(score.predicted, max(lo - score.predicted, score.predicted - hi, 0))
        rows.append(row(variant, service, '바깥줄 분평균 편차', key, expected, '명',
                        mean_gap(old), mean_gap(base), mean_gap(model)))
    tue = summaries['tue']
    tue_ref = read(V12/'runs/candidate'/f'{service}-tue'/'summary.json')
    onboard_key = next(k for k,r in tue_ref['observations'].items() if r['kind'] == 'onboard')
    def onboard(summary):
        o = summary['observations'][onboard_key]
        if not o['matched'] or len(summary['town_vehicle_ranges']) != 1:
            return None
        return Score(o['mean'], o['expected_abs_error'])
    rows.append(row(variant, service, '차내 대기 인원', onboard_key, 17, '명', None, onboard(tue_ref), onboard(tue)))
    for metric, prop, title in [('outside','outside_s','합류→승차'), ('aboard','onboard_s','승차→출발'),
                                ('combined','combined_s','합류→출발')]:
        matches = {z['version']: z for z in clocked if z['day']=='tue' and z['service']==service and z['metric']==metric}
        actual = float(matches['V12']['observed_seconds'])
        def time_score(z):
            return scalar(float(z['median_seconds']), actual) if z['median_seconds'] else None
        median = tue['episodes']['15:23'][prop]
        rows.append(row(variant, service, title, '11/10 행정관 설입 15:23', actual, '초',
                        time_score(matches['V11']), time_score(matches['V12']), scalar(median['median'], actual) if median else None))
    dep = {z['version']:z for z in claim if z['service']==service}
    t = float(dep['V12']['departure_second'])
    assert t == float(dep['V11']['departure_second'])
    nearest = [e for e in summaries['mon']['episodes']['16:59'] if e['time']==t]
    actual = float(dep['V12']['observed_residual'])
    rows.append(row(variant, service, '가장 가까운 17:00 출발 후 잔여', '11/23 행정관 대학동 16:59', actual, '명',
                    scalar(float(dep['V11']['residual']), actual), scalar(float(dep['V12']['residual']), actual),
                    scalar(nearest[-1]['map_outside_after'], actual) if nearest else None))
    return rows


def card_observations():
    actual = Counter()
    names = {}
    for r in records(OBS/'교내정류장별_5분_승차대조.csv'):
        h = int(r['시작시각'][:2])
        if r['V12_승차지지원']=='1' and 15 <= h < 19:
            sid = r['승차정류장ID']
            actual[sid, h] += int(r['교외하차_카드승객수'])
            names[sid] = r['승차정류장명']
    assert len(actual) == 152 and sum(actual.values()) == 4463
    campus = {s['stop_id'] for s in read(ROOT/'seoul_boardings_2026-11-10/stop_scope.json')['stops']
              if s['zone'] in ('campus_core','campus_annex')}
    return names, actual, campus


def card_rows(roots, variants, service):
    names, observed, campus = card_observations()
    estimates = {}
    common = read(V12/'viewer-data/common.json.gz')
    archive11 = VERSIONS['V11']
    common11 = read(archive11/'public_data/common.json.gz')
    assert common11['city_route_stops'] == common['city_route_stops']
    key = f'{service}-thu'
    ref = read(V12/'runs/candidate'/key/'summary.json')
    for version in ('V11', 'V12', *variants):
        if version == 'V11':
            archive = archive11
        elif version == 'V12':
            archive = V12/'runs/candidate'/key
        else:
            archive = case_dir(roots, version, service, 'thu')
            check = read(archive/'summary.json')
            check_controls(check, ref, version, service, 'thu')
        estimates[version] = transit(read(archive/f'audit-{key}.json.gz'),
                                     common11 if version == 'V11' else common,set(names),campus)[-1]
    scores = read(OUT/'scores.json')
    for v in ('V11', 'V12'):
        err = mean(abs(estimates[v][k]-y) for k,y in observed.items())
        assert isclose(err, scores[v][service]['transit']['card_38_stops_x_4_hours']['mae'], abs_tol=1e-6)
    rows = []
    for v in variants:
        versions = ('V11', 'V12', v)
        for stop, name in sorted(names.items()):
            cell_errors = {ver: [] for ver in versions}
            for h in range(15, 19):
                k = (stop, h)
                for ver in versions:
                    cell_errors[ver].append(scalar(estimates[ver][k], observed[k]))
                rows.append(row(v, service, '정류장·시간 승차', f'{name} {stop} {h}~{h+1}시', observed[k],
                                '건', *(cell_errors[ver][-1] for ver in versions)))
            label = f'{name} {stop}'
            rows.append(row(v, service, '정류장 4시간의 시간당 MAE', label, mean(observed[stop,h] for h in range(15,19)),
                            '건/시간', *(Score(mean(s.predicted for s in cell_errors[ver]),
                                                mean(s.error for s in cell_errors[ver])) for ver in versions)))
        def late_share(values):
            return 100 * sum(values[k] for k in observed if k[1]>=17) / sum(values[k] for k in observed)
        share = late_share(observed)
        rows.append(row(v, service, '17~19시 승차 비중', '11/5 공통 교내 승차지 38곳', share, '비중 %, 오차 %p',
                        *(scalar(late_share(estimates[ver]), share) for ver in versions)))
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, action='append', required=True, help='Root containing variant/service-day folders; first match wins')
    parser.add_argument('--variant', action='append', required=True, help='Undated weekday research variant')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert len(set(args.variant)) == len(args.variant) and not {'V11','V12'} & set(args.variant)
    source = records(OUT/'queue.csv'), records(OUT/'departures.csv'), records(OUT/'personal.csv')
    result = []
    for service in ('regular','peak'):
        for name in args.variant:
            result.extend(field_rows(args.runs, name, service, *source))
        result.extend(card_rows(args.runs, args.variant, service))
    keys = {(r['연구조건'],r['배차'],r['항목'],r['관측']) for r in result}
    assert len(keys) == len(result)
    with args.output.open('w', encoding='utf-8-sig', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=list(result[0]))
        writer.writeheader()
        writer.writerows(result)
