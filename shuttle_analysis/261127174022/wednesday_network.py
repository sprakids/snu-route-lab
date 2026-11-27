"""Obtain the same known off-campus alighting measure for the reserved Wednesday."""
from collections import Counter
import csv
import io
import json
from zipfile import ZipFile
from cards import ARCH, FILES, HERE, ROOT


def main():
    when = "20261111"
    scope = json.loads((ROOT / "seoul_boardings_2026-11-10/stop_scope.json").read_bytes())["stops"]
    campus = {s["stop_id"] for s in scope if s["zone"] in ("campus_core","campus_annex")}
    sites = {s["stop_id"].encode() for s in scope if s["zone"] == "campus_core"}
    counts = Counter()
    with ZipFile(ARCH / FILES[when]) as z:
        with z.open("VW_KSCC_DH_CARD.csv") as stream:
            outside = {r["BSST_ID"] for r in csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig"))} - campus
        for table in ("DC","DD","DX"):
            with z.open(f"VW_KSCC_{table}_CARD.csv") as stream:
                cols = next(csv.reader([stream.readline().decode("utf-8-sig")]))
                ix = cols.index("RIDE_BSST_ID")
                for line in stream:
                    if line.split(b",",ix+1)[ix].strip(b'"') not in sites:
                        continue
                    r = dict(zip(cols,next(csv.reader([line.decode("utf8")]))))
                    if r["STDR_DE"] == when and r["RIDE_DTM"].startswith(when) and r["ALGH_BSST_ID"] in outside:
                        counts[r["RIDE_BSST_ID"],int(r["RIDE_DTM"][8:10])] += int(r["PSNG_NUM"])
    assert sum(counts.values()) > 0
    with (HERE/"network_cards_20261111.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer = csv.writer(f)
        writer.writerow(("stop","hour","observed"))
        writer.writerows([*key,v] for key,v in sorted(counts.items()))


if __name__ == "__main__":
    main()
