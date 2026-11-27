"""Download the publicly listed October 2026 hourly boarding CSV, no API key."""
from pathlib import Path
import urllib.request, urllib.parse, re, hashlib, json

ROOT=Path(__file__).resolve().parent
page=(ROOT/'sources/boarding_hourly_page.html').read_text(encoding='utf-8')
match=re.search(r'title="(2026년_버스노선별_정류장별_시간대별_승하차_인원_정보\(10월\)\.csv)" onclick="javascript:downloadFile\(\'(\d+)\'\)',page)
assert match,'October file must exist on the official page; never guess its sequence'
name,seq=match.groups()
target=ROOT/'sources/boardings_hourly_202610.csv'
url='https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false'
body=urllib.parse.urlencode({'infId':'OA-12913','seqNo':'','seq':seq,'infSeq':'3'}).encode()
if not target.exists():
    req=urllib.request.Request(url,data=body,headers={'User-Agent':'Mozilla/5.0',
        'Referer':'https://data.seoul.go.kr/dataList/OA-12913/A/1/datasetView.do'})
    with urllib.request.urlopen(req,timeout=45) as response:
        content_type=response.headers.get('Content-Type','')
        content_disposition=response.headers.get('Content-Disposition','')
        data=response.read()
    if data[:100].lstrip().lower().startswith((b'<html',b'<!doctype')):
        (ROOT/'sources/download_error.html').write_bytes(data)
        raise RuntimeError('Download returned HTML instead of CSV; evidence saved')
    assert len(data)>1_000_000,(len(data),content_type)
    target.write_bytes(data)
else:
    data=target.read_bytes();content_type='previously downloaded';content_disposition=''
receipt={'source_page':'https://data.seoul.go.kr/dataList/OA-12913/A/1/datasetView.do',
    'source_filename':name,'listed_sequence':seq,'request_method':'POST','download_url':url,
    'api_key_used':False,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
    'content_type':content_type,'content_disposition':content_disposition,
    'local_file':str(target)}
(ROOT/'sources/download_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(receipt,ensure_ascii=False,indent=2))
