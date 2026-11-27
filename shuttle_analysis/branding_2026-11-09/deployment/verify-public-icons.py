"""Anonymous public-site checks after promoting the tested deployment."""
import concurrent.futures,datetime,hashlib,json,urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parent
PUBLIC=ROOT.parents[1]/'app/public'
BASE='https://snu-route-lab.vercel.app'
class Markup(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self.images=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='link':self.links.append(attrs)
        if tag=='img' and 'brand-icon-image' in attrs.get('class',''):self.images.append(attrs)
def fetch(path):
    req=urllib.request.Request(BASE+path,headers={'User-Agent':'SNU-Route-Lab/icon-verification'})
    with urllib.request.urlopen(req,timeout=25) as r:return r.read(),r.headers.get('Content-Type',''),r.status
paths=set();pages=[]
for path in ['/', '/privacy.html','/accessibility.html']:
    raw,mime,status=fetch(path);p=Markup();p.feed(raw.decode('utf-8'))
    assert status==200 and p.images
    assert all(i['src']=='/icons/hagyogil-v2-96.png' for i in p.images)
    relevant=[l for l in p.links if l.get('rel') in ('icon','apple-touch-icon','manifest') or l.get('href','').startswith('/brand.css?')]
    assert any(l['href'].startswith('/brand.css?v=') for l in relevant)
    assert any(l.get('rel')=='apple-touch-icon' for l in relevant)
    assert any(l.get('rel')=='manifest' for l in relevant)
    paths.update(l['href'] for l in relevant);paths.update(i['src'] for i in p.images)
    pages.append({'path':path,'status':status,'brand_images':len(p.images)})
manifest,_,_=fetch('/site-v2.webmanifest')
paths.update(i['src'] for i in json.loads(manifest)['icons'])
paths.update(['/favicon.ico','/icon.svg'])
def check(path):
    raw,mime,status=fetch(path);local=PUBLIC/urlsplit(path).path.lstrip('/')
    assert status==200 and raw==local.read_bytes(),path
    if path.endswith('.webmanifest'):assert 'manifest+json' in mime,mime
    if '.png' in path:assert mime.startswith('image/png'),mime
    return {'path':path,'status':status,'bytes':len(raw),'content_type':mime,'sha256':hashlib.sha256(raw).hexdigest()}
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:assets=list(pool.map(check,sorted(paths)))
health,_,_=fetch('/api/health');assert json.loads(health)['ok']
result={'checked_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(),
    'url':BASE,'deployment_id':'dpl_E5xxkXDwJCPHjYGwju9dxFnNCzES','anonymous_access':True,
    'pages':pages,'assets':assets,'health_ok':True,'build_tests_passed':5,
    'home_screen_note':'Manifest and touch icon references and image delivery checked; physical-device installation not exercised.'}
(ROOT/'public-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':'PASS','pages':len(pages),'assets':len(assets),'health':True,'url':BASE},ensure_ascii=True))
