"""Server-only client for the shared collector. Never fetch positions per visitor."""
import json,os,time,threading,urllib.request
from service_state import PersistenceUnavailable

class CollectorState:
    persistent=True
    position_updates_paused=False
    message=''
    def __init__(self,url=None,token=None):
        self.url=(url or os.environ.get('SNU_COLLECTOR_URL','')).rstrip('/')
        self.token=token or os.environ.get('SNU_COLLECTOR_TOKEN','')
        self.latest={};self.latest_at=0;self.history_cache={};self.available=False;self.lock=threading.RLock()
    def request(self,path,body=None):
        raw=json.dumps(body,ensure_ascii=False,allow_nan=False).encode() if body is not None else None
        req=urllib.request.Request(self.url+path,data=raw,headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json','User-Agent':'SNU-Route-Lab/0.4'})
        try:
            with urllib.request.urlopen(req,timeout=5) as r:result=json.load(r)
            self.available=True;self.message='';return result
        except Exception:
            self.available=False;self.message='공용 저장소 연결이 지연됩니다. 마지막 관측 시각을 확인해 주세요.'
            raise PersistenceUnavailable('공용 저장소에 연결하지 못했습니다. 입력한 기록은 저장되지 않았습니다.') from None
    def snapshot(self):
        with self.lock:
            if time.time()-self.latest_at>=5:
                try:self.latest=self.request('/snapshot');self.latest_at=time.time()
                except PersistenceUnavailable:self.latest_at=time.time()
            return {**self.latest,'collector_available':self.available}
    def history(self,when):
        # Shared historical query reads saved observations; it cannot collect buses.
        import urllib.parse
        key=int(when)//3600;cached=self.history_cache.get(key)
        if cached and time.time()-cached[0]<300:return cached[1]
        try:
            result=self.request('/history?'+urllib.parse.urlencode({'when':int(when)}))
            if len(self.history_cache)>168:self.history_cache.clear()
            self.history_cache[key]=(time.time(),result);return result
        except PersistenceUnavailable:return {'traffic':{},'historical_traffic':{},'travel_history':{},'available':False}
    def info(self):return {'mode':'cloudflare_sqlite','persistent':True,'observations_available':self.available,'available':self.available,
        'blob_access_enabled':False,'counter_scope':'global','message':self.message}
    def used(self,day,service):
        state=self.snapshot()
        return state.get('position_calls_today') if service=='seoul_position' else state.get('service_calls',{}).get(service)
    def budget(self,day,service,limit):
        if service=='seoul_position':return False
        try:return bool(self.request('/budget',{'service':service,'limit':limit}).get('allowed'))
        except PersistenceUnavailable:return False
    def read(self,key):
        try:return self.request('/cache',{'key':key.removeprefix('cache-'),'action':'read'}),None
        except PersistenceUnavailable:return {},None
    def cached(self,key,seconds,producer):
        try:claim=self.request('/cache',{'key':key,'action':'claim'})
        except PersistenceUnavailable:
            # A failed lease must not discard a readable last observation.
            return self.read('cache-'+key)[0].get('value')
        if not claim.get('owned'):return claim.get('value')
        try:
            value=producer()
        except Exception:
            try:self.request('/cache',{'key':key,'action':'release','owner':claim['owner']})
            except PersistenceUnavailable:pass
            raise
        try:self.request('/cache',{'key':key,'action':'publish','owner':claim['owner'],'value':value,'seconds':seconds})
        except PersistenceUnavailable:pass  # This instance still has a valid source observation.
        return value
    def observations(self,candidates=None):
        try:return (self.request('/observation-errors',{'keys':candidates}) if candidates is not None else self.request('/observations')).get('records',[])
        except PersistenceUnavailable:return []
    def add_observation(self,record):return self.request('/observations',record)['id']
