"""Read-only localhost server for the public demo directory, with precompressed JSON."""
from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
import argparse
ROOT=Path(__file__).resolve().parent/'public'
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT),**kwargs)
    def do_GET(self):
        if '?' not in self.path and self.path.endswith('.json') and 'gzip' in self.headers.get('Accept-Encoding',''):
            target=Path(self.translate_path(self.path)).resolve()
            compressed=Path(str(target)+'.gz')
            if target.is_relative_to(ROOT.resolve()) and compressed.exists():
                self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Encoding','gzip');self.send_header('Vary','Accept-Encoding');self.send_header('Cache-Control','no-cache');self.send_header('Content-Length',str(compressed.stat().st_size));self.end_headers()
                with compressed.open('rb') as f:self.copyfile(f,self.wfile)
                return
        super().do_GET()
    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        super().end_headers()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8786);a=p.parse_args()
    print(f'http://127.0.0.1:{a.port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
