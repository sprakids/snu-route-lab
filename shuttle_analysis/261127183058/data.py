"""Collect two reserved evaluation days; training stop shares use only November 5."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import io
import json
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile

D = Path(__file__).resolve().parent
ROOT = D.parent
ARCH = ROOT/"tdata_campus_cards_2026-11-10/archives"
INDEX = "https://t-data.seoul.go.kr/dataprovide/trafficdataviewfile.do?data_id=20006"
PAIR = ("120000173","120000174")
ENDS = {"120900119":"nak","120900110":"nak","120000150":"snu"}
TEST = {"20261117":("16254","20261121"),"20261118":("16266","20261122")}


def read(path):
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))


def collect(date):
    code,posted=TEST[date]
    ARCH.mkdir(parents=True,exist_ok=True)
    name=f"TAIMS_{posted}_{date}.zip"
    file=ARCH/name
    receipt=D/f"source_{date}.json"
    if not (file.exists() and receipt.exists()):
        url="https://t-data.seoul.go.kr/dataprovide/download.do?id="+code
        assert f'value="{code}">{name}</option>' in urlopen(INDEX,timeout=60).read().decode("utf8")
        tmp=file.with_suffix(".v13.part")
        sha=hashlib.sha256()
        with urlopen(Request(url,headers={"Referer":INDEX}),timeout=180) as src,tmp.open("wb") as out:
            for block in iter(lambda:src.read(4*1024*1024),b""):
                sha.update(block);out.write(block)
            if src.headers.get("Content-Length"): assert int(src.headers["Content-Length"])==out.tell()
        with ZipFile(tmp) as z: assert "VW_KSCC_DX_CARD.csv" in z.namelist()
        tmp.replace(file)
        receipt.write_text(json.dumps(dict(date=date,file=name,index=INDEX,url=url,sha256=sha.hexdigest(),size=file.stat().st_size),indent=2),encoding="utf8")
    scope=json.loads((ROOT/"seoul_boardings_2026-11-10/stop_scope.json").read_bytes())["stops"]
    campus={s["stop_id"] for s in scope if s["zone"] in ("campus_core","campus_annex")}
    sites={s["stop_id"].encode() for s in scope if s["zone"]=="campus_core"}
    counts=Counter()
    with ZipFile(file) as z:
        with z.open("VW_KSCC_DH_CARD.csv") as f:
            outside={r["BSST_ID"] for r in csv.DictReader(io.TextIOWrapper(f,encoding="utf-8-sig"))}-campus
        for table in ("DC","DD","DX"):
            with z.open(f"VW_KSCC_{table}_CARD.csv") as f:
                cols=next(csv.reader([f.readline().decode("utf-8-sig")]))
                i=cols.index("RIDE_BSST_ID")
                for line in f:
                    if line.split(b",",i+1)[i].strip(b'"') not in sites:continue
                    r=dict(zip(cols,next(csv.reader([line.decode("utf8")]))))
                    if r["STDR_DE"]!=date or not r["RIDE_DTM"].startswith(date) or not r["ROUTE_ID"]:continue
                    stop=r["RIDE_BSST_ID"];h=int(r["RIDE_DTM"][8:10]);off=r["ALGH_BSST_ID"];w=int(r["PSNG_NUM"])
                    if off in outside:counts[stop,h,"outside"]+=w
                    if stop in PAIR:
                        counts[stop,h,"all"]+=w
                        if off in ENDS:counts[stop,h,ENDS[off]]+=w
    assert all(sum(v for (s,h,m),v in counts.items() if m=="all" and s==stop)>0 for stop in PAIR)
    with (D/f"holdout_{date}.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.writer(f);writer.writerow(("stop","hour","metric","observed"))
        writer.writerows([*k,v] for k,v in sorted(counts.items()))


if __name__=="__main__":
    with ThreadPoolExecutor(2) as pool:list(pool.map(collect,TEST))
