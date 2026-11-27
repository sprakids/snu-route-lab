"""Local integration server; immutable V11 input and zero Seoul/Kakao polling."""
import os,json,hashlib
from pathlib import Path
os.environ['SNU_COLLECTOR_URL']='http://127.0.0.1:8857'
os.environ['SNU_COLLECTOR_TOKEN']='shadow-local-fixture-only'
import server
from http.server import ThreadingHTTPServer
from automatic_queue import AutomaticQueue
from queue_model_sync import LatestQueueModel
root=Path(__file__).resolve().parent
raw=(root.parent/'shadow_operation_261116/V11_261110162302.json').read_bytes()
app=server.Application();queue=LatestQueueModel(app.historical,remote=False)
queue._active=AutomaticQueue(app.historical,data=json.loads(raw));queue._sha256=hashlib.sha256(raw).hexdigest();queue._active.payload_sha256=queue._sha256
app.transit.automatic_queue=queue;app.transit.prefetch=lambda *args:None;app.walker.key=None
class LocalHandler(server.make_handler(app)):
    def log_message(self,*args):pass # A detached test console is not an API dependency.
ThreadingHTTPServer(('127.0.0.1',8861),LocalHandler).serve_forever()
