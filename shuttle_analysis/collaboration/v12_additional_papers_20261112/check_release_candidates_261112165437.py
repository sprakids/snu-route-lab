"""Verify frozen class lineage and isolate the lag transform; never run a model."""
from pathlib import Path
from collections import Counter
import ast
import datetime
import gzip
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent.parent
MODELS = [BASE / "261112165437", BASE / "261112165438"]
FILES = ["prepare.py", "analyze_followup.py", "config.json", "experiment_lock.json", "input_manifest.json", "run_case.py", "future_evaluation_plan.json"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


before = {f"{b.name}/{n}": digest(b/n) for b in MODELS for n in FILES}
b = MODELS[0]
meta = read(b/"frozen/class_release_map.json.gz")
course_source = read(b/"frozen/class_endings_source_20261106.json")
events = [{"section_id": x["section_id"], "weekday": x["weekday"], "building": x["building"],
           "class_end_seconds": x["end_minute"]*60, "enrollment": x["enrollment"]}
          for x in course_source if x["included_main"] and x["weekday"] in ["월", "화", "수", "목", "금"]]
assert len(course_source) == 7503 and len(events) == 6201 and events == meta["events"]
source_path = b/"frozen/prepared_capacity44_pair.json.gz"
source_digest = digest(source_path)
assert source_digest == meta["parent_prepared_sha256"]
assert digest(b/"frozen/class_endings_source_20261106.json") == meta["source_sha256"]
bundle = read(source_path)
source_plans = bundle["prepared"]["plans"]
seen = set();per_event = Counter();by_day = Counter();lag_min = math.inf;lag_max = -math.inf
for day, plans in source_plans.items():
    for p in plans:
        uid = p[0];assert uid not in seen;seen.add(uid)
        event_index = (uid-1)//48;event = events[event_index]
        assert event["weekday"] == day and event["building"] == p[1]
        lag = p[4]-event["class_end_seconds"]
        assert 60 <= lag <= 480
        per_event[event_index] += 1;by_day[day] += 1
        lag_min = min(lag_min, lag);lag_max = max(lag_max, lag)
assert len(seen) == 297648 and seen == set(range(1, 297649))
assert len(per_event) == len(events) and set(per_event.values()) == {48}

# Run just the added statement block. No prepare module import, physical path
# preparation, split operation, or simulator is invoked.
tree = ast.parse((b/"prepare.py").read_text(encoding="utf-8-sig"))
prepare = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "prepare")
block = next(n for n in prepare.body if isinstance(n, ast.If) and "cohort_release_lag_scale" in ast.unparse(n.test))
code = compile(ast.Module(body=[block], type_ignores=[]), str(b/"prepare.py"), "exec")
transform_checks = []
for alpha in [.5, .75, 1.]:
    total = 0;minimum = math.inf;maximum = -math.inf;largest_time_change = 0.;mass_before = mass_after = 0.
    for day, originals in source_plans.items():
        plans = [list(p) for p in originals]
        ns = {"config": {"cohort_release_lag_scale": alpha}, "ROOT": b,
              "read": lambda path: meta, "sha": lambda path: source_digest,
              "amendment": {"active_prepared": "frozen/prepared_capacity44_pair.json.gz"}, "plans": plans, "day": day}
        exec(code, ns)
        for old, new in zip(originals, plans):
            # Expected end is reconstructed from frozen source course rows,
            # rather than accepting the simulator's transformed clock.
            end = events[(old[0]-1)//48]["class_end_seconds"]
            want = end+alpha*(old[4]-end)
            assert new[4] == want and new[4] >= end and new[4] <= old[4]
            assert new[:4] == old[:4] and new[5:] == old[5:]
            minimum = min(minimum, new[4]-end);maximum = max(maximum, new[4]-end)
            largest_time_change = max(largest_time_change, old[4]-new[4])
            total += 1;mass_before += old[3];mass_after += new[3]
        assert originals[0][4] == source_plans[day][0][4]
    assert total == 297648 and mass_before == mass_after
    transform_checks.append({"alpha": alpha, "parent_rows": total, "departure_not_before_class_end": True,
        "min_new_lag_seconds": minimum, "max_new_lag_seconds": maximum,
        "maximum_advance_seconds": largest_time_change, "only_departure_field_changed": True,
        "total_scenario_mass_preserved": mass_after})
for invalid in [0., -.5, 1.01]:
    p = source_plans["월"][0]
    ns = {"config": {"cohort_release_lag_scale": invalid}, "ROOT": b, "read": lambda path: meta,
          "sha": lambda path: source_digest, "amendment": {"active_prepared": "frozen/prepared_capacity44_pair.json.gz"},
          "plans": [list(p)], "day": "월"}
    try:
        exec(code, ns)
    except AssertionError:
        pass
    else:
        raise AssertionError(("invalid alpha accepted", invalid))

receipt_checks = [];hash_checks = [];lock_summaries = []
for model in MODELS:
    manifest = read(model/"input_manifest.json")
    for row in manifest["frozen"]:
        if "class_" in row["path"]:
            assert digest(model/row["path"]) == row["sha256"]
    assert digest(model/"frozen/prepared_capacity44_pair.json.gz") == source_digest
    assert digest(model/"frozen/class_release_map.json.gz") == digest(b/"frozen/class_release_map.json.gz")
    future = read(model/"future_evaluation_plan.json")
    for name, want in future["frozen_sha256"].items():
        assert digest(model/name) == want, (model.name, name)
    hash_checks.append({"model": model.name, "future_registered_hashes_verified": len(future["frozen_sha256"])})
    lock = read(model/"experiment_lock.json");cfg = read(model/"config.json")
    assert lock["calibrated_parameter"]["value"] == cfg["cohort_release_lag_scale"]
    lock_summaries.append({"model": model.name, "alpha": cfg["cohort_release_lag_scale"],
        "selection_rule": lock["selection_rule"], "comparison_parent": lock["comparison_parent"],
        "future_evaluation_rules": future["evaluation_rules"], "production_replacement_allowed": lock["production_replacement_allowed"]})
    for p in sorted((model/"runs").glob("*/attempt_01/started.json")):
        if not p.parent.parent.name.endswith(("regular-mon", "regular-tue")): continue
        receipt = read(p)
        assert all(digest(model/name) == h for name, h in receipt["code_sha256"].items())
        assert receipt["config"]["cohort_release_lag_scale"] == cfg["cohort_release_lag_scale"]
        receipt_checks.append({"model": model.name, "case": p.parent.parent.name,
            "alpha": receipt["config"]["cohort_release_lag_scale"], "source_manifest_matches_current": True})

after = {f"{p.name}/{n}": digest(p/n) for p in MODELS for n in FILES};assert before == after
out = ROOT/"release_candidate_checks_261112165437.json";assert not out.exists()
out.write_text(json.dumps({"status": "PASS_FROZEN_LINEAGE_AND_ISOLATED_TIME_TRANSFORM", "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "scope": "raw_frozen_course_to_synthetic_parent_lineage_and_AST_lag_statement_only_not_a_model_run",
    "source_course_rows": len(course_source), "eligible_weekday_events": len(events), "source_parent_rows": len(seen),
    "parents_per_event": 48, "by_weekday": dict(by_day), "original_lag_seconds_range": [lag_min, lag_max],
    "transform_checks": transform_checks, "invalid_alphas_rejected": [0., -.5, 1.01],
    "registered_hash_checks": hash_checks, "receipts": receipt_checks, "lock_summaries": lock_summaries,
    "source_hashes_before": before, "source_hashes_after": after, "source_files_unchanged": True,
    "simulator_imported": False, "model_runs_started": False, "new_date_observation_outcomes_read": False,
    "candidate_performance_recomputed": False, "production_writes": False}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(json.dumps({"status": "PASS_FROZEN_LINEAGE_AND_ISOLATED_TIME_TRANSFORM", "course_events": len(events),
    "parents": len(seen), "alpha_controls": len(transform_checks), "receipts": len(receipt_checks),
    "registered_hashes": [x["future_registered_hashes_verified"] for x in hash_checks], "protected_sources": len(before)}))
