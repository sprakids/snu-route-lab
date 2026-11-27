"""Save public SNU notices and their ordinary download links in the same session."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from html import unescape
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import build_opener, HTTPCookieProcessor, Request
import hashlib
import json

ROOT = Path(__file__).resolve().parent
(ROOT / 'sources').mkdir(exist_ok=True)
DOCS = [
    ('O11', 4641, '2026학년도 2학기 셔틀버스 운행 안내'),
    ('O12', 4645, '2026학년도 2학기 셔틀버스 증차 운행 안내'),
    ('O13', 4544, '신공학관 하교 셔틀 노선 한시적 운행 종료 안내'),
    ('O14', 4539, '시내버스 대학동 방면 단축에 따른 한시적 셔틀 연장'),
    ('O15', 4580, '대학동 방면 셔틀버스 노선 연장 운행 종료 안내'),
]

class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.downloads = []
        self.parts = []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag in {'script', 'style', 'svg', 'noscript'}:
            self.skip += 1
        if tag == 'a' and 'download.php' in data.get('href', ''):
            self.downloads.append(data['href'])
        if not self.skip and tag in {'p', 'div', 'tr', 'br', 'h1', 'h2', 'h3', 'li'}:
            self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'svg', 'noscript'} and self.skip:
            self.skip -= 1
        if not self.skip and tag in {'p', 'div', 'tr', 'h1', 'h2', 'h3', 'li'}:
            self.parts.append('\n')
    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

def fetch_doc(doc):
    key, number, title = doc
    url = f'https://cuee.snu.ac.kr/bbs/board.php?bo_table=sub5_1&wr_id={number}'
    row = {'id': key, 'title': title, 'url': url, 'captured_at': datetime.now(timezone(timedelta(hours=9))).isoformat(), 'files': []}
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    def get(target):
        with opener.open(Request(target, headers={'User-Agent': 'Mozilla/5.0', 'Referer': url}), timeout=25) as response:
            return response.read()
    def save(data, name):
        path = ROOT / 'sources' / name
        path.write_bytes(data)
        return {'file': 'sources/' + name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    try:
        data = get(url)
        row['files'].append(save(data, key + '.html'))
        parser = Page()
        parser.feed(data.decode('utf-8', 'replace'))
        cleaned = '\n'.join(line for raw in ''.join(parser.parts).splitlines() if (line := ' '.join(raw.split())))
        (ROOT / 'sources' / (key + '.txt')).write_text(cleaned, encoding='utf-8')
        row['downloads'] = []
        for index, link in enumerate(dict.fromkeys(parser.downloads)):
            target = urljoin(url, unescape(link)).replace('|', '%7C')
            item = {'index': index, 'url': target}
            try:
                content = get(target)
                if content.startswith(b'%PDF'):
                    item.update(save(content, f'{key}_{index + 1}.pdf'))
                else:
                    item['error'] = 'Download returned non-PDF; no access restriction bypass attempted.'
            except Exception as error:
                item['error'] = str(error)
            row['downloads'].append(item)
    except Exception as error:
        row['error'] = str(error)
    return row

if __name__ == '__main__':
    rows = list(ThreadPoolExecutor(max_workers=4).map(fetch_doc, DOCS))
    (ROOT / 'official_capture_manifest.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    for row in rows:
        print(json.dumps({'id': row['id'], 'title': row['title'], 'error': row.get('error'), 'downloads': [{k: v for k, v in x.items() if k != 'url'} for x in row.get('downloads', [])]}, ensure_ascii=False))
