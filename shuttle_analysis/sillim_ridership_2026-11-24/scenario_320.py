"""Rebuild the Gwanaksan scenario using only Nov 5 station boardings."""
import csv
import io
import json
import math
import zipfile
from collections import Counter, defaultdict

from return_patterns import DAY, ROOT, TABLES, records


def collect():
    scope = json.loads((ROOT.parent / "seoul_boardings_2026-11-10/stop_scope.json").read_text(encoding="utf-8"))
    core = {s["stop_id"] for s in scope["stops"] if s["zone"] == "campus_core"}
    inside = core | {s["stop_id"] for s in scope["stops"] if s["zone"] == "campus_annex"}
    boardings = defaultdict(list)
    history = defaultdict(list)
    bus = Counter()
    morning = Counter()
    total = Counter()
    path = ROOT.parent / "tdata_campus_cards_2026-11-10/archives/TAIMS_20261109.zip"
    with zipfile.ZipFile(path) as archive:
        with archive.open("VW_KSCC_DH_CARD.csv") as source:
            known = {s["BSST_ID"] for s in csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig"))}
        for table in TABLES:
            for r in records(archive, table):
                t = r["RIDE_DTM"]
                if r["RIDE_BSST_ID"] != "4411" or r["ROUTE_ID"] or not "15" <= t[8:10] < "19":
                    continue
                total[int(t[8:10])] += int(r["PSNG_NUM"])
                assert r["PSNG_NUM"] == "1"
                if r["TRCR_ID"] and r["TRTR_FCNT"].isdigit():
                    boardings[r["TRCR_ID"]].append((t, int(r["TRTR_FCNT"]), r["TRNC_ID"]))
        cards = {c.encode("utf-8") for c in boardings}
        for table in TABLES:
            for r in records(archive, table, cards):
                t, end, start = r["RIDE_DTM"], r["ALGH_DTM"], r["RIDE_BSST_ID"]
                is_bus = bool(r["ROUTE_ID"])
                inbound = (is_bus and start in known and start not in inside and r["ALGH_BSST_ID"] in core
                           and r["PSNG_NUM"] == "1" and DAY + "060000" <= end < DAY + "130000" and t <= end)
                seq = int(r["TRTR_FCNT"]) if r["TRTR_FCNT"].isdigit() else None
                history[r["TRCR_ID"]].append((t, end, inbound, is_bus and start in core, seq, r["TRNC_ID"]))
    for card, rail in boardings.items():
        legs = history[card]
        for t, seq, trip in rail:
            hour = int(t[8:10])
            if seq > 0:
                matches = [leg for leg in legs if trip and leg[5] == trip and leg[4] == seq - 1 and leg[3]
                           and len(leg[1]) == 14 and leg[0] <= leg[1] <= t]
                if len(matches) == 1:
                    bus[hour] += 1
                continue
            before = sorted((leg for leg in legs if leg[0] < t), key=lambda leg: leg[0])
            if not before or sum(leg[0] == t for leg in legs) != 1:
                continue
            last = before[-1]
            if last[2] and sum(leg[0] == last[0] for leg in before) == 1 and all(
                len(leg[1]) == 14 and leg[1] <= t for leg in before
            ):
                morning[hour] += 1
    return total, bus, morning


def main():
    total, bus, morning = collect()
    overlap = json.loads((ROOT / "morning_overlap_20261105.json").read_text(encoding="utf-8"))["stations"]["4411"]
    assert sum(bus.values()) == overlap["campus_bus_then_rail"] == 87
    assert sum(morning.values()) == overlap["morning_then_first_rail"] == 125
    assert [total[h] for h in range(15, 19)] == [304, 357, 304, 330]
    inputs = [("low", 51/87, 240, .25), ("base", .40, 320, .50), ("high", .30, 400, .25)]
    scenarios = []
    for label, rate, target, weight in inputs:
        hourly = [.80 * (bus[h] + morning[h] / rate) for h in range(15, 19)]
        probabilities = [v / sum(hourly) for v in hourly]
        exact = [target * p for p in probabilities]
        apportioned = [math.floor(x) for x in exact]
        by_remainder = sorted(range(4), key=lambda i: exact[i] - apportioned[i], reverse=True)
        for i in by_remainder[:target - sum(apportioned)]:
            apportioned[i] += 1
        assert sum(apportioned) == target and math.isclose(sum(probabilities), 1.)
        scenarios.append(dict(scenario=label, morning_capture_assumption=rate, raw_student_trip_estimate=sum(hourly),
                              round_target=target, experimental_weight=weight,
                              hourly_boarding_probabilities=probabilities, hourly_reference_counts=apportioned))
    assert math.isclose(sum(s["experimental_weight"] for s in scenarios), 1)
    output = dict(date=DAY, time_zone="Asia/Seoul", station="4411", window="[15:00,19:00) rail boarding",
                  student_share_assumption=.80, hours=list(range(15,19)), all_station_boardings=dict(sorted(total.items())),
                  core_bus_connections=dict(sorted(bus.items())), morning_inbound_then_first_rail=dict(sorted(morning.items())),
                  evidence_only_student_bounds=[0,sum(total.values())], scenarios=scenarios,
                  note="Single Thursday. Trial weights are a design choice. Hourly event timing and access mix are modeled. No individual route choice probabilities are measured.")
    (ROOT / "scenario_320.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
