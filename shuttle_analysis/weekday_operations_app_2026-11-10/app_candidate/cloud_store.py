"""Small private JSON documents with consistent reads and ETag-conditional writes.

Used for this prototype's shared quotas, snapshots and observation records.
Authentication stays in Vercel's runtime environment. No credentials are logged.
"""
import json
import os
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request

class Conflict(Exception):pass

class CloudStore:
    def __init__(self):
        self.store_id=os.environ['BLOB_STORE_ID']
        identifier=self.store_id.removeprefix('store_').lower()
        self.base='https://'+identifier+'.private.blob.vercel-storage.com/'

    def headers(self):
        token=os.environ.get('BLOB_READ_WRITE_TOKEN') or os.environ.get('VERCEL_OIDC_TOKEN')
        if not token:raise RuntimeError('Cloud storage credentials unavailable')
        return {'Authorization':'Bearer '+token,'x-vercel-blob-store-id':self.store_id,'x-api-version':'12'}

    @staticmethod
    def pathname(key):
        if not key or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in key):
            raise ValueError('Invalid state document name')
        return 'route-lab-v1/'+key+'.json'

    def read(self,key):
        url=self.base+self.pathname(key)+'?cache=0'
        req=urllib.request.Request(url,headers=self.headers())
        try:
            with urllib.request.urlopen(req,timeout=8) as response:
                etag=response.headers.get('ETag')
                if not etag:raise RuntimeError('Cloud state ETag missing')
                return json.load(response),etag
        except urllib.error.HTTPError as error:
            status=error.code;error.close()
            if status==404:return {},None
            raise RuntimeError('Cloud state read failed') from None

    def write(self,key,value,etag):
        headers=self.headers()|{'Content-Type':'application/json','x-content-type':'application/json',
            'x-vercel-blob-access':'private','x-add-random-suffix':'0',
            'x-allow-overwrite':'1' if etag else '0','x-cache-control-max-age':'60'}
        if etag:headers['x-if-match']=etag
        url='https://vercel.com/api/blob?'+urllib.parse.urlencode({'pathname':self.pathname(key)})
        req=urllib.request.Request(url,data=json.dumps(value,ensure_ascii=False,allow_nan=False).encode(),headers=headers,method='PUT')
        try:
            with urllib.request.urlopen(req,timeout=8) as response:json.load(response)
        except urllib.error.HTTPError as error:
            status=error.code;detail=error.read(2000).decode(errors='replace').lower();error.close()
            if status in (409,412) or status==400 and ('already exists' in detail or 'already_exists' in detail):raise Conflict() from None
            raise RuntimeError('Cloud state write failed') from None

    def mutate(self,key,transform):
        for attempt in range(8):
            previous,etag=self.read(key)
            value,result=transform(previous)
            if value is None:return result
            try:self.write(key,value,etag);return result
            except Conflict:time.sleep(.015*(attempt+1))
        raise RuntimeError('Cloud state busy; retry shortly')

    def budget(self,day,service,limit):
        def change(doc):
            count=doc.get(service,0)
            if count>=limit:return None,False
            doc[service]=count+1
            return doc,True
        # Reserve globally before calling the external API. Fail closed on store failure.
        try:return self.mutate('quota-'+day,change)
        except RuntimeError:return False

    def used(self,day,service):return self.read('quota-'+day)[0].get(service,0)

    def cached(self,key,seconds,producer):
        owner=uuid.uuid4().hex;now=time.time()
        def claim(doc):
            if doc.get('expires_at',0)>now or doc.get('lease_until',0)>now:
                return None,(False,doc.get('value'))
            return {**doc,'lease_until':now+55,'owner':owner},(True,doc.get('value'))
        owned,previous=self.mutate('cache-'+key,claim)
        if not owned:return previous
        try:value=producer()
        except Exception:
            def release(doc):return ({**doc,'lease_until':0},None) if doc.get('owner')==owner else (None,None)
            self.mutate('cache-'+key,release)
            raise
        def publish(doc):
            if doc.get('owner')!=owner:return None,None
            return {'value':value,'expires_at':time.time()+seconds,'lease_until':0},None
        self.mutate('cache-'+key,publish)
        return value

    def observations(self):return self.read('observations')[0].get('rows',[])

    def add_observation(self,record):
        def change(doc):
            rows=doc.get('rows',[])
            if len(rows)>=5000:raise ValueError('시제품 기록 한도에 도달했습니다.')
            record_id=doc.get('next_id',1)
            rows.append({**record,'id':record_id})
            return {'rows':rows,'next_id':record_id+1},record_id
        return self.mutate('observations',change)
