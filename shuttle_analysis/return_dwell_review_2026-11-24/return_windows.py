"""Build interval-censored terminal visits from consecutive polls of the same vehicle."""
import argparse
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime, time, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
DAY = date(2026, 11, 24)
KST = timezone(timedelta(hours=9))
MIDNIGHT = datetime.combine(DAY, time.min, KST).timestamp()
TERMINALS = {"41843": (3, 6), "41841": (4, 10)}


def extract(path):
    aliases = {}
    polls = defaultdict(list)
    with gzip.open(path, "rt", encoding="utf8") as stream:
        for line in stream:
            for item in json.loads(line)["routes"]:
                route = item["route"]
                if route not in TERMINALS:
                    continue
                value = item.get("value") or {}
                if "captured_at" not in value:
                    continue
                stamp = value["captured_at"] - MIDNIGHT
                if not 0 <= stamp < 16 * 3600 + 28 * 60 + 5:
                    continue
                samples = {}
                for vehicle in value.get("vehicles", []):
                    key = (route, vehicle["id"])
                    if key not in aliases:
                        aliases[key] = f"v{len(aliases)+1:02}"
                    pos = vehicle.get("position") or {}
                    if pos.get("segment_index") is not None:
                        samples[aliases[key]] = [pos["segment_index"], pos.get("at_stop_index") if pos.get("at_stop") else None]
                polls[route].append([round(stamp, 3), samples])
    for rows in polls.values():
        rows.sort(key=lambda row: row[0])
        assert all(b[0] > a[0] for a, b in zip(rows, rows[1:]))
    return {"day": DAY.isoformat(), "timezone": "Asia/Seoul", "source_archive_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "polls": polls}


def episodes(rows, route):
    terminal, size = TERMINALS[route]
    visits = []
    for tag in sorted({tag for _, samples in rows for tag in samples}):
        index = 1
        while index + 1 < len(rows):
            loc = rows[index][1].get(tag)
            if not loc or loc[1] != terminal:
                index += 1
                continue
            start = index
            index += 1
            while index < len(rows) and (rows[index][1].get(tag) or [None, None])[1] == terminal:
                index += 1
            if index == len(rows):
                break
            before = rows[start-1][1].get(tag)
            after = rows[index][1].get(tag)
            if not before or not after or before[0] != terminal-1 or after[0] not in (terminal, (terminal+1) % size):
                continue
            if any(rows[i][0]-rows[i-1][0] > 180 for i in range(start, index+1)):
                continue
            # Find the other terminal before this visit, without crossing a missing poll or another visit.
            other = None
            for j in range(start-1, -1, -1):
                stamp, samples = rows[j]
                position = samples.get(tag)
                if not position or position[1] == terminal or rows[j+1][0]-stamp > 180:
                    break
                if position[1] == 0:
                    other = stamp
                    break
            visits.append(dict(vehicle=tag, arrival=[rows[start-1][0], rows[start][0]],
                               departure=[rows[index-1][0], rows[index][0]], previous_other_terminal=other))
    return sorted(visits, key=lambda item: item["departure"][0])


def matched_trips(visits, clocks):
    """Assign a complete return only if both departure bounds identify one planned trip."""
    def nearest(t):
        return min(clocks, key=lambda x: abs(x-t))
    candidates = []
    for row in visits:
        lo, hi = row["departure"]
        slot = nearest(lo)
        if (row["previous_other_terminal"] is not None and slot == nearest(hi)
                and min(clocks) < slot < max(clocks)
                and row["arrival"][1] < lo):
            candidates.append((slot, row))
    multiplicity = Counter(slot for slot, _ in candidates)
    return {slot: row for slot, row in candidates if multiplicity[slot] == 1}


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--archive", type=Path)
    args = cli.parse_args()
    source = HERE/"terminal_polls.json.gz"
    if args.archive:
        packed = json.dumps(extract(args.archive), separators=(",", ":")).encode()
        source.write_bytes(gzip.compress(packed, mtime=0))
    with gzip.open(source, "rt") as f:
        data = json.load(f)
    visits = {r: episodes(rows, r) for r, rows in data["polls"].items()}
    (HERE/"return_visits.json").write_text(json.dumps(visits, indent=2), encoding="utf8")
