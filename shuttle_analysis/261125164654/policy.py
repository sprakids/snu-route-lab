"""A historical supply template and an independently switchable class-release treatment."""
import bisect
import hashlib
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROUTES = {'shuttle-41841':'41841', 'shuttle-daehak':'41843'}
# Nearest preceding complete archived school week. Monday's partial archive
# has no completed visits. Tuesday provides a weekday proxy for Monday.
TEMPLATE = dict(zip('월화수목금', (17, 17, 18, 19, 20)))
SECONDS_PER_RIDER = 2.0  # Scenario, no directly timed sequence yet.

def return_template(day, rid, clocks, group_size):
    if rid not in ROUTES:
        return {}
    data = json.loads((HERE / 'return_samples.json').read_text(encoding='utf8'))
    visits = data[f'2026-11-{TEMPLATE[day]}']['visits']
    groups = defaultdict(list)
    for v in visits:
        if v['route'] != ROUTES[rid]:
            continue
        lo, hi = v['departure']
        dep, arr = (lo + hi) / 2, sum(v['arrival']) / 2
        # Extended parking is visible in the operator feed, but its boarding
        # status is unknown. Only transfer short, bounded visits to another day.
        if dep - arr > 30 * 60 or arr >= lo:
            continue
        i = bisect.bisect_left(clocks, dep)
        if not 0 < i < len(clocks):
            continue
        slot = min(clocks[i-1:i+1], key=lambda t: abs(dep-t))
        # Exclude uncertain mappings whose endpoint crosses a slot boundary.
        nearest = lambda stamp: min(clocks, key=lambda t:abs(stamp-t))
        if nearest(lo) != slot or nearest(hi) != slot:
            continue
        groups[slot].append((dep, dep-arr))
    result = {}
    for slot, times in groups.items():
        if len(times) > group_size(slot):
            continue
        common_dep = sum(t for t,_ in times) / len(times)
        result[slot] = (common_dep, sorted((dwell for _,dwell in times), reverse=True))
    return result

def spread_release(bundle, day, donors, timing):
    courses = timing.ref.ref.class_events(timing.ref.load(timing.ref.ref.COURSES))
    rows = bundle['prepared']['plans'][day]
    changed = {}
    for i, p in enumerate(rows):
        parent = donors.get(p[0], p[0])
        c = courses[(parent-1)//48]
        key = '/'.join((day, c['section_id'], str(c['building']), c['start'], c['end']))
        if timing.release(key):
            continue
        if key not in changed:
            changed[key] = 60 * timing.triangular(timing.uniform('ordinary-section/'+key), -5, 0, 5)
        start = p[4] + changed[key]
        h,m = map(int,c['start'].split(':'))
        assert (h*60+m)*60 <= start < 86400
        rows[i] = [*p[:4], start, *p[5:]]
    return len(changed)

def signature(bundle, day, include_time):
    digest = hashlib.sha256()
    for p in bundle['prepared']['plans'][day]:
        columns = [p[0], p[1], p[3], bundle['destination_keys'][str(p[0])], p[5], p[6]]
        if include_time:
            columns.append(p[4])
        digest.update(json.dumps(columns, separators=(',',':'), sort_keys=True).encode())
        digest.update(b'\n')
    return digest.hexdigest()
