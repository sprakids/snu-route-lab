"""Storage-outage mode: no Blob traffic and no pretend durable persistence.

Only public, keyless lookups use process-local counters and short-lived caches.
Keyed API calls stay blocked until a durable shared quota store is available.
"""
import copy
import threading
import time


class PersistenceUnavailable(RuntimeError):
    pass


class StoragePausedState:
    persistent = False
    position_updates_paused = True
    message = ('저장소 무료 한도로 기록 저장과 버스 위치 수집을 일시 중단했습니다. '
               '버스 도착정보·셔틀 실시간 조회·경로 비교는 계속 이용할 수 있습니다.')

    def __init__(self):
        self._lock = threading.RLock()
        self._cache = {}
        self._key_locks = {}
        self._counts = {}

    def info(self):
        return {'mode': 'storage_paused', 'persistent': False,
                'blob_access_enabled': False, 'counter_scope': 'process',
                'observations_available': False, 'message': self.message}

    def budget(self, day, service, limit):
        # Never reset a provider's shared daily quota to a per-instance counter.
        if service not in ('public_arrivals', 'busin_live'):
            return False
        with self._lock:
            self._counts = {k: v for k, v in self._counts.items() if k[0] == day}
            key = (day, service)
            count = self._counts.get(key, 0)
            if count >= limit:
                return False
            self._counts[key] = count + 1
            return True

    def used(self, day, service):
        # A process-local count must not be advertised as a team-wide daily count.
        return None

    def read(self, key):
        with self._lock:
            return copy.deepcopy(self._cache.get(key.removeprefix('cache-'), {})), None

    def cached(self, key, seconds, producer):
        with self._lock:
            lock = self._key_locks.setdefault(key, threading.RLock())
        with lock:
            with self._lock:
                doc = self._cache.get(key, {})
                if doc.get('expires_at', 0) > time.time():
                    return copy.deepcopy(doc['value'])
            value = producer()
            with self._lock:
                self._cache[key] = {'value': copy.deepcopy(value),
                                    'expires_at': time.time() + seconds}
            return value

    def observations(self):
        # The unavailable history is identified in API metadata, never called empty history.
        return []

    def add_observation(self, record):
        raise PersistenceUnavailable('저장소 연결 복구 전에는 이동 기록을 저장할 수 없습니다. 입력한 기록은 저장되지 않았습니다.')
