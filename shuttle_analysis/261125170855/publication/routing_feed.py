"""Export terminal wait estimates by the minute a passenger physically joins the queue."""
from bisect import bisect_left, bisect_right
from collections import defaultdict
import gzip
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL = HERE.parent
STOPS = {"admin_snu": "41841", "admin_daehak": "41843"}
COLUMNS = ["minute", "boarded_mass", "mean_join_to_board_s", "mean_board_to_depart_s",
           "queue_mean_people", "next_dispatch_boarding_share"]


def read(path):
    with gzip.open(path, "rt", encoding="utf8") as file:
        return json.load(file)


def minute_mean(curve, times, minute):
    start = minute * 60
    end = start + 60
    i = bisect_right(times, start)
    level = curve[i - 1][1] if i else 0.
    area = 0.
    for t, new_level, _ in curve[i:bisect_left(times, end)]:
        area += level * (t - start)
        start, level = t, new_level
    return (area + level * (end - start)) / 60


def build_case(key, nodes):
    data = read(MODEL / "viewer-data" / (key + ".json.gz"))
    audit = read(MODEL / "runs/candidate" / key / ("audit-" + key + ".json.gz"))
    windows = {vehicle: (node, departure, cap) for node, vehicle, _, departure, cap in data["door_windows"]}
    rows, supply = {}, {}
    for stop, node in nodes.items():
        clocks = sorted({dep for n, dep, _ in windows.values() if n == node})
        schedule = defaultdict(list)
        for n, vehicle, _, _, dep, plan in data["terminal_presence"]:
            if n == node:
                wn, wd, capacity = windows[vehicle]
                assert (n, dep) == (wn, wd)
                schedule[plan].append(capacity)
        supply[stop] = [[int(plan), sorted(caps)] for plan, caps in sorted(schedule.items())]
        groups = defaultdict(list)
        for rider in audit["wait_audit"]:
            if rider["node"] != node or rider["outcome"] != "boarded":
                continue
            entry, boarded, mass = rider["physical_stop_entry"], rider["end"], rider["weight"]
            n, depart, _ = windows[rider["vehicle"]]
            assert n == node and 0 < mass and entry <= boarded <= depart
            first = depart == clocks[bisect_left(clocks, entry)]
            groups[int(entry // 60)].append((mass, boarded - entry, depart - boarded, first))
        curve = data["queue_timeline"][node]
        times = [row[0] for row in curve]
        independent = data["terminal_minute_waits"][str(node)]
        assert {int(m) for m in independent} == set(groups)
        rows[stop] = []
        for minute, trips in sorted(groups.items()):
            mass = math.fsum(r[0] for r in trips)
            wait, dwell, share = [math.fsum(r[0]*r[i] for r in trips)/mass for i in (1, 2, 3)]
            assert abs(mass - independent[str(minute)][0]) < .000006
            assert abs(share - independent[str(minute)][2]) < .000006
            assert abs(wait+dwell-math.fsum(w*(a+b) for w,a,b,_ in trips)/mass) < 1e-7
            q = minute_mean(curve, times, minute)
            assert q >= -1e-6
            rows[stop].append([minute, round(mass, 8), round(wait, 3), round(dwell, 3),
                               round(max(0., q), 4), round(share, 6)])
        boarded = math.fsum(r[1] for r in rows[stop])
        vehicle_boardings = math.fsum(e[6] for e in data["events"] if e[1] == node)
        assert abs(boarded - vehicle_boardings) < 1e-5
        passenger_seconds = math.fsum(r[1] * r[3] for r in rows[stop])
        from_vehicles = math.fsum(w * (dep-t) for t,n,_,w,_,dep in data["preboard_events"] if n == node)
        assert abs(passenger_seconds - from_vehicles) <= max(1e-7, .00051 * boarded)
    return rows, supply


def build():
    common = read(MODEL / "viewer-data/common.json.gz")
    nodes = {stop: common["hot_nodes"][stop] for stop in STOPS}
    cases, schedules = {}, {}
    for service in ("regular", "peak"):
        for day in ("mon", "tue", "wed", "thu", "fri"):
            key = f"{service}-{day}"
            cases[key], schedules[key] = build_case(key, nodes)
    feed = dict(schema="snu-terminal-wait-v1", release="V"+MODEL.name, family="V12", timezone="Asia/Seoul",
                columns=COLUMNS, cases=cases, routes=STOPS, schedules=schedules,
                schedule_columns=["nominal_departure_second", "passenger_capacities_per_bus"],
                interpretation="Weighted simulation means conditional on boarding at this terminal. Both waits use the same riders. Physical queue entry includes the 20-second boarding preparation. Outside queue is a time average of all people waiting. Next dispatch groups vehicles departing at the same time. Sparse or missing cohorts do not imply zero wait.")
    (HERE / "routing-feed.json").write_text(json.dumps(feed, ensure_ascii=False, separators=(",",":" )), encoding="utf8")
    print("case count", len(cases), "minute cells", sum(len(v) for stops in cases.values() for v in stops.values()))


if __name__ == "__main__":
    build()
