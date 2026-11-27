"""Download four public attachments exposed on council post 7733 via its normal download form."""
from pathlib import Path
from datetime import datetime,timezone
import urllib.request,urllib.parse,json,hashlib
ROOT=Path(__file__).resolve().parent/'survey'
OUT=ROOT/'cardnews'; OUT.mkdir(exist_ok=True)
rows=[]
for bid in ('9324','9325','9326','9327'):
    fields={'down_mode':'SINGLE','this_blog_id':'128','bid':bid}
    url='https://we.snu.ac.kr/attach-download/'
    req=urllib.request.Request(url,data=urllib.parse.urlencode(fields).encode(),headers={'User-Agent':'Mozilla/5.0','Referer':'https://we.snu.ac.kr/7733/','Content-Type':'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req,timeout=30) as r:
        data=r.read();status=r.status;headers=dict(r.headers)
    assert data[:3]==b'\xff\xd8\xff', 'Expected JPEG, refusing to label HTML as image'
    path=OUT/f'M7733_A{bid}.jpg';assert not path.exists();path.write_bytes(data)
    rows.append({'post_id':'7733','attachment_id':bid,'source_url':url,'form_fields':fields,'file':str(path),'http_status':status,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'content_disposition':headers.get('Content-Disposition'),'captured_at_utc':datetime.now(timezone.utc).isoformat()})
(ROOT/'cardnews_downloads.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(rows,ensure_ascii=False))
