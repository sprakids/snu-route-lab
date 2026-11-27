"""Bounded causal warm-worker memory; no network calls, disk or quota writes."""
from collections import deque
import hashlib
import math


class TransportHistory:
    def __init__(self, routes, limit=10000):
        self.stops = {(r['id'], s['seq']): s for r in routes if not r['id'].startswith('shuttle') for s in r['stops']}
        self.passages = deque(maxlen=limit)
        self.travel = deque(maxlen=limit)
        self.progress, self.visited = {}, {}
        self.last_snapshot = None

    def update(self, snapshot, asof):
        if not isinstance(snapshot, dict):
            return
        stamp = snapshot.get('captured_at', snapshot.get('at'))
        if stamp is not None and (not isinstance(stamp, (int, float)) or not math.isfinite(stamp) or stamp > asof):
            return
        if stamp is not None and stamp == self.last_snapshot:
            return
        self.last_snapshot = stamp
        for v in sorted(snapshot.get('vehicles', []), key=lambda x: x.get('provided_at') or 0):
            try:
                rid, vid, at = v['route_id'], v['id'], float(v['provided_at'])
                seq = int(v['section_order']);seen = float(v.get('captured_at', stamp if stamp is not None else asof))
                if not (math.isfinite(at) and math.isfinite(seen) and 0 <= seen-at <= 150 and at <= seen <= asof):
                    continue
                stop = self.stops.get((rid, seq))
                if stop is None:
                    continue
                key = rid, vid
                old = self.progress.get(key)
                if old and at <= old['at']:
                    continue
                reset = bool(old and (seq < old['seq'] or at-old['at'] > 1800))
                generation = (old['generation']+int(reset)) if old else 0
                token = hashlib.sha256(f'{rid}:{vid}:{generation}'.encode()).hexdigest()[:20]
                self.progress[key] = {'at': at, 'seq': seq, 'generation': generation}
                prior = v.get('previous_observation') or {}
                gap = at-float(prior.get('provided_at') or 0)
                distance = math.hypot((float(v['lat'])-stop['lat'])*111195,
                                      (float(v['lon'])-stop['lon'])*111195*math.cos(math.radians(float(v['lat']))))
                if not (v.get('at_stop') and distance <= 60 and 0 < gap <= 120):
                    continue
                previous = self.visited.setdefault(token, {})
                if seq in previous:
                    continue
                full = v.get('full') if v.get('full_known') is True and type(v.get('full')) is bool else None
                event = {'r': rid, 's': seq, 'stop_id': stop['id'], 'at': at, 'seen': seen, 'trip': token, 'full': full}
                for a, p in previous.items():
                    seconds = at-p['at']
                    if 0 < seq-a <= 12 and 0 < seconds <= 1800:
                        self.travel.append({'r': rid, 'a': a, 'b': seq, 'at': p['at'], 'end': at,
                                            'known_at': seen, 'seconds': seconds, 'trip': token})
                self.passages.append(event);previous[seq] = event
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        # Memory bounded in both duration and row count, including vehicle maps.
        while self.passages and self.passages[0]['seen'] < asof-7200:
            self.passages.popleft()
        while self.travel and self.travel[0]['known_at'] < asof-7200:
            self.travel.popleft()
        self.progress = {k: p for k, p in self.progress.items() if p['at'] >= asof-7200}
        self.visited = {k: p for k, p in self.visited.items() if p and max(x['at'] for x in p.values()) >= asof-7200}


def history_rows(transit, live=True):
    memory = getattr(transit, '_transport_history', None)
    if memory is not None and live:
        memory.update(getattr(transit, 'plan_snapshot', getattr(transit, 'snapshot', {})), transit.now())
    passages = list(getattr(transit, 'observed_stop_events', ())) if live else []
    travel = list(getattr(transit, 'completed_trip_segments', ())) if live else []
    if memory is not None and live:
        passages += list(memory.passages);travel += list(memory.travel)
    return passages, travel
