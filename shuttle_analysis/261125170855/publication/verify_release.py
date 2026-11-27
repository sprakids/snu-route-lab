"""Check the actual static responses and the independently running recommendation API."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
from http.cookiejar import MozillaCookieJar
import json
from pathlib import Path
import subprocess
from urllib.request import build_opener, HTTPCookieProcessor, Request

HERE=Path(__file__).resolve().parent


def verify(origin, phase, cookies, require_terminal_wait=False):
    expected=json.loads((HERE/'expected.json').read_text(encoding='utf8'))
    model=expected['model']
    old=json.loads((HERE.parent/'v11_comparison/비교결과.json').read_text(encoding='utf8'))['production']['manifest']

    def fetch(url):
        if cookies:
            jar=MozillaCookieJar(str(cookies))
            jar.load(ignore_discard=True)
            opener=build_opener(HTTPCookieProcessor(jar))
        else:
            opener=build_opener()
        with opener.open(Request(url,headers={'Accept-Encoding':'identity','User-Agent':'SNU-Route-Lab/0.4'}),timeout=35) as r:
            assert r.status==200, (url,r.status)
            raw=r.read()
            encoding=r.headers.get('Content-Encoding','identity')
            if encoding=='gzip':
                raw=gzip.decompress(raw)
            elif encoding=='br':
                script="process.stdout.write(require('node:zlib').brotliDecompressSync(require('node:fs').readFileSync(0)))"
                raw=subprocess.run(['node','-e',script],input=raw,stdout=subprocess.PIPE,check=True).stdout
            else:
                assert encoding=='identity', (url,encoding)
            return raw, r.geturl()

    def digest(path):
        return hashlib.sha256(fetch(origin+path)[0]).hexdigest()
    def asset(item):
        path,want=item
        assert digest('/'+model+'/'+path)==want,path
        return path
    with ThreadPoolExecutor(max_workers=4) as pool:
        verified=list(pool.map(asset,expected['decoded_sha256'].items()))
    for path in ('/','/city.html','/index.html','/'+model+'/'):
        assert digest(path)==expected['public_html_sha256'],path
    legacy,legacy_url=fetch(origin+'/?dataset=corrected_supply_v1&day=tue&minute=923')
    assert '/v11.html' in legacy_url and b'viewer-v5.js' in legacy
    guide=fetch(origin+'/model-guide.html')[0]
    assert model.encode() in guide and b'V12' in guide
    for alias in ('/V12','/'+expected['research_id']+'/'):
        page,url=fetch(origin+alias+'?day=tue&minute=923')
        assert model in url and 'minute=923' in url and hashlib.sha256(page).hexdigest()==expected['public_html_sha256'],url
    history=json.loads((HERE/'history'/expected['research_id']/'expected.json').read_bytes())
    for path,sha in history['decoded_sha256'].items():
        if path.startswith(('viewer-data/regular-', 'viewer-data/peak-')):
            assert expected['decoded_sha256'][path]==sha
    assert digest('/'+expected['research_id']+'/viewer-data/common.json')==history['decoded_sha256']['viewer-data/common.json']
    assert b'V12' in fetch(origin+'/methodology.md')[0]
    manifest=json.loads(fetch(origin+'/routing-model/latest.json')[0])
    assert manifest==old
    assert digest(manifest['payload_path'])==manifest['sha256']
    status=json.loads(fetch('https://snu-route-lab.vercel.app/api/queue-model')[0])
    assert status['model_id']==status['sync']['active_model_id']==manifest['model_id']
    assert status['sync']['status']=='active' and status['sync']['payload_sha256']==manifest['sha256']
    terminal=status.get('terminal_wait', {})
    if require_terminal_wait:
        assert terminal.get('release')==model and terminal.get('status')=='active',terminal
        assert terminal['sha256']==expected['decoded_sha256']['routing-feed.json']
    out=dict(phase=phase,origin=origin,verified_at=datetime.now(timezone.utc).isoformat(),
             current_map=model,family=expected['family'],decoded_assets=verified,verified_html_entries=4,legacy_explicit_link=True,
             routing_base_model=manifest['model_id'],base_payload_sha256=manifest['sha256'],base_sync='active',
             routing_terminal_wait=terminal,
             authenticated_map_requests=bool(cookies))
    (HERE/(phase+'_http.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(out))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('origin');p.add_argument('phase',choices=['staged','live'])
    p.add_argument('--cookies',type=Path)
    p.add_argument('--require-terminal-wait',action='store_true')
    a=p.parse_args()
    verify(a.origin.rstrip('/'),a.phase,a.cookies,a.require_terminal_wait)
