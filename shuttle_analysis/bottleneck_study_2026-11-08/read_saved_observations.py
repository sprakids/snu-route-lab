"""Read already saved collector archives. Never call Seoul APIs or collector jobs."""
from pathlib import Path
import collections,datetime,gzip,hashlib,json,os,sys,urllib.request

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'bus_api_2026-11-04'))
from credential_store import crypt
KST=datetime.timezone(datetime.timedelta(hours=9))

def save(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
def objects(raw):
    text=gzip.decompress(raw).decode('utf-8');decoder=json.JSONDecoder();pos=0
    while pos<len(text):
        while pos<len(text) and text[pos].isspace():pos+=1
        if pos>=len(text):break
        obj,pos=decoder.raw_decode(text,pos);yield obj

def main():
    credential=Path(os.environ['LOCALAPPDATA'])/'SnuTransit/credentials/collector_backend.dpapi'
    c=json.loads(crypt(credential.read_bytes(),decrypt=True))
    source=HERE/'sources';source.mkdir(exist_ok=True)
    manifest=[];records=[];coverage=[]
    for day in ('2026-11-07','2026-11-08'):
        p=source/f'collector-{day}.json.gz';cached=p.exists()
        if not cached:
            request=urllib.request.Request(c['url'].rstrip('/')+'/export?day='+day,headers={'Authorization':'Bearer '+c['token'],'User-Agent':'SNU-Bottleneck-Study/1.0'})
            with urllib.request.urlopen(request,timeout=30) as response:raw=response.read()
            # Reject invalid/partial archives before persisting them.
            list(objects(raw));p.write_bytes(raw)
        raw=p.read_bytes();manifest.append({'date':day,'path':p.name,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'cache_reused':cached,'source':'saved collector /export; no upstream API request'})
        batches=list(objects(raw));count=0;stamps=[]
        for batch in batches:
            for v in batch.get('vehicles',[]):
                if not v.get('provided_at'):continue
                count+=1;stamps.append(v['provided_at'])
                records.append({k:v.get(k) for k in ('id','route_id','route_name','provided_at','captured_at','section_order','at_stop','full','crowd_code')})
        coverage.append({'archive_day':day,'batches':len(batches),'poll_rows':count,'first':datetime.datetime.fromtimestamp(min(stamps),KST).isoformat() if stamps else None,'last':datetime.datetime.fromtimestamp(max(stamps),KST).isoformat() if stamps else None})
    # First deduplicate the same provider timestamp; then one label per vehicle-trip-section.
    unique={}
    for v in records:
        key=(v['route_id'],v['id'],v['provided_at'],v['section_order'])
        unique[key]=v
    seen={};passages=[]
    for v in sorted(unique.values(),key=lambda x:(x['route_id'],x['id'],x['provided_at'])):
        key=(v['route_id'],v['id']);prior=seen.get(key);seq=int(v['section_order'] or 0)
        newtrip=prior is None or seq<prior['seq'] or v['provided_at']-prior['at']>1800
        trip=(prior['trip']+1 if prior else 0) if newtrip else prior['trip']
        if newtrip or seq!=prior['seq']:
            at=datetime.datetime.fromtimestamp(v['provided_at'],KST)
            passages.append({**v,'trip':trip,'date':at.date().isoformat(),'weekday':at.weekday(),'half_hour':at.hour*2+at.minute//30})
        seen[key]={'seq':seq,'at':v['provided_at'],'trip':trip}
    grouped=collections.defaultdict(collections.Counter)
    for p in passages:
        grouped[p['date'],p['route_name']][str(p['crowd_code'])]+=1
    summary={'source_manifest':manifest,'coverage':coverage,'poll_rows':len(records),'unique_provider_rows':len(unique),'vehicle_section_passages':len(passages),
        'unique_vehicle_routes':len(set((p['route_id'],p['id']) for p in passages)),
        'by_date_route':[{'date':d,'route':r,'grades':dict(c),'n':sum(c.values())} for (d,r),c in sorted(grouped.items())],
        'grade_source':'https://www.data.go.kr/data/15000332/openapi.do',
        'grade_definition':{'0':'정보 없음','3':'여유','4':'보통','5':'혼잡','6':'매우혼잡'},
        'limitations':['Weekend and partial collection coverage; cannot validate weekday peak queue or occupancy.','One first label per vehicle-trip-section, not independent person samples.','Unknown grade 0 excluded from valid-grade percentages.','Bus IDs retained in private audit only; never publish raw archives or individual IDs.']}
    save(HERE/'observation_inventory.json',summary)
    save(source/'deduplicated_passages.private.json',passages)
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
