"""Follow public council search pagination exposed by the normal HTML UI."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import urllib.request, urllib.parse, hashlib, json, importlib.util, sys, re
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('council_parser', ROOT.parent/'traffic_results_2026-11-06/collect_council_search.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
OUT = ROOT/'survey/pagination'; OUT.mkdir(exist_ok=True)
def fetch(n):
    url = 'https://we.snu.ac.kr/?'+urllib.parse.urlencode({'var_page':n,'s':'총조사'})
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=30) as r:
        data=r.read(); status=r.status
    (OUT/f'total_survey_page_{n}.html').write_bytes(data)
    parser=module.PublicSearch(); parser.feed(data.decode('utf-8','replace'))
    (OUT/f'total_survey_page_{n}.txt').write_text('\n'.join(parser.parts),encoding='utf-8')
    posts=[]
    for x in parser.links:
        m=re.search(r'[?&]p=(\d+)',x['url'])
        if m and 'subject' in x['class'].split():
            same=[a['text'].strip() for a in parser.links if a['url']==x['url']]
            posts.append({'post_id':m[1],'url':x['url'],'title':x['text'].strip(),'text':max(same,key=len)})
    return {'url':url,'page':n,'http_status':status,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'captured_at_utc':datetime.now(timezone.utc).isoformat(),'posts':posts}
with ThreadPoolExecutor(max_workers=3) as pool:
    rows=list(pool.map(fetch,range(2,7)))
(OUT/'search_pages.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
for r in rows:
    print('PAGE',r['page'],'POSTS',len(r['posts']))
    for p in r['posts']:print(p['post_id'],p['title'])
