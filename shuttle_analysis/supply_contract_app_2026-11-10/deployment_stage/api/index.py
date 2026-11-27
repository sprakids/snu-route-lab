"""Vercel Python function entrypoint, sharing the tested local backend."""
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlencode

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import Application, make_handler

_application=Application()
_base=make_handler(_application)

class handler(_base):
    def normalize_endpoint(self):
        query=parse_qs(urlsplit(self.path).query)
        if 'endpoint' in query:
            endpoint=query.pop('endpoint')[0].strip('/')
            self.path='/api/'+endpoint+('?' + urlencode(query,doseq=True) if query else '')
    def do_GET(self):
        self.normalize_endpoint()
        try:return super().do_GET()
        except Exception:return self.send_json(503,{'error':'데이터 연결을 확인하고 있습니다. 잠시 후 다시 시도해 주세요.'})
    def do_POST(self):
        self.normalize_endpoint()
        return super().do_POST()
