"""Local integrated R map. The published viewer and its data are read-only dependencies."""
from argparse import ArgumentParser
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
PUBLIC = HERE.parents[1] / 'simulation_viewer_2026-11-07/public'
MODEL = HERE.parent
VERSION = 'R'+MODEL.name
PREVIOUS = MODEL.parent/'261124102753'
SHARED = {
    'bus-motion.js', 'snapshot-query.js', 'initial-clock.js', 'json-loader.js', 'mobile-lab.js',
    'graphs-v5.js', 'campus-theme.css', 'campus-theme.js', 'mobile-lab.css', 'viewer-v2.css',
    'viewer-v5.css', 'data/chart_reference_v1/legacy.json',
}


def resource(path, page_fetch=False):
    prefix='/'+VERSION+'/'
    versioned=path.startswith(prefix)
    if versioned:
        path=path[len(prefix)-1:]
    # A map tab opened before cutover still holds the prior JS and its in-memory
    # common data. Keep its unversioned replay fetches on the same generation.
    legacy=page_fetch and not versioned
    if path in ('/', '/index.html'):
        return HERE/'index.html', 'text/html', False
    if path in ('/viewer.js','/integrated.css'):
        return HERE/path[1:], None, False
    if path=='/model-guide':
        return HERE/'README.md', 'text/plain', False
    if path in ('/map-stats.json','/station-access.json'):
        if legacy and path=='/map-stats.json':
            return PREVIOUS/'local-map/map-stats.json.gz','application/json',True
        return HERE/(path[1:]+'.gz'), 'application/json', True
    if re.fullmatch(r'/viewer-data/(common|(regular|peak)-(mon|tue|wed|thu|fri))\.json',path):
        return (PREVIOUS if legacy else MODEL)/(path[1:]+'.gz'), 'application/json', True
    if path[1:] in SHARED or re.fullmatch(r'/(vendor|assets)/[\w./-]+',path):
        target=(PUBLIC/path[1:]).resolve()
        if target.is_relative_to(PUBLIC) and '..' not in path.split('/'):
            return target,None,False
    return None


class Handler(BaseHTTPRequestHandler):
    def reply(self, include_body):
        legacy_fetch=(self.headers.get('Sec-Fetch-Site')=='same-origin' and
                      self.headers.get('Sec-Fetch-Dest')=='empty' and
                      urlsplit(self.headers.get('Referer','')).path in ('/','/index.html','/viewer.js'))
        item=resource(urlsplit(self.path).path,legacy_fetch)
        if item is None or not item[0].is_file():
            self.send_error(404)
            return
        source, mime, packed=item
        mime=mime or mimetypes.guess_type(source.name)[0] or 'application/octet-stream'
        accepts_gzip=bool(re.search(r'(?:^|,)\s*gzip\s*(?:,|$)',self.headers.get('Accept-Encoding','')))
        self.send_response(200)
        self.send_header('Content-Type',mime+('; charset=utf-8' if mime.startswith('text/') or mime in ('application/json','application/javascript') else ''))
        self.send_header('Cache-Control','no-cache')
        if packed:
            self.send_header('Vary','Accept-Encoding, Referer, Sec-Fetch-Site, Sec-Fetch-Dest')
        if packed and accepts_gzip:
            self.send_header('Content-Encoding','gzip')
        if not packed or accepts_gzip:
            self.send_header('Content-Length',source.stat().st_size)
        self.end_headers()
        if include_body:
            reader=gzip.open if packed and not accepts_gzip else open
            try:
                with reader(source,'rb') as stream:
                    shutil.copyfileobj(stream,self.wfile)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
                pass

    def do_GET(self):
        self.reply(True)

    def do_HEAD(self):
        self.reply(False)


if __name__=='__main__':
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8794)
    port=parser.parse_args().port
    with ThreadingHTTPServer(('127.0.0.1',port),Handler) as httpd:
        print(f'http://127.0.0.1:{port}/',flush=True)
        httpd.serve_forever()
