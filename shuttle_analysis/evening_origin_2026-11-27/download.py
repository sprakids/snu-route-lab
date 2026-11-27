"""Fetch the two November Thursday holdouts, using file IDs from the public official index."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
from urllib.request import Request,urlopen
from zipfile import ZipFile

HERE=Path(__file__).resolve().parent
ARCHIVES=HERE.parent/'tdata_campus_cards_2026-11-10/archives'
INDEX='https://t-data.seoul.go.kr/dataprovide/trafficdataviewfile.do?data_id=20006'

def main():
    page=urlopen(INDEX,timeout=45).read().decode('utf8')
    ids={day:(label,code) for code,label,day in re.findall(r'<option value="(\d+)">(TAIMS_\d{8}_(\d{8})\.zip)</option>',page)}
    def fetch(day):
        name,code=ids[day];path=ARCHIVES/name
        url=f'https://t-data.seoul.go.kr/dataprovide/download.do?id={code}'
        if path.exists() and (HERE/f'source_{day}.json').exists():return
        temp=path.with_suffix('.part')
        digest=hashlib.sha256();size=0
        with urlopen(Request(url,headers={'Referer':INDEX,'User-Agent':'SNU-Route-Research/1.0'}),timeout=90) as src, temp.open('wb') as out:
            length=src.headers.get('Content-Length')
            for block in iter(lambda:src.read(4*1024*1024),b''):
                if size==0:assert block[:4]==b'PK\x03\x04'
                out.write(block);digest.update(block);size+=len(block)
        if length:assert int(length)==size
        with ZipFile(temp) as z:
            assert all('VW_KSCC_'+table+'_CARD.csv' in z.namelist() for table in ('DC','DD','DX','DH','DO'))
        temp.replace(path)
        (HERE/f'source_{day}.json').write_text(json.dumps(dict(date=day,url=url,index=INDEX,file=name,size=size,
                        sha256=digest.hexdigest()),indent=2),encoding='utf8')
        print(day,size,flush=True)
    with ThreadPoolExecutor(2) as pool:list(pool.map(fetch,['20261112','20261119']))

if __name__=='__main__':main()
