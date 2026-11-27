"""Temporary app preview using the existing shared collector, with isolated local state."""
import os,sys
from pathlib import Path
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parents[1]
sys.path.insert(0,str(BASE/'app'));sys.path.insert(0,str(BASE/'collector'))
from export_history import credentials
import server
from collector_client import CollectorState
c=credentials()
server.SHARED=CollectorState(c['url'],c['token'])
server.RUNTIME=ROOT/'preview-runtime';server.RUNTIME.mkdir(exist_ok=True)
os.environ['SNU_QUEUE_MODEL_SYNC']='1'
app=server.Application()
http=ThreadingHTTPServer(('127.0.0.1',0),server.make_handler(app))
print('ICON_APP_PREVIEW=http://127.0.0.1:'+str(http.server_port),flush=True)
http.serve_forever()
