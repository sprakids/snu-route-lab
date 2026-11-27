"""Matched Thursday replays of later departure after upper-campus evening classes."""
import argparse
import csv
import gzip
import importlib.util
import shutil
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "261127170244"
spec = importlib.util.spec_from_file_location("evening_access_reference", BASE / "run.py")
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
core = prior.core
DELAYS = {"control": (0, 0), "short": (30, 60), "long": (60, 120)}


def prepare(day, service, condition):
    key = f"{service}-{day}"
    out = HERE / "runs" / condition / key
    # The earlier experiment writes intermediate files inside its own working
    # directory. Point that directory at an isolated copy of its lookup table.
    with tempfile.TemporaryDirectory(dir=out) as scratch:
        scratch = Path(scratch)
        (scratch / "runs" / "joint_soft" / key).mkdir(parents=True)
        shutil.copyfile(BASE / "access_paths.json", scratch / "access_paths.json")
        prior.HERE = scratch
        try:
            bundle, donors, stats, upper, reference = prior.prepare(day, service, "joint_soft")
        finally:
            prior.HERE = BASE
        with gzip.open(scratch / "runs" / "joint_soft" / key / "inputs.csv.gz", "rb") as current:
            with gzip.open(BASE / "runs" / "joint_soft" / key / "inputs.csv.gz", "rb") as frozen:
                assert current.read() == frozen.read(), "Input differs from archived matched control"
    courses = core.timing.ref.ref.class_events(core.timing.ref.load(core.timing.ref.ref.COURSES))
    plans = bundle["prepared"]["plans"][core.official.prior.DAYS[day]]
    low, high = DELAYS[condition]
    with gzip.open(out / "students.csv.gz", "wt", encoding="utf8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("uid", "building", "end_min", "dest", "weight", "base_start", "start", "eligible", "picked"))
        for i, plan in enumerate(plans):
            uid, building, _, weight, start, walk, stages = plan
            owner = donors.get(uid, uid)
            course = courses[(owner - 1) // 48]
            end = course["end_minute"]
            dest = bundle["destination_keys"][str(uid)]
            eligible = uid in upper and dest != core.RAIL and 1080 < end < 1200 and start <= (end + 30) * 60
            picked = eligible and core.timing.uniform(f"late-class-stay/select/{owner}") < 0.25
            minutes = (low + (high - low) * core.timing.uniform(f"late-class-stay/minutes/{owner}")) if picked else 0
            later = start + 60 * minutes
            if minutes:
                assert later < core.E.END
                plans[i] = [*plan[:4], later, walk, stages]
            writer.writerow((uid, building, end, dest, weight, start, later, int(eligible), int(picked)))
    common = bundle["prepared"]["common"]
    common["candidate_id"] = common["data_version"] = "R" + HERE.name
    return bundle, donors, stats, upper, reference


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("condition", choices=DELAYS)
    parser.add_argument("service", choices=("regular", "peak"))
    args = parser.parse_args()
    core.HERE = HERE
    core.inputs = prepare
    core.run("thu", args.service, args.condition)
