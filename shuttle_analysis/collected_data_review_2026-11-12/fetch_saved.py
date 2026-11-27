"""Read saved collector data only; no live provider polls or control mutations."""
import concurrent.futures as futures
import datetime as dt
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'app'))
import server

KST = dt.timezone(dt.timedelta(hours=9))

def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def credentials():
    path = Path(os.environ['LOCALAPPDATA']) / 'SnuTransit/credentials/collector_backend.dpapi'
    return json.loads(server.crypt(path.read_bytes(), decrypt=True))

def fetch(c, endpoint):
    # Native curl has a total deadline and avoids observed urllib TLS/read stalls.
    # Authentication is passed privately on stdin, not in command arguments/logs.
    config = ('url="' + c['url'] + endpoint + '"\n'
              'header="Authorization: Bearer ' + c['token'] + '"\n'
              'user-agent="SNU-Route-Lab/0.4"\n')
    result = subprocess.run(['curl.exe','--config','-','--silent','--show-error',
        '--fail','--max-time','90','--connect-timeout','15'], input=config.encode(),
        capture_output=True, timeout=95)
    if result.returncode:
        raise RuntimeError('saved_endpoint_read_failed:' + endpoint + ':' + str(result.returncode))
    return result.stdout

def main():
    c = credentials()
    status_path = ROOT / 'source_status.json'
    status = json.loads(status_path.read_text(encoding='utf-8')) if status_path.exists() else json.loads(fetch(c, '/status'))
    if not status_path.exists():dump(status_path, status)
    today = dt.datetime.fromtimestamp(status['server_time'], KST).date()
    days = [(today - dt.timedelta(days=i)).isoformat() for i in range(35, -1, -1)]
    def get_day(day):
        saved = ROOT / 'recording' / (day + '.json')
        if saved.exists():
            return json.loads(saved.read_text(encoding='utf-8'))
        value = json.loads(fetch(c, '/recording?day=' + day))
        dump(ROOT / 'recording' / (day + '.json'), value)
        return value
    with futures.ThreadPoolExecutor(max_workers=3) as pool:
        recordings = list(pool.map(get_day, days))
    occupied = [r for r in recordings if r.get('routes')]
    dump(ROOT / 'recording_index.json', recordings)
    print(json.dumps({'saved_dates': [{
        'day': r['day'], 'routes': len(r['routes']),
        'grade_observations': sum(x['grade_observations'] for x in r['routes']),
        'full_known': sum(x['known_full_flag_observations'] for x in r['routes']),
        'headways': sum(x['observed_stop_headways'] for x in r['routes'])
    } for r in occupied]}, ensure_ascii=False), flush=True)
    manifest = []
    def export_day(r):
        day = r['day']
        aggregate_path = ROOT / 'aggregates' / (day + '.json')
        if aggregate_path.exists():
            aggregate = json.loads(aggregate_path.read_text(encoding='utf-8'))
        else:
            aggregate = json.loads(fetch(c, '/aggregate?day=' + day))
            dump(aggregate_path, aggregate)
        item = {'day': day, 'aggregate_rows': len(aggregate.get('rows', []))}
        try:
            folder = ROOT / 'raw'
            folder.mkdir(exist_ok=True)
            raw_path = folder / (day + '.jsons.gz')
            data = raw_path.read_bytes() if raw_path.exists() else fetch(c, '/export?day=' + day)
            if not raw_path.exists():raw_path.write_bytes(data)
            raw = gzip.decompress(data)
            item.update(compressed_bytes=len(data), uncompressed_bytes=len(raw),
                        sha256=hashlib.sha256(data).hexdigest(), lines=len(raw.splitlines()))
        except urllib.error.HTTPError as error:
            item['export_http_status'] = error.code
        return item
    with futures.ThreadPoolExecutor(max_workers=2) as pool:
        for item in pool.map(export_day, occupied):
            manifest.append(item)
            print(json.dumps(item), flush=True)
    dump(ROOT / 'download_manifest.json', {'retrieved_at': dt.datetime.now(KST).isoformat(),
         'source': 'authenticated Cloudflare collector saved recording/aggregate/export endpoints',
         'provider_calls_triggered': 0, 'date_discovery_window': [days[0], days[-1]],
         'days': manifest})
    observations = json.loads(fetch(c, '/observations'))
    dump(ROOT / 'saved_trip_observations.json', observations)
    print('trip_observation_records', len(observations.get('records', [])), flush=True)

if __name__ == '__main__':
    main()
