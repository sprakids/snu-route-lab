"""Download only file IDs exposed by the public T-data catalogue, with receipts.

Raw archives and failed partial files are preserved; there are no silent retries.
No API key, browser cookie, login, or personal identifier is needed or logged.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent


def download(date):
    page = (ROOT / 'source_page.html').read_text(encoding='utf-8')
    files = {name: file_id for file_id, name in re.findall(
        r'<option value="(\d+)">(TAIMS_\d{8}\.zip)</option>', page)}
    name = f'TAIMS_{date}.zip'
    if name not in files:
        raise ValueError('Date is not present in the captured public catalogue')
    directory = ROOT / 'archives'
    directory.mkdir(exist_ok=True)
    final = directory / name
    receipt = directory / f'{name}.receipt.json'
    if final.exists():
        if receipt.exists() and json.loads(receipt.read_text(encoding='utf-8')).get('status') == 'complete':
            print(json.dumps({'date': date, 'status': 'cached'}, ensure_ascii=False), flush=True)
            return
        raise FileExistsError('An existing archive without a complete receipt must be reviewed')
    partial = directory / f'{name}.{datetime.now(timezone.utc).strftime("%H%M%S%f")}.partial'
    url = 'https://t-data.seoul.go.kr/dataprovide/download.do?id=' + files[name]
    meta = {'file_label_date': date, 'public_file_id': files[name], 'source_url': url,
            'catalogue_url': 'https://t-data.seoul.go.kr/dataprovide/trafficdataviewfile.do?data_id=20006',
            'status': 'started', 'authenticated': False, 'api_key_used': False,
            'automatic_retries': 0, 'started_at': datetime.now(timezone.utc).isoformat()}
    receipt.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    size = 0
    digest = hashlib.sha256()
    started = time.monotonic()
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'SNU-Route-Research/1.0',
                                                  'Referer': meta['catalogue_url']})
        with urllib.request.urlopen(req, timeout=45) as response, partial.open('xb') as output:
            meta['http_status'] = response.status
            meta['content_type'] = response.headers.get('Content-Type')
            expected = int(response.headers.get('Content-Length') or 0)
            meta['expected_bytes'] = expected
            if response.status != 200 or expected > 1_500_000_000:
                raise ValueError('Unexpected response or bounded download size exceeded')
            mark = 0
            while chunk := response.read(4 * 1024 * 1024):
                if size == 0 and not chunk.startswith(b'PK\x03\x04'):
                    raise ValueError('Response is not a ZIP archive')
                size += len(chunk)
                if size > 1_500_000_000:
                    raise ValueError('Bounded download size exceeded')
                output.write(chunk)
                digest.update(chunk)
                if size - mark >= 128 * 1024 * 1024:
                    mark = size
                    print(json.dumps({'date': date, 'downloaded_mib': round(size / 2**20, 1),
                                      'expected_mib': round(expected / 2**20, 1)}, ensure_ascii=False), flush=True)
        if expected and size != expected:
            raise ValueError('Content length mismatch')
        with zipfile.ZipFile(partial) as archive:
            members = [{'name': m.filename, 'bytes': m.file_size, 'compressed_bytes': m.compress_size,
                        'crc32': f'{m.CRC:08x}', 'compression': m.compress_type} for m in archive.infolist()]
        partial.rename(final)
        meta.update(status='complete', bytes=size, sha256=digest.hexdigest(), members=members,
                    elapsed_seconds=round(time.monotonic() - started, 2),
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    warning='File label date has not yet been checked against the dates inside the tables')
        receipt.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'date': date, 'status': 'complete', 'bytes': size, 'members': members}, ensure_ascii=False), flush=True)
    except Exception as error:
        meta.update(status='partial_error', received_bytes=size, error_class=type(error).__name__,
                    partial_file=partial.name, no_automatic_retry=True)
        receipt.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'date': date, 'status': 'partial_error', 'error_class': type(error).__name__}), flush=True)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', required=True)
    arguments = parser.parse_args()
    datetime.strptime(arguments.date, '%Y%m%d')
    download(arguments.date)
