"""Extract anonymous terminal visit intervals from archived operator position polls."""
import gzip
import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'return_dwell_review_2026-11-24'))
from return_windows import TERMINALS, episodes

# Prior weekdays, ending before the November 23–25 field observations.
TRAIN_DAYS = [f'2026-11-{n}' for n in (16, 17, 18, 19, 20)]

def read_day(day, credentials):
    origin = credentials['url']
    assert (urlsplit(origin).scheme, urlsplit(origin).hostname) == (
        'https', 'snu-route-collector.touchline-atlas-june.workers.dev')
    req = Request(origin + '/shuttle/export?day=' + day,
                  headers={'Authorization': 'Bearer ' + credentials['token'], 'User-Agent':'SNU-Route-Lab/0.4'})
    with urlopen(req, timeout=45) as response:
        raw = response.read()
    midnight = datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=9))).timestamp()
    polls = defaultdict(dict)
    for line in gzip.decompress(raw).splitlines():
        for item in json.loads(line)['routes']:
            route, value = item['route'], item.get('value') or {}
            if route not in TERMINALS or 'captured_at' not in value:
                continue
            t = round(value['captured_at'] - midnight, 3)
            if not 0 <= t < 86400:
                continue
            positions = {}
            for v in value.get('vehicles', []):
                p = v.get('position') or {}
                if p.get('segment_index') is not None:
                    positions[v['id']] = [p['segment_index'], p.get('at_stop_index') if p.get('at_stop') else None]
            polls[route][t] = positions
    retained = []
    for route, rows in polls.items():
        for v in episodes(sorted(rows.items()), route):
            if v['previous_other_terminal'] is not None and v['arrival'][1] < v['departure'][0]:
                retained.append(dict(day=day, route=route, arrival=v['arrival'], departure=v['departure']))
    return dict(sha256=hashlib.sha256(raw).hexdigest(),
                polls={r:len(rows) for r,rows in polls.items()}, visits=retained)

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--validation',action='store_true')
    args=parser.parse_args()
    sys.path.insert(0, str(HERE.parent / 'collector'))
    from export_history import credentials
    creds = credentials()
    dates=['2026-11-23','2026-11-24'] if args.validation else TRAIN_DAYS
    data = {day:read_day(day, creds) for day in dates}
    dest='validation_samples.json' if args.validation else 'return_samples.json'
    (HERE / dest).write_text(json.dumps(data, indent=2) + '\n', encoding='utf8')
    print({d:(v['polls'], len(v['visits'])) for d,v in data.items()})
