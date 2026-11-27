"""Compare realised passenger journeys with three Thursdays of card observations."""
from bisect import bisect_left
from collections import Counter
import csv
import gzip
import json
from math import isclose
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "261127170244"
SOURCE = HERE.parent / "evening_origin_2026-11-27"
DATES = ("20261105", "20261112", "20261119")
STOPS = ("120000173", "120000174")
DIRECTIONS = {"120900119": "nak", "120900110": "nak", "120000150": "snu"}
LINE = "120900011"
METRICS = ("all", "nak", "snu", "line_all", "line_nak")


def csv_rows(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf8") as f:
        return json.load(f)


def write(name, fields, rows):
    with (HERE / name).open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(fields.split())
        w.writerows(rows)


def card_counts():
    result = Counter()
    for day in DATES:
        for r in csv_rows(SOURCE / f"카드_{day}.csv"):
            direction, label = r["direction"], r["measure"]
            key = (day, r["boarding_stop"], int(r["hour"]))
            column = {"전체": "all", "낙성대": "nak", "서울대입구": "snu"}.get(direction)
            if label == "승차" and column:
                result[*key, column] = int(r["passengers"])
            if label == "노선" and direction in ("전체", "낙성대") and r["category"] == LINE:
                result[*key, "line_all" if direction == "전체" else "line_nak"] = int(r["passengers"])
    return result


def extract(folder, key, mode, students, net, campus):
    audit = load(folder / f"audit-{key}.json.gz")
    events = {}
    for sec, node, vehicle, _, _, _, board, *tail in audit["events"]:
        route, idx = tail[4:6]
        if route in net["city_route_stops"]:
            stop = net["city_route_stops"][route][idx]["id"]
            events[vehicle, node, sec] = (route, idx, stop, board)
    realised, counts, sources, mass = Counter(), Counter(), Counter(), Counter()
    for trip in audit["legs"]:
        student = students[trip["id"]]
        weight = trip["weight"]
        mass[trip["id"]] += weight
        start = float(student["base_start" if mode == "control" else "start"])
        assert isclose(trip["start"], start, abs_tol=1e-7)
        cohort = student["building"], int(student["end_min"])
        for leg in trip["legs"]:
            if leg[0] != 3:
                continue
            _, t, end, _, node, _, vehicle, *_ = leg
            k = vehicle, node, t
            if k not in events:
                continue
            route, idx, stop, _ = events[k]
            realised[k] += weight
            offsets = net["route_info"][route]["offsets"]
            pos = bisect_left(offsets, offsets[idx] + end - t - 1e-5)
            assert pos > idx and abs(offsets[pos] - offsets[idx] - (end - t)) < 1e-5
            alight_stop = net["city_route_stops"][route][pos]["id"]
            direction = DIRECTIONS.get(alight_stop)
            metrics = ["all"]
            if alight_stop not in campus:
                metrics.append("outside")
            if direction:
                metrics.append(direction)
            if route == LINE:
                metrics.append("line_all")
                if direction == "nak":
                    metrics.append("line_nak")
            h = int(t // 3600)
            for metric in metrics:
                counts[stop, h, metric] += weight
                if stop == STOPS[0] and 17 <= h <= 22:
                    sources[*cohort, h, metric] += weight
    assert mass.keys() == students.keys()
    assert all(abs(mass[k] - float(students[k]["weight"])) < 1e-6 for k in mass)
    assert all(abs(realised[k] - e[3]) < 1e-6 for k, e in events.items())
    return counts, sources


def main():
    measured = card_counts()
    net = load(HERE.parent / "261125170855/viewer-data/common.json.gz")
    scope = load(HERE.parent / "seoul_boardings_2026-11-10/stop_scope.json")
    campus = {s["stop_id"] for s in scope["stops"] if s["zone"] in ("campus_core", "campus_annex")}
    network_ref = [r for r in csv_rows(BASE / "목요일_38개정류장.csv") if r["model"] == "joint_soft"]
    report, fits, check, cohort, choices, network = [], [], [], [], [], []
    for service in ("peak", "regular"):
        key = f"{service}-thu"
        baseline_file = BASE / "runs" / "joint_soft" / key
        reference_counts = None
        reference_students = None
        for mode in ("control", "short", "long"):
            run = HERE / "runs" / mode / key
            has_replay = (run / "summary.json").is_file()
            if mode != "control" or service == "peak":
                assert has_replay, (mode, key)
            ledger = (run if has_replay else HERE / "runs/short" / key) / "students.csv.gz"
            students = {int(r["uid"]): r for r in csv_rows(ledger)}
            match = {uid: tuple(r[c] for c in ("building", "end_min", "dest", "weight", "base_start", "eligible", "picked")) for uid, r in students.items()}
            if reference_students is None:
                reference_students = match
            assert reference_students == match
            folder = run if has_replay else baseline_file
            counts, sources = extract(folder, key, mode, students, net, campus)
            if mode == "control":
                reference_counts = counts
                if has_replay:
                    frozen, _ = extract(baseline_file, key, mode, students, net, campus)
                    assert frozen == counts
            for row in network_ref:
                if row["service"] != service:
                    continue
                stop, h, obs = row["stop"], int(row["hour"]), int(row["measured"])
                base = reference_counts[stop, h, "outside"]
                assert abs(base - float(row["modeled"])) < 1e-6
                current = counts[stop, h, "outside"]
                network.append((service, mode, stop, row["name"], h, obs, base, current, abs(current-obs)-abs(base-obs)))
            summary = load(folder / "summary.json")
            assert abs(sum(float(r["weight"]) for r in students.values()) - summary["daily"]) < 1e-6
            assert all(summary[k] == 0 for k in ("over20_weight", "unserved", "capacity_violations"))
            groups = Counter()
            for r in students.values():
                w = float(r["weight"])
                delta = 0 if mode == "control" else (float(r["start"]) - float(r["base_start"])) / 60
                if mode != "control":
                    assert bool(delta) == bool(int(r["picked"]))
                if int(r["eligible"]):
                    groups[r["building"], r["end_min"], "eligible"] += w
                if delta:
                    groups[r["building"], r["end_min"], "moved"] += w
                    groups[r["building"], r["end_min"], "minutes_sum"] += w * delta
            for group in sorted({k[:2] for k in groups}):
                den = groups[*group, "moved"]
                choices.append((service, mode, *group, groups[*group, "eligible"], den, groups[*group, "minutes_sum"] / den if den else ""))
            check.append((service, mode, summary["daily"], sum(n for (*_, k), n in groups.items() if k == "eligible"),
                          sum(n for (*_, k), n in groups.items() if k == "moved"), summary["capacity_violations"],
                          summary["unserved"], summary["over20_weight"], summary["max_continuous_wait"]))
            cohort.extend((service, mode, *k, n) for k, n in sorted(sources.items()))
            for d in DATES:
                for stop in STOPS:
                    for h in range(18, 21):
                        for m in METRICS:
                            obs, pred = measured[d, stop, h, m], counts[stop, h, m]
                            err, old = abs(obs - pred), abs(obs - reference_counts[stop, h, m])
                            report.append((service, mode, d, stop, h, m, obs, pred, pred - obs, err, err - old))
            for stop in STOPS:
                for hours in ((18,), (19,), (20,), (18, 19, 20), (18, 19)):
                    for measures in (("nak", "snu"), ("all",)):
                        cells = [(d, h, m) for d in DATES for h in hours for m in measures]
                        mae = mean(abs(measured[d, stop, h, m] - counts[stop, h, m]) for d, h, m in cells)
                        fits.append((service, mode, stop, "+".join(map(str, hours)), "+".join(measures), len(cells), mae))
    write("실측대조.csv", "service condition date stop hour metric observed modeled bias abs_error delta_abs_error", report)
    write("오차요약.csv", "service condition stop hours metrics cells MAE", fits)
    write("운영검산.csv", "service condition daily eligible delayed capacity_violations unserved over20 max_wait_min", check)
    write("강좌별_체류.csv", "service condition building end_min eligible delayed mean_extra_min", choices)
    write("제2공학관_승차출처.csv", "service condition building end_min hour metric modeled", cohort)
    write("11월5일_38곳_교외하차대조.csv", "service condition stop name hour observed base modeled delta_abs_error", network)


if __name__ == "__main__":
    main()
