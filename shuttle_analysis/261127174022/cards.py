"""Aggregate paid boardings by stop and hour without keeping passenger identifiers."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ARCH = ROOT / "tdata_campus_cards_2026-11-10/archives"
INDEX = "https://t-data.seoul.go.kr/dataprovide/trafficdataviewfile.do?data_id=20006"
FILES = {"20261105": "TAIMS_20261109.zip", "20261111": "TAIMS_20261115_20261111.zip",
         "20261112": "TAIMS_20261116_20261112.zip", "20261119": "TAIMS_20261123_20261119.zip"}
STOPS = {"120000173", "120000174"}


def fetch_wednesday():
    path = ARCH / FILES["20261111"]
    receipt = HERE / "source_20261111.json"
    if path.exists() and receipt.exists():
        return
    url = "https://t-data.seoul.go.kr/dataprovide/download.do?id=16192"
    with urlopen(INDEX, timeout=45) as response:
        assert f'value="16192">{path.name}</option>' in response.read().decode("utf8")
    tmp = HERE / (path.name + ".part")
    digest = hashlib.sha256()
    with urlopen(Request(url, headers={"Referer": INDEX}), timeout=120) as response, tmp.open("wb") as dst:
        for block in iter(lambda: response.read(4 * 1024 * 1024), b""):
            dst.write(block)
            digest.update(block)
        if response.headers.get("Content-Length"):
            assert dst.tell() == int(response.headers["Content-Length"])
    with ZipFile(tmp) as z:
        assert "VW_KSCC_DX_CARD.csv" in z.namelist()
    tmp.replace(path)
    receipt.write_text(json.dumps(dict(date="20261111", url=url, index=INDEX, file=path.name,
                                       bytes=path.stat().st_size, sha256=digest.hexdigest()),indent=2),encoding="utf8")


def extract(date, file):
    counts = Counter()
    with ZipFile(ARCH / file) as z:
        for table in ("DC", "DD", "DX"):
            with z.open(f"VW_KSCC_{table}_CARD.csv") as stream:
                cols = next(csv.reader([stream.readline().decode("utf-8-sig")]))
                for line in stream:
                    if b"120000173" not in line and b"120000174" not in line:
                        continue
                    r = dict(zip(cols,next(csv.reader([line.decode("utf8")]))))
                    stop, dest, time = r["RIDE_BSST_ID"], r["ALGH_BSST_ID"], r["RIDE_DTM"]
                    if stop not in STOPS or not r["ROUTE_ID"] or r["STDR_DE"] != date or not time.startswith(date):
                        continue
                    h, w = int(time[8:10]), int(r["PSNG_NUM"])
                    counts[stop,h,"all"] += w
                    if dest in ("120900119", "120900110"):
                        counts[stop,h,"nak"] += w
                        if r["ROUTE_ID"] == "120900011":
                            counts[stop,h,"line_nak"] += w
                    if dest == "120000150":
                        counts[stop,h,"snu"] += w
    assert all(sum(v for (s,h,m),v in counts.items() if s==stop and m=="all") > 0 for stop in STOPS)
    with (HERE/f"cards_{date}.csv").open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(("stop","hour","metric","passengers"))
        writer.writerows([*k,v] for k,v in sorted(counts.items()))
    print(date, "OK", flush=True)


if __name__ == "__main__":
    fetch_wednesday()
    for date, file in FILES.items():
        extract(date, file)
