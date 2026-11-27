"""Fresh normal public searches, preserving HTML and exposed links/images."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import importlib.util,sys,json,re,urllib.request,hashlib
from html.parser import HTMLParser
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'traffic_results_2026-11-06/collect_council_search.py'
spec=importlib.util.spec_from_file_location('public_council_search',OLD)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.SOURCE=ROOT/'survey/sources';module.SOURCE.mkdir(parents=True,exist_ok=True)
terms=['교통총조사','총조사','교통총조사 결과','교통 분석','하교셔틀 만족도','교통 보고','교통 2024','캠퍼스관리과']
with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(module.fetch,terms))
(ROOT/'survey/search_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
posts={p['post_id']:p for r in results for p in r.get('posts',[])}
(ROOT/'survey/posts.json').write_text(json.dumps(list(posts.values()),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([{'query':r['query'],'posts':len(r.get('posts',[])),'error':r.get('error'),'count_text':r.get('result_count_text')} for r in results],ensure_ascii=False))
for pid,p in posts.items():print(pid,p['title'])

class Links(HTMLParser):
    def __init__(self):super().__init__();self.images=[];self.forms=[];self.links=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='img':self.images.append({k:a[k] for k in ('src','data-src','alt','srcset') if k in a})
        if tag=='form':self.forms.append(a)
        if tag=='a' and a.get('href'):self.links.append(a['href'])
extras=[]
for r in results:
    if r.get('error'):continue
    name='we_'+re.sub(r'[<>:"/\\|?*\s]+','_',r['query'])+'.html'
    source=module.SOURCE/name
    parser=Links();parser.feed(source.read_text(encoding='utf-8',errors='replace'))
    extras.append({'query':r['query'],'images':parser.images,'forms':parser.forms,
        'document_links':[x for x in parser.links if re.search(r'pdf|hwp|docx|xlsx|drive.google|docs.google|download|youtube|youtu.be',x,re.I)]})
(ROOT/'survey/exposed_media_and_links.json').write_text(json.dumps(extras,ensure_ascii=False,indent=2),encoding='utf-8')
print('Image/link inventories saved; survey not submitted and council not contacted.')
