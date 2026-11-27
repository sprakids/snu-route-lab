"""Download explicitly linked public G2B attachments; preserve every response."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import urllib.request,urllib.error,json,hashlib

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'contracts/sources';OUT.mkdir(parents=True,exist_ok=True)
files=[(22,'붙임4_제안요청서.hwp'),(23,'붙임5_과업지시서.hwp'),(24,'붙임6_사업내역서.hwp')]
def get(item):
    seq,name=item
    path=OUT/name
    assert not path.exists(),'Preserve prior download'
    url=f'https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?bidPbancNo=20231243066&bidPbancOrd=001&fileSeq={seq}&fileType=&prcmBsneSeCd=03'
    record={'file':name,'url':url,'collected_at_utc':datetime.now(timezone.utc).isoformat(),
        'discovery':'Public attachment link on https://sujubut.com/bid/domestic/697360/; response from g2b.go.kr',
        'document_role':'Tender attachment, not automatically the signed current contract'}
    try:
        request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.g2b.go.kr/'})
        with urllib.request.urlopen(request,timeout=45) as response:
            body=response.read();record.update(http_status=response.status,final_url=response.url,
                content_type=response.headers.get('Content-Type'),content_disposition=response.headers.get('Content-Disposition'))
        path.write_bytes(body)
        record.update(bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),first16_hex=body[:16].hex(),
            is_ole_compound=body.startswith(bytes.fromhex('d0cf11e0a1b11ae1')))
    except Exception as error:
        record.update(error_type=type(error).__name__,error=str(error))
    (OUT/(name+'.receipt.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    return record
if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(get,files))
    (ROOT/'contracts/download_manifest.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(results,ensure_ascii=False,indent=2))
