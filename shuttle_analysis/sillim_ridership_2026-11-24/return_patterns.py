"""Count same-day campus inbound / afternoon station patterns; export aggregates only."""
import csv
import io
import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DAY = "20261105"
TARGETS = {"4410", "4411"}
TABLES = ("DC", "DD", "DX")


def records(archive, table, cards=None):
    with archive.open(f"VW_KSCC_{table}_CARD.csv") as stream:
        columns = next(csv.reader([stream.readline().decode("utf-8-sig")]))
        assert columns[0] == "TRCR_ID"
        for line in stream:
            if cards is None:
                if b",4410," not in line and b",4411," not in line:
                    continue
            elif line.partition(b",")[0].strip(b'"') not in cards:
                continue
            row = dict(zip(columns, next(csv.reader([line.decode("utf-8")]))))
            if row["STDR_DE"] == DAY and row["RIDE_DTM"].startswith(DAY):
                yield row


def count_patterns():
    scope = json.loads((ROOT.parent / "seoul_boardings_2026-11-10/stop_scope.json").read_text(encoding="utf-8"))
    core = {s["stop_id"] for s in scope["stops"] if s["zone"] == "campus_core"}
    inside = core | {s["stop_id"] for s in scope["stops"] if s["zone"] == "campus_annex"}
    targets = defaultdict(list)
    history = defaultdict(list)
    totals = Counter()
    hits = Counter()
    path = ROOT.parent / "tdata_campus_cards_2026-11-10/archives/TAIMS_20261109.zip"
    with zipfile.ZipFile(path) as archive:
        with archive.open("VW_KSCC_DH_CARD.csv") as source:
            known_stops = {s["BSST_ID"] for s in csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig"))}
        for table in TABLES:
            for r in records(archive, table):
                card, when, station = r["TRCR_ID"], r["RIDE_DTM"], r["RIDE_BSST_ID"]
                if station in TARGETS and not r["ROUTE_ID"] and "15" <= when[8:10] < "19" and r["TRTR_FCNT"] == "0":
                    totals[station] += int(r["PSNG_NUM"])
                    if card and r["PSNG_NUM"] == "1":
                        targets[card].append((when, station))
        cards = {c.encode("utf-8") for c in targets}
        for table in TABLES:
            for r in records(archive, table, cards):
                when, end = r["RIDE_DTM"], r["ALGH_DTM"]
                inbound = (bool(r["ROUTE_ID"]) and r["RIDE_BSST_ID"] in known_stops
                           and r["RIDE_BSST_ID"] not in inside and r["ALGH_BSST_ID"] in core
                           and r["PSNG_NUM"] == "1" and DAY + "060000" <= end < DAY + "130000"
                           and when <= end)
                history[r["TRCR_ID"]].append((when, end, inbound))
    for card, boardings in targets.items():
        legs = sorted(history[card])
        for when, station in boardings:
            before = [leg for leg in legs if leg[0] < when]
            if not before or sum(leg[0] == when for leg in legs) != 1:
                continue
            last = before[-1]
            if last[2] and sum(leg[0] == last[0] for leg in before) == 1 and all(
                len(end) == 14 and end <= when for _, end, _ in before
            ):
                hits[station] += 1
    return {"date": DAY, "rail_window_kst": "[15:00,19:00)", "previous_alight_window_kst": "[06:00,13:00)",
            "first_paid_boardings": dict(totals), "last_recorded_leg_inbound_then_first_rail": dict(hits)}


if __name__ == "__main__":
    result = count_patterns()
    (ROOT / "return_pattern_counts.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(result)
