"""Read-only public-source acquisition. No simulation inputs are changed."""
import concurrent.futures
import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / 'sources'
SOURCES.mkdir(exist_ok=True)
URLS = {
    'W01_vision': 'https://www.snu.ac.kr/webdata/uploads/kor/file/2020/02/26th_vision_change.pdf',
    'W02_news31753': 'https://www.snunews.com/news/articleView.html?idxno=31753',
    'W03_news32053': 'https://www.snunews.com/news/articleView.html?idxno=32053',
    'W04_news34963': 'https://www.snunews.com/news/articleView.html?idxno=34963',
    'W05_news35150': 'https://www.snunews.com/news/articleView.html?idxno=35150',
    'W06_satisfaction2019': 'https://needs.snu.ac.kr/api/pdf/' + urllib.parse.quote('2019년도 서울대학교 교육수요자 만족도 조사 보고서(학부)_최종_1716356853250.pdf'),
    'W07_news31457': 'https://www.snunews.com/news/articleView.html?idxno=31457',
    'W08_snunews_search': 'https://www.snunews.com/news/articleList.html?' + urllib.parse.urlencode({'sc_word':'셔틀','sc_area':'A','view_type':'sm'}),
}

def textify(raw):
    raw = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', raw, flags=re.S|re.I)
    raw = re.sub(r'</(?:p|div|li|h[1-6]|tr)>|<br\s*/?>', '\n', raw, flags=re.I)
    raw = re.sub('<[^>]+>', ' ', raw)
    return '\n'.join(re.sub(r'\s+', ' ', html.unescape(s)).strip() for s in raw.splitlines() if s.strip())

def fetch(item):
    key, url = item
    meta = {'id':key,'url':url,'accessed_date':'2026-11-07'}
    try:
        ext = '.pdf' if '.pdf' in url else '.html'
        path = SOURCES / (key + ext)
        if not path.exists():
            with urllib.request.urlopen(url, timeout=45) as r:
                data = r.read()
                meta.update(status=r.status,final_url=r.url)
            path.write_bytes(data)
        data=path.read_bytes()
        meta.update(file=path.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        if ext == '.pdf':
            reader=PdfReader(path)
            pages=[p.extract_text() or '' for p in reader.pages]
            text='\n\n'.join(f'--- PDF PAGE {i+1} ---\n{t}' for i,t in enumerate(pages))
            meta['pages']=len(pages)
            meta['matching_pages']=[i+1 for i,t in enumerate(pages) if re.search('대기시간|대기 시간|기다리|기다렸', t)]
            (SOURCES/(key+'_pages.json')).write_text(json.dumps(pages,ensure_ascii=False),encoding='utf-8')
        else:
            raw=data.decode('utf-8',errors='replace')
            text=textify(raw)
            m=re.search(r'<article[^>]*id="article-view-content-div"[^>]*>(.*?)</article>',raw,re.S)
            if m: text=textify(m.group(1))
        (SOURCES/(key+'.txt')).write_text(text,encoding='utf-8')
        matches=list(re.finditer('대기시간|대기 시간|기다리|기다렸',text))
        meta['snippets']=[text[max(0,m.start()-90):m.end()+180].replace('\n',' ') for m in matches[:30]]
    except Exception as e:
        meta['error']=f'{type(e).__name__}: {e}'
    return meta

if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results=list(pool.map(fetch,URLS.items()))
    (ROOT/'download_manifest.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    for r in results:
        print(r['id'],r.get('bytes'),r.get('pages'),r.get('matching_pages'),r.get('error',''))
        if not r['id'].endswith('search'):
            for s in r.get('snippets',[])[:12]:print(s)
