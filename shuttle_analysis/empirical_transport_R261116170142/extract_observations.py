"""Reconstruct interval-censored passages from saved archives; no provider calls."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import gzip
import hashlib
import json
import math

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent
GATE = '120000029'
STATION = '120000150'
GATE_ROUTES = {'100100250', '100100251', '100100252', '100100263', '100100521'}


def clock(at):
    return datetime.fromtimestamp(at, KST)


def load_network():
    return json.loads((ROOT / 'baseline_app/data/network.json').read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


def campus_keys(network):
    # Geographic evaluation scope is frozen before the new-day labels are opened.
    # Direction is always route + ordered sequence, never just a stop name.
    return {(r['id'], s['seq']) for r in network['routes'] for s in r['stops']
            if s['id'] == GATE or (37.439 <= s['lat'] <= 37.4675 and 126.946 <= s['lon'] <= 126.973)}


def extract(path, day, network):
    stops = {(r['id'], s['seq']): s for r in network['routes'] for s in r['stops']}
    unique = {}
    route_polls = defaultdict(list)
    quality = Counter()
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        for line in stream:
            batch = json.loads(line)
            quality['batches'] += 1
            for rr in batch.get('route_records', []):
                if rr.get('route_id') and not rr.get('error'):
                    route_polls[rr['route_id']].append(rr.get('at', batch['at']))
            for v in batch.get('vehicles', []):
                quality['raw_rows'] += 1
                rid, vid, at = v.get('route_id'), v.get('id'), v.get('provided_at')
                try:
                    seq = int(v.get('section_order'))
                    captured = float(v.get('captured_at', batch['at']))
                    valid = (rid, seq) in stops and vid and isinstance(at, (int, float)) and math.isfinite(at)
                    valid = valid and clock(at).date().isoformat() == day and 0 <= captured - at <= 150
                except (TypeError, ValueError, OverflowError):
                    valid = False
                if not valid:
                    quality['invalid_or_stale_rows'] += 1
                    continue
                key = rid, vid, at
                if key in unique:
                    quality['repeated_provider_timestamp'] += 1
                    continue
                unique[key] = {**v, 'seq': seq, 'at': float(at), 'captured': captured}
    passages, grades = [], []
    progress, trip_number, visited, last_grade = {}, defaultdict(int), defaultdict(set), {}
    for (rid, vid, at), v in sorted(unique.items(), key=lambda kv: (kv[0][2], kv[0][0], kv[0][1])):
        key = rid, vid
        seq = v['seq']
        old = progress.get(key)
        if old and (seq < old['seq'] or at - old['at'] > 1800):
            trip_number[key] += 1
            quality['trip_resets'] += 1
        token = hashlib.sha256(f'{day}:{rid}:{vid}:{trip_number[key]}'.encode()).hexdigest()[:20]
        code = str(v.get('crowd_code'))
        grade = int(code) - 3 if code in ('3', '4', '5', '6') else None
        previous = last_grade.get(token)
        if grade is not None and (not previous or seq != previous['seq'] or at - previous['at'] >= 90):
            grades.append({'day': day, 'r': rid, 's': seq, 'at': at, 'seen': v['captured'],
                           'trip': token, 'grade': grade})
            last_grade[token] = {'seq': seq, 'at': at}
        if grade is None:
            quality['unknown_grade_rows'] += 1
        stop = stops[(rid, seq)]
        distance = math.hypot((v['lon'] - stop['lon']) * math.cos(math.radians(v['lat'])) * 111195,
                              (v['lat'] - stop['lat']) * 111195)
        prior = v.get('previous_observation') or {}
        gap = at - (prior.get('provided_at') or 0)
        if distance <= 60 and not v.get('at_stop'):
            quality['near_stop_without_stop_flag_rows'] += 1
        if v.get('at_stop') and distance <= 60 and 0 < gap <= 120 and seq not in visited[token]:
            full = v.get('full') if v.get('full_known') is True and type(v.get('full')) is bool else None
            passages.append({'day': day, 'r': rid, 's': seq, 'at': at, 'seen': v['captured'],
                             'trip': token, 'grade': grade, 'full': full, 'detection_gap': gap,
                             'stop_id': stop.get('id'), 'evidence_type': 'stop_flag_within_60m'})
            visited[token].add(seq)
        progress[key] = {'seq': seq, 'at': at}
    quality['unique_provider_rows'] = len(unique)
    quality['confirmed_stop_events'] = len(passages)
    quality['grade_records'] = len(grades)
    quality['route_poll_coverage'] = {r: {'responses': len(xs),
        'maximum_gap_seconds': max((b-a for a, b in zip(sorted(set(xs)), sorted(set(xs))[1:])), default=None)}
        for r, xs in route_polls.items()}
    return {'day': day, 'source_sha256': digest(path), 'quality': dict(quality),
            'passages': passages, 'grades': grades}


def intervals(events, minimum=15):
    result = []
    for a, b in zip(sorted(events, key=lambda x: x['at']), sorted(events, key=lambda x: x['at'])[1:]):
        gap = b['at'] - a['at']
        if a['trip'] != b['trip'] and minimum <= gap <= 3600:
            result.append({'day': a['day'], 'r': b['r'], 's': b['s'], 'at': a['at'],
                           'end': b['at'], 'h': clock(a['at']).hour, 'seconds': gap,
                           'trip': b['trip']})
    return result


def derive(extracted, network):
    by_stop, by_trip, grade_trips = defaultdict(list), defaultdict(list), defaultdict(list)
    for x in extracted['passages']:
        by_stop[(x['r'], x['s'])].append(x)
        by_trip[x['trip']].append(x)
    for x in extracted['grades']:
        grade_trips[x['trip']].append(x)
    heads = [x for events in by_stop.values() for x in intervals(events)]
    rides = []
    stops = {(r['id'], s['seq']): s for r in network['routes'] for s in r['stops']}
    for events in by_trip.values():
        events.sort(key=lambda x: x['at'])
        for i, a in enumerate(events):
            for b in events[i+1:]:
                seconds = b['at'] - a['at']
                if not (0 < b['s'] - a['s'] <= 12 and 0 < seconds <= 1800):
                    continue
                p, q = stops[(a['r'], a['s'])], stops[(b['r'], b['s'])]
                lower = math.hypot((p['lat']-q['lat'])*111195,
                                  (p['lon']-q['lon'])*111195*math.cos(math.radians(p['lat']))) / (100/3.6)
                if seconds >= lower:
                    rides.append({'day': a['day'], 'r': a['r'], 'a': a['s'], 'b': b['s'],
                                  'h': clock(a['at']).hour, 'at': a['at'], 'end': b['at'],
                                  'known_at': b['seen'], 'seconds': seconds, 'trip': a['trip'],
                                  'measurement_interval_seconds': [max(0., seconds-b['detection_gap']), seconds+a['detection_gap']],
                                  'detection_uncertainty_seconds': a['detection_gap'] + b['detection_gap']})
    transitions, persistence = [], []
    for events in grade_trips.values():
        events.sort(key=lambda x: x['at'])
        # One target per trip/section, even if it was polled many times.
        seen_targets = set()
        for i, target in enumerate(events):
            if target['s'] in seen_targets:
                continue
            seen_targets.add(target['s'])
            for bucket, lo, hi in [(0, 90, 180), (1, 180, 360), (2, 360, 601)]:
                candidates = [p for p in events[:i] if lo <= target['at']-p['at'] < hi
                              and 0 <= target['s']-p['s'] <= 8]
                if not candidates:
                    continue
                source = min(candidates, key=lambda p: abs(target['at']-p['at']-(lo+hi)/2))
                transitions.append({'day': target['day'], 'r': target['r'], 'a': source['s'], 'b': target['s'],
                                    'h': clock(target['at']).hour, 'at': target['at'], 'trip': target['trip'],
                                    'age': target['at']-source['at'], 'bucket': bucket,
                                    'g0': source['grade'], 'g1': target['grade'],
                                    'source_at': source['at'], 'source_seen': source['seen']})
        run = None
        previous = None
        for x in events:
            if previous and x['at']-previous['at'] > 180:
                if run:
                    persistence.append({**run, 'seconds': previous['at']-run['at'], 'censored': True})
                run = None
            if x['grade'] >= 2 and run is None:
                run = {'r': x['r'], 's': x['s'], 'at': x['at'], 'day': x['day'], 'trip': x['trip']}
            if run and x['grade'] < 2:
                persistence.append({**run, 'seconds': x['at']-run['at'], 'censored': False})
                run = None
            previous = x
        if run:
            persistence.append({**run, 'seconds': previous['at']-run['at'], 'censored': True})
    eligible = {}
    for r in network['routes']:
        if r['id'] not in GATE_ROUTES:
            continue
        for s in r['stops']:
            if s['id'] == GATE and any(t['id'] == STATION and t['seq'] > s['seq'] for t in r['stops']):
                eligible[r['id']] = s['seq']
    gate = [p for p in extracted['passages'] if eligible.get(p['r']) == p['s']]
    return {'headways': heads, 'rides': rides, 'transitions': transitions,
            'persistence': persistence, 'gate_events': sorted(gate, key=lambda x: (x['at'], x['r'])),
            'quality': extracted['quality'], 'day': extracted['day'],
            'source_sha256': extracted['source_sha256']}
