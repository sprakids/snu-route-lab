"""Data-only model refresh with last-valid fallback and request-local pinning."""
import hashlib
import json
import os
import re
import threading
import time
import urllib.request
from pathlib import Path
from automatic_queue import AutomaticQueue
from calculation_context import memoized
from queue_release import SCHEMA,MAX_PAYLOAD,SUPPLY_UPGRADE_BASE,accepted_compatibilities,compatibility,content_digest,release_time,validate

ORIGIN='https://snu-shuttle-simulation.vercel.app'
FEED=ORIGIN+'/routing-model/latest.json'
POLL_SECONDS=60

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('redirect')

def download(url,limit,timeout):
    request=urllib.request.Request(url,headers={'Accept':'application/json','Accept-Encoding':'identity',
        'Cache-Control':'no-cache','User-Agent':'SNU-Route-Queue-Sync/1'})
    with urllib.request.build_opener(NoRedirect()).open(request,timeout=timeout) as response:
        if response.geturl()!=url:raise ValueError('redirect')
        raw=response.read(limit+1)
    if len(raw)>limit:raise ValueError('payload_size')
    return raw

def strict_json(raw):
    def bad(value):raise ValueError('nonfinite_json')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate_key')
            result[key]=value
        return result
    return json.loads(raw,parse_constant=bad,object_pairs_hook=unique)

class LatestQueueModel:
    def __init__(self,historical,path=None,*,remote=None,fetch=None,clock=None):
        self._active=AutomaticQueue(historical,path);self._historical=historical
        self._compatibility=compatibility(self._active.data)
        self._accepted_compatibilities=accepted_compatibilities(self._active.data)
        self._remote=bool(os.environ.get('VERCEL') or os.environ.get('SNU_QUEUE_MODEL_SYNC')=='1') if remote is None else remote
        self._fetch=fetch or download;self._clock=clock or time.time
        self._lock=threading.Lock();self._next_check=0;self._checked_at=None;self._error=None
        self._sha256=hashlib.sha256((Path(path) if path else Path(__file__).parent/'data/auto_queue_inputs.json').read_bytes()).hexdigest()
        self._active.payload_sha256=self._sha256

    def _refresh(self):
        now=self._clock()
        if not self._remote or now<self._next_check or not self._lock.acquire(blocking=False):return
        try:
            if now<self._next_check:return
            self._next_check=now+POLL_SECONDS;self._checked_at=now
            manifest=strict_json(self._fetch(FEED,16_000,1.0))
            if manifest.get('schema')!=SCHEMA:raise ValueError('manifest_schema')
            name=manifest['model_id'];at=release_time(name)
            if at.timestamp()>now+300:raise ValueError('future_release')
            if manifest['published_at']!=at.isoformat():raise ValueError('publication_time')
            candidate_compatibility=manifest['compatibility_sha256']
            if candidate_compatibility not in self._accepted_compatibilities:raise ValueError('incompatible_clock_or_stops')
            path='/routing-model/releases/'+name+'.json'
            if manifest['payload_path']!=path:raise ValueError('payload_path')
            if not re.fullmatch('[0-9a-f]{64}',manifest['sha256']):raise ValueError('digest')
            if type(manifest['bytes']) is not int or not 0<manifest['bytes']<=MAX_PAYLOAD:raise ValueError('payload_size')
            previous=self._active.config['id']
            if re.fullmatch('[0-9]{12}',previous):
                if name<previous:raise ValueError('older_release')
                if name==previous:
                    if self._sha256!=manifest['sha256']:raise ValueError('immutable_release_changed')
                    self._error=None;return
            raw=self._fetch(ORIGIN+path,MAX_PAYLOAD,2.0)
            if len(raw)!=manifest['bytes'] or hashlib.sha256(raw).hexdigest()!=manifest['sha256']:raise ValueError('payload_hash')
            data=validate(strict_json(raw),candidate_compatibility,check_profiles=True)
            if data['model']['id']!=name or data['model']['algorithm_id']!=manifest['algorithm_id']:raise ValueError('model_identity')
            if content_digest(data)!=manifest['content_sha256']:raise ValueError('content_hash')
            release=data.get('release',{})
            for key in ('model_id','published_at','compatibility_sha256','content_sha256'):
                if release.get(key)!=manifest[key]:raise ValueError('release_metadata')
            candidate=AutomaticQueue(self._historical,data=data)
            candidate.payload_sha256=manifest['sha256']
            self._active=candidate;self._compatibility=candidate_compatibility
            # Once upgraded, a newer release cannot silently revert to 60 all day.
            if candidate_compatibility!=SUPPLY_UPGRADE_BASE:
                self._accepted_compatibilities=self._accepted_compatibilities-{SUPPLY_UPGRADE_BASE}
            self._sha256=manifest['sha256'];self._error=None
        except Exception as error:
            self._error=str(error) if type(error) is ValueError and re.fullmatch('[a-z_]+',str(error)) else type(error).__name__
        finally:self._lock.release()

    def current(self):
        def select():
            self._refresh()
            return self._active
        return memoized('queue_release',id(self),select)

    def info(self):
        selected=self.current()
        return {**selected.info(),'sync':{'enabled':self._remote,'source':FEED,'check_interval_seconds':POLL_SECONDS,
            'checked_at':self._checked_at,'next_check_at':self._next_check if self._remote else None,
            'status':'last_valid_model' if self._error else 'active','last_error':self._error,
            'active_model_id':selected.config['id'],'compatibility_sha256':compatibility(selected.data),
            'payload_sha256':selected.payload_sha256}}

    def __getattr__(self,name):return getattr(self.current(),name)
