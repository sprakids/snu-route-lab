"""Replay observed November 24 returns while preserving the matched Tuesday demand."""
import argparse
from bisect import bisect_right
import contextlib
import json
import math
from pathlib import Path
import sys

from return_windows import HERE, matched_trips

BASE = HERE.parent/"261124160531"
sys.path.insert(0, str(BASE))
from timing_inputs import inputs, ref
from mechanism_check import summarize
from verify_candidate import check
import return_engine as engine


def times(row, variant):
    alo, ahi = row["arrival"]
    dlo, dhi = row["departure"]
    if variant == "narrow":
        return ahi, dlo
    if variant == "wide":
        return alo, dhi
    return (alo+ahi)/2, (dlo+dhi)/2


def vehicle_range(data, vehicle):
    start = 918*60
    records = [(t, total) for t, _, vid, _, total, _ in data["preboard_events"] if vid == vehicle]
    stamps = [t for t, _ in records]
    def load(t):
        i = bisect_right(stamps, t)-1
        return records[i][1] if i >= 0 else 0.
    values = [load(start)] + [w for t, w in records if start < t < start+60]
    return [min(values), max(values)]


def run(variant, service):
    out = HERE/"runs"/f"{service}-{variant}"
    out.mkdir(parents=True, exist_ok=True)
    bundle, _, donors, _ = inputs("화", service)
    visits = ref.load(HERE/"return_visits.json")["41843"]
    slots = engine.base.dispatches("shuttle-daehak", service)
    matches = matched_trips(visits, slots)
    schedule = {}
    for slot, row in matches.items():
        arrival, dep = times(row, variant)
        schedule[slot] = dict(arrival=arrival, departure=dep, vehicle=row["vehicle"])
    bundle["daehak_return_visits"] = schedule
    engine.WORK = engine.OUT = engine.base.OUT = out
    replay_file = out/f"{service}-tue.json.gz"
    audit_file = out/f"audit-{service}-tue.json.gz"
    if audit_file.is_file() and replay_file.is_file():
        data = ref.load(replay_file)
    else:
        with (out/"simulation.log").open("w", encoding="utf8") as log, contextlib.redirect_stdout(log):
            data = engine.simulate(bundle, "화", service)
    baseline = ref.load(BASE/"viewer-data"/f"{service}-tue.json.gz")
    assert data["report"]["input_weight"] == baseline["report"]["input_weight"] and data["report"]["capacity_violations"] == 0
    assert data["report"]["unserved_trip_weight"] == 0 and math.isclose(data["report"]["final_weight"], data["report"]["input_weight"], abs_tol=1e-6)
    assert check(bundle, service, "화", "tue", out, donors)["status"]=="PASS"
    events = lambda d: {(e[1],e[2],e[11],e[12]):(e[0],e[3]) for e in d["events"]}
    before, after = events(baseline), events(data)
    assert before.keys()==after.keys() and len(before)==len(baseline["events"])==len(data["events"])
    terminal = bundle["prepared"]["common"]["hot_nodes"]["admin_daehak"]
    vehicles = {int(dep):vid for n,vid,op,dep,cap in baseline["door_windows"] if n==terminal}
    changed = {vehicles[k]:row["departure"]-k for k,row in schedule.items()}
    for key,(old,cap) in before.items():
        new,newcap = after[key]
        assert newcap==cap and math.isclose(new,old+changed.get(key[1],0),abs_tol=1e-6)
    windows = {vid:(op,dep) for n,vid,op,dep,_ in data["door_windows"] if n==terminal}
    assert set(changed)=={int(key) for key in data["observed_return_vehicles"]}
    for slot,row in schedule.items():
        assert all(math.isclose(a,b,abs_tol=1e-6) for a,b in zip(windows[vehicles[slot]],(row["arrival"],row["departure"])))
    target = vehicles[920*60]
    assert windows[target][0] < 918*60 < 919*60 < windows[target][1]
    a = vehicle_range(data, target)
    measured_minute=summarize(data)
    earlier_minute=summarize(baseline)
    assert all(math.isclose(x,y,abs_tol=1e-5) for x,y in zip(a,measured_minute["daehak"]["inside_1518"]))
    result = dict(service=service,variant=variant,matched_departures=len(matches),windows=schedule,
                  observed_return_case_weight=data["report"]["input_weight"], unserved=0, capacity_violations=0,
                  validated_stop_events=len(after),baseline_1518=earlier_minute,replay_1518=measured_minute,
                  same_vehicle_1518=a,
                  simulated_load_at_departure=next(e[7] for e in data["events"] if e[1]==terminal and e[2]==target))
    ref.previous.SAVE(out/"comparison.json", result)
    print(service, variant, a, flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("variant", choices=["middle", "narrow", "wide"])
    p.add_argument("service", choices=["peak", "regular"])
    args=p.parse_args()
    run(args.variant,args.service)
