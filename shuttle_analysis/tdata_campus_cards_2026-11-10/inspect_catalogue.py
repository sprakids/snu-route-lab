"""Inspect dates in the first small reference table without downloading citywide trips."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from collections import Counter
import csv
import io
import json
import re
import struct
import urllib.request
import zlib

ROOT = Path(__file__).resolve().parent


def inspect(entry):
    file_id, label_date = entry
    url = 'https://t-data.seoul.go.kr/dataprovide/download.do?id=' + file_id
    result = {'file_id': file_id, 'file_label_date': label_date, 'url': url}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={
                'User-Agent': 'SNU-Route-Research/1.0'}), timeout=30) as response:
            header = response.read(30)
            sig, version, flags, method, mtime, mdate, crc, csize, usize, nlen, xlen = struct.unpack('<IHHHHHIIIHH', header)
            if sig != 0x04034b50 or flags & 8:
                raise ValueError('Unexpected first ZIP entry')
            name = response.read(nlen).decode('utf-8')
            response.read(xlen)
            if not name.startswith('VW_KSCC_') or not name.endswith('.csv'):
                raise ValueError('First ZIP entry is not a known transport table')
            compressed = response.read(min(csize, 65536))
            raw = zlib.decompressobj(-15).decompress(compressed, 512000) if method == 8 else compressed
            if csize <= 65536:
                if zlib.crc32(raw) & 0xffffffff != crc:
                    raise ValueError('Reference CRC mismatch')
            else:
                raw = raw[:raw.rfind(b'\n')+1]
            rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig',errors='replace'))))[:100]
            dates = Counter(row['STDR_DE'] for row in rows)
            result.update(status='inspected', zip_bytes=int(response.headers.get('Content-Length') or 0),
                          reference_member=name, reference_dates=dict(dates), sampled_rows=len(rows),
                          downloaded_reference_bytes=30+nlen+xlen+len(compressed),
                          note='First-table sample only; every selected trip row date is checked during extraction')
    except Exception as error:
        result.update(status='error', error_class=type(error).__name__, automatic_retries=0)
    return result


if __name__ == '__main__':
    page = (ROOT/'source_page.html').read_text(encoding='utf-8')
    entries = [(file_id, date) for file_id, date in re.findall(
        r'<option value="(\d+)">TAIMS_(\d{8})\.zip</option>', page)
        if '20261013' <= date <= '20261110']
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(inspect, entries))
    payload = {'captured_at': datetime.now(timezone.utc).isoformat(),
               'requested_event_dates': ['20261013', '20261109'], 'archives': results}
    (ROOT/'catalogue_manifest_v2.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    for row in results:
        print(json.dumps({k: row.get(k) for k in ['file_label_date','reference_dates','zip_bytes','status','error_class']},ensure_ascii=False),flush=True)
