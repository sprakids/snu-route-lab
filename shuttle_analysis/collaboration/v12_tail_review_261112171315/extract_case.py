"""Extract one existing simulated lineage; no simulator imports or execution."""
from pathlib import Path
import datetime
import gc
import gzip
import hashlib
import json

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent.parent
UID = 1205536
PARENT = 75346
SOURCES = [
    ("new", BASE/"261112171315", "release1p125-combined-regular-tue"),
    ("previous", BASE/"261112132736", "repair-combined-regular-tue"),
]


def read(p):
    return json.loads(gzip.decompress(p.read_bytes()) if p.suffix == ".gz" else p.read_bytes())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def matches(row):
    return isinstance(row, dict) and (row.get("uid") == UID or row.get("id") == UID)


records = {};input_hashes = {};source_hashes = {}
for label, folder, case in SOURCES:
    for n in ["prepare.py", "policy.py", "engine.py", "preferences.py", "config.json", "experiment_lock.json", "analyze_followup.py"]:
        source_hashes[f"{folder.name}/{n}"] = sha(folder/n)
    work = folder/"runs"/case/"attempt_01"
    path = work/"audit-regular-tue.json.gz";input_hashes[f"{label}_audit"] = sha(path)
    data = read(path)
    selected = [row for row in data["legs"] if row["id"] == UID]
    assert selected
    nodes = {int(leg[4]) for row in selected for leg in row["legs"] if leg[0] in (1, 2, 3) and int(leg[4]) >= 0}
    start = min(row["start"] for row in selected);end = max(row["finish_time"] for row in selected)
    record = {"case": case, "uid": UID, "source_parent": PARENT, "audit_section_counts": {k:len(v) for k,v in data.items() if isinstance(v,(list,dict))},
        "config": data["prototype_config"], "legs": selected, "policy_report": data["policy_report"]}
    for section in ["behavior_decisions", "boarding_choices", "review_diagnostics", "wait_audit"]:
        record[section] = [r for r in data.get(section, []) if matches(r)]
    record["switches"] = [r for r in data["switches"] if isinstance(r,list) and len(r)>3 and r[3]==UID]
    record["waits"] = [r for r in data["waits"] if len(r)>6 and r[6]==UID]
    used_vehicles = {int(leg[6]) for row in selected for leg in row["legs"] if leg[0]==3}
    used_vehicles.update(r["vehicle"] for r in record["boarding_choices"] if "vehicle" in r)
    record["events_at_visited_nodes"] = [r for r in data["events"] if r[1] in nodes and start<=r[0]<=end]
    event_vehicles = {r[2] for r in record["events_at_visited_nodes"]}
    record["relevant_vehicles"] = [r for r in data["vehicles"] if r["id"] in used_vehicles|event_vehicles]
    record["parent_mapping"] = data["parent_ids"][str(UID)]
    assert record["parent_mapping"] == PARENT and all(r["parent_id"]==PARENT for r in selected)
    records[label] = record
    del data;gc.collect()

folder = SOURCES[0][1]
amendment = read(folder/"pair_amendment.json")
path = folder/amendment["active_prepared"];input_hashes["frozen_prepared"] = sha(path);assert input_hashes["frozen_prepared"] == amendment["prepared_sha256"]
frozen = read(path)
records["source_parent_plan"] = next(p for p in frozen["prepared"]["plans"]["화"] if p[0] == PARENT)
records["source_parent_walk_factor"] = frozen["walk_scales"][str(PARENT)]
records["destination_key"] = frozen["destination_keys"][str(PARENT)]
records["nodes"] = frozen["prepared"]["common"]["nodes"]
pids = {int(leg[3]) for label in ["new", "previous"] for row in records[label]["legs"] for leg in row["legs"]}
records["used_path_geometry"] = {str(i): frozen["prepared"]["common"]["paths"][i] for i in pids}
del frozen;gc.collect()
path = folder/"physical_paths_e3e9b7863828.json.gz";input_hashes["physical_paths"] = sha(path)
physical = read(path);records["used_physical_paths"] = {str(i):physical[i] for i in pids};del physical
records["class_release"] = read(folder/"frozen/class_release_map.json.gz")["events"][(PARENT-1)//48]
final = folder/"tail_regression_diagnosis_final.json";input_hashes["peer_final_diagnostic"] = sha(final);records["peer_final_diagnostic"] = read(final)
for rel,h in source_hashes.items():assert sha(BASE/rel) == h
for label, folder, case in SOURCES:
    assert sha(folder/"runs"/case/"attempt_01/audit-regular-tue.json.gz") == input_hashes[f"{label}_audit"]
records["provenance"] = {"created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "input_hashes":input_hashes,
    "source_hashes": source_hashes, "candidate_source_files_unchanged": True, "audit_hashes_unchanged": True,
    "excluded_preliminary_tail_json": True, "new_date_observation_outcomes_read": False, "model_runs_started": False, "production_writes": False}
out = ROOT/"case_evidence.json";assert not out.exists();out.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"status":"EXTRACTED_EXISTING_CASE_ONLY", "uid":UID,
    "new_fragments":len(records["new"]["legs"]), "previous_fragments":len(records["previous"]["legs"]),
    "new_decisions":len(records["new"]["behavior_decisions"]), "source_factor":records["source_parent_walk_factor"],
    "destination":records["destination_key"]},ensure_ascii=False))
