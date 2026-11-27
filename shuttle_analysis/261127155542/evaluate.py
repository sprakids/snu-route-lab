"""Score measured boardings and queues, and check the matched class-end intervention."""
import argparse
from collections import Counter
from pathlib import Path
from statistics import mean
import sys

HERE = Path(__file__).resolve().parent
V12 = HERE.parent / '261125170855'
ACC = V12 / 'comparison_20261127/accuracy'
sys.path.insert(0, str(ACC))
from check_r_regressions import card_observations, field_rows
from score_versions import DAYS, SERVICES, read, records, save_json, transit, write_rows

STOPS = {'upper2': '120000173', 'upper1': '120000174', 'eng_entry': '120000190'}
WINDOW = (15, 16, 17, 18)


def boardings():
    names, observed_four, campus = card_observations()
    observed = Counter()
    for r in records(ACC.parent / '교내정류장별_5분_승차대조.csv'):
        if r['V12_승차지지원'] == '1':
            observed[r['승차정류장ID'], int(r['시작시각'][:2])] += int(r['교외하차_카드승객수'])
    assert all(observed[k] == y for k, y in observed_four.items())
    common = read(V12/'viewer-data/common.json.gz')
    detail, scores = [], []
    areas = {name: [s] for name, s in STOPS.items()}
    areas.update(upper_three=list(STOPS.values()), campus=list(names))
    for service in SERVICES:
        key = f'{service}-thu'
        for group in ('V12', 'upper120', 'upper60', 'allplus30'):
            root = V12/'runs/candidate' if group == 'V12' else HERE/'runs'/group
            actual_model = transit(read(root/key/f'audit-{key}.json.gz'), common, set(names), campus)[-1]
            for s in names:
                for h in range(24):
                    detail.append(dict(model=group, service=service, stop_id=s, stop_name=names[s], hour=h,
                                       observed=observed[s,h], predicted=actual_model[s,h]))
            for name, stations in areas.items():
                def hours(counts):
                    return [sum(counts[s,h] for s in stations) for h in WINDOW]
                y, m = hours(observed), hours(actual_model)
                scores.append(dict(model=group, service=service, area=name, measured_hours=y, modeled_hours=m,
                                   observed_late_pct=100*sum(y[2:])/sum(y), modeled_late_pct=100*sum(m[2:])/sum(m),
                                   obs_total=sum(y), model_total=sum(m),
                                   mae_stop_hour=mean(abs(observed[s,h]-actual_model[s,h]) for s in stations for h in WINDOW),
                                   abs_error_18=abs(y[-1]-m[-1])))
    write_rows(HERE/'목요일_정류장별_승차.csv', detail)
    save_json(HERE/'card_scores.json', scores)


def paired_lags(strata):
    by_key = {(r['end_minute'],r['zone']): r for r in strata}
    weight = affected = difference = modeled_change = 0.
    upper_eligible = sum(r['mass'] for r in strata if r['zone']=='upper' and r['end_minute']<=1080)
    for (minute, zone), r in by_key.items():
        if zone != 'upper' or minute > 1080 or (minute,'other') not in by_key:
            continue
        other = by_key[minute,'other']
        assert not other.get('delta_min_mass', 0)
        difference += r['v12_lag_min_mass'] - r['mass'] * other['v12_lag_min_mass']/other['mass']
        weight += r['mass']
        affected += r.get('affected', 0)
        modeled_change += r.get('delta_min_mass', 0)
    return dict(matched_upper_mass=weight, upper_eligible_mass=upper_eligible,
                matched_affected=affected, upper_minus_other_v12_min=difference/weight,
                upper_minus_other_r_min=(difference+modeled_change)/weight,
                extra_min_per_upper=modeled_change/weight, extra_min_per_affected=modeled_change/affected)


def operating_checks():
    metrics = []
    for variant, days in [('upper120',DAYS),('upper60',('thu',)),('allplus30',('thu',))]:
        for day in days:
            for service in SERVICES:
                key = f'{service}-{day}'
                r = read(HERE/'runs'/variant/key/'summary.json')
                official = read(V12/'runs/candidate'/key/'summary.json')
                assert r['identity'] == official['identity'] and abs(r['daily']-official['daily']) < 1e-6
                metrics.append(dict(variant=variant, day=day, service=service, daily=r['daily'],
                                    max_wait_min=r['max_continuous_wait'], over20_mass=r['over20_weight'],
                                    unserved=r['unserved'], capacity_violations=r['capacity_violations'],
                                    **paired_lags(r['strata'])))
    write_rows(HERE/'요일별_실험검산.csv', metrics)


def field_checks():
    source = records(ACC/'queue.csv'), records(ACC/'departures.csv'), records(ACC/'personal.csv')
    result = []
    for service in SERVICES:
        result.extend(field_rows([HERE/'runs'], 'upper120', service, *source))
    write_rows(HERE/'현장_제보별_비교.csv', result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('section', choices=['cards','checks','all'], default='all', nargs='?')
    section = parser.parse_args().section
    if section in ('cards','all'):
        boardings()
    if section in ('checks','all'):
        operating_checks()
        field_checks()
