"""Research replay with a fixed campus and destination budget for upper-campus activity."""
import argparse
from collections import Counter
import csv
import gzip
import importlib.util
from math import isclose
from pathlib import Path
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
PREV = HERE.parent / "261127173038"
spec = importlib.util.spec_from_file_location("late_class_replay", PREV / "experiment.py")
late = importlib.util.module_from_spec(spec)
spec.loader.exec_module(late)
core = late.core
MODES = ("base", "placebo", "within", "relocate", "half")


def prepare(day, service, mode):
    key = f"{service}-{day}"
    out = HERE / "runs" / mode / key
    with TemporaryDirectory(dir=out) as tmp:
        late.HERE = Path(tmp)
        stage = late.HERE / "runs/short" / key
        stage.mkdir(parents=True)
        try:
            bundle, donors, stats, upper, reference = late.prepare(day, service, "short")
        finally:
            late.HERE = PREV
        with gzip.open(stage / "students.csv.gz","rt",encoding="utf8") as f:
            original = {int(r["uid"]):r for r in csv.DictReader(f)}
        archived = PREV / "runs/short" / key / "students.csv.gz"
        if archived.exists():
            with gzip.open(archived,"rt",encoding="utf8") as f:
                assert original == {int(r["uid"]):r for r in csv.DictReader(f)}
    courses = core.timing.ref.ref.class_events(core.timing.ref.load(core.timing.ref.ref.COURSES))
    plans = bundle["prepared"]["plans"][core.official.prior.DAYS[day]]
    dest = bundle["destination_keys"]
    common = bundle["prepared"]["common"]
    capacity, requested, early, old_dest, old_cells = Counter(), Counter(), Counter(), Counter(), Counter()
    fraction = 0.125 if mode == "half" else 0.25
    spatial = mode in ("relocate", "half")
    next_uid = max(map(int, bundle["walk_scales"])) + 1
    extra, origin = [], {}
    eligible = 0.
    for p in plans:
        uid, building, _, w, start, walk, stages = p
        parent = donors.get(uid,uid)
        course = courses[(parent-1)//48]
        destination = dest[str(uid)]
        cell = int(start//1800), destination
        old_dest[destination] += w
        old_cells[cell] += w
        if uid not in upper and destination != core.RAIL:
            capacity[cell] += w
        if (uid not in upper or destination == core.RAIL or course["degree_level"] != "석박사통합"
                or start >= 16*3600 or course["end_minute"] >= 16*60):
            continue
        eligible += w
        if mode == "base":
            continue
        activity_start = (17 + 4*core.timing.uniform(f"upper-activity-clock/{uid}"))*3600
        at = start if mode == "placebo" else activity_start
        amount = w*fraction
        extra.append([next_uid, building, p[2], amount, at, walk, stages])
        requested[int(activity_start//1800),destination] += amount
        early[uid] = amount
        origin[next_uid] = uid
        donors[next_uid] = parent
        bundle["walk_scales"][str(next_uid)] = bundle["walk_scales"][str(uid)]
        dest[str(next_uid)] = destination
        next_uid += 1
    if spatial:
        assert all(v < capacity[cell] for cell,v in requested.items())
    mass_before = sum(old_dest.values())
    for i,p in enumerate(plans):
        uid = p[0]
        cell = int(p[4]//1800), dest[str(uid)]
        reduction = early[uid] if not spatial else 0.
        if spatial and uid not in upper and requested[cell]:
            reduction = p[3] * (requested[cell] / capacity[cell])
        if reduction:
            assert 0 < reduction < p[3]
            plans[i] = [*p[:3],p[3]-reduction,*p[4:]]
    plans.extend(extra)
    upper.update(origin)
    new_cells, new_dest = Counter(), Counter()
    with gzip.open(out/"students.csv.gz","wt",encoding="utf8",newline="") as f:
        writer = csv.writer(f)
        writer.writerow(("uid","building","dest","weight","start","base_start","end_min","activity","template_uid"))
        for p in plans:
            uid, building, _, w, start, *_ = p
            d = dest[str(uid)]
            new_dest[d] += w
            new_cells[int(start//1800),d] += w
            template = origin.get(uid,uid)
            # A matching course supplies a physical route template. It does not
            # show that someone in the spatial activity cohort took that class.
            end = -1 if spatial and uid in origin else int(original[template]["end_min"])
            writer.writerow((uid,building,d,w,start,original[template]["start"],end,int(uid in origin),template))
            if d == core.RAIL:
                assert uid not in origin and w == float(original[uid]["weight"]) and start == float(original[uid]["start"])
    assert all(abs(new_dest[k]-v)<1e-6 for k,v in old_dest.items())
    if spatial or mode=="placebo":
        assert all(abs(old_cells[k]-new_cells[k])<1e-6 for k in set(old_cells)|set(new_cells))
    assert isclose(sum(new_dest.values()),mass_before,abs_tol=1e-6)
    stats["upper_r"] = sum(p[3] for p in plans if p[0] in upper)
    stats["first_target_r"] = sum(p[3] for p in plans if p[0] in upper and core.first_target(p,common))
    common["candidate_id"] = common["data_version"] = "R"+HERE.name
    core.save(out/"treatment.json",dict(eligible=eligible,activity=sum(p[3] for p in extra),
              funding_other_evening=sum(p[3] for p in extra) if spatial else 0.,before=mass_before,
              after=sum(new_dest.values()),max_halfhour_dest_delta=max(abs(new_cells[k]-old_cells[k]) for k in set(new_cells)|set(old_cells))))
    return bundle, donors, stats, upper, reference


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("day",choices=("wed","thu"))
    ap.add_argument("service",choices=("peak","regular"))
    ap.add_argument("mode",choices=MODES)
    a=ap.parse_args()
    core.HERE=HERE
    core.inputs=prepare
    core.run(a.day,a.service,a.mode)
