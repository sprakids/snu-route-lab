"""Aggregate Nov 5 ticket legs locally. Only station/hour aggregates leave memory."""
import csv
import io
import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DAY = "20261105"
TABLES = ("DC", "DD", "DX")


def rows(archive, table):
    with archive.open(f"VW_KSCC_{table}_CARD.csv") as binary:
        with io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as stream:
            yield from csv.reader(stream)


def aggregate():
    scope = json.loads((ROOT.parent / "seoul_boardings_2026-11-10/stop_scope.json").read_text("utf-8"))
    stops = {s["stop_id"] for s in scope["stops"] if s["zone"] == "campus_core"}
    previous = defaultdict(set)
    counts = defaultdict(Counter)
    connected = Counter()
    gate_routes = Counter()
    gate_exits = Counter()
    gate_origins = Counter()
    qa = Counter()
    with zipfile.ZipFile(ROOT.parent / "tdata_campus_cards_2026-11-10/archives/TAIMS_20261109.zip") as archive:
        with archive.open("VW_KSCC_DV_CARD.csv") as f:
            stations = {r["OUT_STN_NUM"]: r["STN_KR_NM"] for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))}
        with archive.open("VW_KSCC_DO_CARD.csv") as f:
            routes = {r["ROUTE_ID"]: r["ROUTE_NUM"] for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))}
        with archive.open("VW_KSCC_DH_CARD.csv") as f:
            names = {r["BSST_ID"]: r["BSST_NM"] for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))}
        for table in TABLES:
            it = rows(archive, table)
            h = next(it)
            stop, route, board, alight, seq, trip, card, day = map(h.index, ("RIDE_BSST_ID", "ROUTE_ID", "RIDE_DTM", "ALGH_DTM", "TRTR_FCNT", "TRNC_ID", "TRCR_ID", "STDR_DE"))
            end = h.index("ALGH_BSST_ID")
            for r in it:
                if r[stop] not in stops or not r[route] or r[day] != DAY or not r[board].startswith(DAY):
                    continue
                if r[card] and r[trip] and r[seq].isdigit() and len(r[alight]) == 14 and r[board] <= r[alight]:
                    previous[(r[card], r[trip], int(r[seq]) + 1)].add((r[board], r[alight], r[stop], r[end], r[route]))

        for table in TABLES:
            it = rows(archive, table)
            h = next(it)
            stop, route, board, seq, trip, card, n, day = map(h.index, ("RIDE_BSST_ID", "ROUTE_ID", "RIDE_DTM", "TRTR_FCNT", "TRNC_ID", "TRCR_ID", "PSNG_NUM", "STDR_DE"))
            for r in it:
                station = r[stop]
                if r[route] or station not in stations or r[day] != DAY or not r[board].startswith(DAY):
                    continue
                hour = int(r[board][8:10])
                count = int(r[n])
                if station.startswith("44") or station in {"0227", "0228"}:
                    counts[station][hour] += count
                if 15 <= hour < 19 and r[seq].isdigit():
                    matches = previous.get((r[card], r[trip], int(r[seq])), ())
                    valid = [p for p in matches if p[1] <= r[board]]
                    if len(valid) == 1:
                        connected[station] += count
                        if station == "4411":
                            _, _, start, finish, route_id = valid[0]
                            gate_routes[routes.get(route_id, route_id)] += count
                            gate_exits[f"{names.get(finish, '')} ({finish})"] += count
                            gate_origins[f"{names.get(start, '')} ({start})"] += count
                    elif matches:
                        qa["ambiguous_or_out_of_order"] += count
    return dict(day=DAY, rail_board_window="15:00 <= time < 19:00 KST", core_stop_count=len(stops),
                hourly_rail_boardings={stations[s] + " (" + s + ")": dict(sorted(v.items())) for s, v in sorted(counts.items())},
                campus_bus_to_rail={stations[s] + " (" + s + ")": v for s, v in connected.most_common()},
                gwanaksan_previous_bus_route=dict(gate_routes.most_common()),
                gwanaksan_previous_bus_exit=dict(gate_exits.most_common()),
                gwanaksan_previous_bus_entry=dict(gate_origins.most_common()),
                campus_bus_to_any_rail=sum(connected.values()), qa=qa)


if __name__ == "__main__":
    result = aggregate()
    (ROOT / "campus_transfer_counts.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(result["campus_bus_to_any_rail"], result["campus_bus_to_rail"], result["qa"])
