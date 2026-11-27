"""Check Thursday departures in the realized passenger ledger and identify who boards at stop 120000173."""
from bisect import bisect_left
from collections import Counter
import importlib.util
from math import isclose
from pathlib import Path
import sys

# Historical model code imports its own module named "run".
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('upper_stay_experiment', HERE/'run.py')
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)
UPPER, V12, official = study.UPPER, study.V12, study.official
sys.path.insert(0, str(V12/'comparison_20261127/accuracy'))
from check_r_regressions import card_observations
from score_versions import read, records, write_rows


def analyze(service, campus, exported):
    timing = official.prior.timing
    bundle, _, donors, _ = timing.inputs('목', service)
    courses = timing.ref.ref.class_events(timing.ref.load(timing.ref.ref.COURSES))
    common = bundle['prepared']['common']
    source = {}
    for p in bundle['prepared']['plans']['목']:
        uid = p[0]
        parent = donors.get(uid, uid)
        course = courses[(parent-1)//48]
        assert p[1] == str(course['building']) and course['weekday'] == '목'
        origin = '다른 권역'
        sensitivity = 0.
        if p[1] in UPPER:
            origin = '윗공대 그 외'
            if course['end_minute'] <= 1080 and timing.uniform(f'trip/{parent}') < timing.STAY_RATE:
                origin = '윗공대 기존 추가 체류 대상'
                sensitivity = timing.uniform(f'extended-activity/{parent}')
        source[uid] = (origin, sensitivity)
    key = f'{service}-thu'
    rows, original_start = [], {}
    for model, cap in [('V12',90), ('upper120',120), ('upper60',60), ('allplus30',90)]:
        folder = V12/'runs/candidate' if model == 'V12' else HERE/'runs'/model
        a = read(folder/key/f'audit-{key}.json.gz')
        events = {(e[2],e[1],e[0]):(e[11],e[12]) for e in a['events'] if e[11] in common['city_route_stops']}
        counts = Counter()
        assert {trip['id'] for trip in a['legs']} == set(source)
        for trip in a['legs']:
            uid = trip['id']
            origin, fraction = source[uid]
            if model == 'V12':
                original_start.setdefault(uid, trip['start'])
            if model == 'allplus30':
                # Reuse the same origin-to-course mapping, including split donor IDs.
                course = courses[(donors.get(uid,uid)-1)//48]
                shift = 30 if str(course['building']) in UPPER and course['end_minute'] <= 1080 else 0
            else:
                shift = (cap-90)*fraction
            assert isclose(trip['start'], original_start[uid] + 60*shift, rel_tol=0, abs_tol=1e-6)
            for mode,start,end,_,node,_,vehicle,*_ in trip['legs']:
                if mode != 3 or not 15*3600 <= start < 19*3600:
                    continue
                if common['nodes'][node].get('stop_id') != '120000173':
                    continue
                route,i = events[vehicle,node,start]
                times = common['route_info'][route]['offsets']
                j = bisect_left(times,times[i]+(end-start)-1e-5)
                assert abs(times[j]-times[i]-(end-start)) < 1e-5
                if common['city_route_stops'][route][j]['id'] not in campus:
                    counts[origin,int(start//3600)] += trip['weight']
        for hour in range(15,19):
            assert abs(sum(n for (origin,h),n in counts.items() if h==hour)-exported[model,service,hour]) < 1e-5
            for origin in sorted({g for g,fraction in source.values()}):
                rows.append(dict(model=model,service=service,hour=hour,origin=origin,boardings=counts[origin,hour]))
    return rows


if __name__ == '__main__':
    _, _, campus = card_observations()
    exported = {(r['model'],r['service'],int(r['hour'])):float(r['predicted'])
                for r in records(HERE/'목요일_정류장별_승차.csv') if r['stop_id'] == '120000173'}
    rows = []
    for service in ('regular','peak'):
        rows.extend(analyze(service, campus, exported))
    write_rows(HERE/'제2공학관_출발집단별_검산.csv', rows)
