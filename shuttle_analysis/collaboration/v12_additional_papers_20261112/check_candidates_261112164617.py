"""Read-only, AST-isolated checks; no simulator import, run, or candidate writes."""
from pathlib import Path
from types import ModuleType, SimpleNamespace
import ast
import bisect
import copy
import hashlib
import json
import math
import random
import sys

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent.parent
B = BASE / "261112164250"
C = BASE / "261112164617"
NAMES = ["prepare.py", "policy.py", "physics.py", "engine.py", "config.json", "run_case.py", "experiment_lock.json", "analyze_followup.py"]


def hashes():
    return {f"{p.name}/{n}": hashlib.sha256((p / n).read_bytes()).hexdigest() for p in [B, C] for n in NAMES}


before = hashes()


def definitions(path, wanted, ns):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    body = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in wanted]
    assert {node.name for node in body} == set(wanted)
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), ns)


env = {"math": math, "bisect": bisect, "EPS": 1e-7}
definitions(B / "engine.py", ["QueueView", "LiveMass", "stage_choice", "forecast_available", "boarding_projection", "indexed_boardable", "first_boardable", "scaled_stages"], env)


def leg(lines=("A",), path=1):
    rows = [{"rid": rid, "board": 0, "alight": 1, "next_walk": [path, 999.]} for rid in lines]
    return {**rows[0], "pool": rows} if len(rows) > 1 else rows[0]


def vehicle(vid, cap=44, retained=0., when=100., rid="A", quota=None):
    v = {"id": vid, "rid": rid, "cap": cap, "last_stop": -1, "times": [when, when+60], "onboard": [(1, {"w": retained})] if retained else []}
    if quota is not None:
        v["seat_history"] = {(rid, 0): [(0., quota), (10., quota)]}
    return v


def waiter(weight, lines=("A",)):
    return {"w": weight, "stage": 0, "stages": [leg(lines)]}


def first(fleet, waiting):
    rows = [(v["times"][0], v["id"], 0) for v in fleet]
    args = rows, fleet, 20., 20., leg(), 1., waiting
    legacy = env["first_boardable"](*args, indivisible=True)
    projected = env["first_boardable"](*args, indivisible=True, project_load=True)
    assert legacy == (None if projected is None else projected[:4])
    return projected


probes = []
for ahead, expected_vid, expected_load in [(0, 0, 1), (40, 0, 41), (43, 0, 44), (44, 1, 1), (66, 1, 23)]:
    result = first([vehicle(0), vehicle(1)], [waiter(ahead)])
    assert result[1] == expected_vid and result[4]["projected_after_self"] == expected_load
    probes.append({"ahead": ahead, "vehicle": result[1], "known_entry_load": result[4]["projected_after_self"]})
r = first([vehicle(0, retained=5., quota=3.)], [waiter(1.)])[4]
assert (r["known_retained_onboard"], r["known_ahead_boarded_here"], r["unidentified_reserved_capacity"], r["projected_after_self"], r["quota_implied_load_upper_proxy"]) == (5., 1., 36., 7., 43.)

# The isolated random fixtures exercise mixed compatible services and quotas.
# This seed is only for the test inputs, not a new passenger distribution.
check_rng = random.Random(20261112)
for case in range(150):
    waiting = [waiter(check_rng.choice([.5, 1., 2.]), check_rng.choice([("A",), ("B",), ("A", "B")])) for _ in range(check_rng.randrange(18))]
    patterns = sorted({tuple(s["rid"] for s in w["stages"][0].get("pool", [w["stages"][0]])) for w in waiting})
    cache = {"types": [{"indices": [], "prefix": [0.]} for _ in patterns], "type_at": [], "services": {}}
    for pos, w in enumerate(waiting):
        pat = tuple(s["rid"] for s in w["stages"][0].get("pool", [w["stages"][0]]));kind = patterns.index(pat)
        row = cache["types"][kind];row["indices"].append(pos);row["prefix"].append(row["prefix"][-1]+w["w"]);cache["type_at"].append(kind)
    for rid in ["A", "B"]:
        cache["services"][(rid, 0)] = [i for i, pat in enumerate(patterns) if rid in pat]
    fleet = []
    for i in range(5):
        cap = check_rng.choice([10, 44]);retained = check_rng.randrange(min(6, cap));quota = check_rng.choice([None, 1., 3., float(cap-retained)])
        fleet.append(vehicle(i, cap, retained, 100.+i*30, check_rng.choice(["A", "B"]), quota))
    rows = [(v["times"][0], v["id"], 0) for v in fleet];frozen = copy.deepcopy((fleet, waiting))
    args = rows, fleet, 20., 20., leg(("A", "B")), 1.
    direct = env["first_boardable"](*args, waiting, indivisible=True, project_load=True)
    indexed = env["first_boardable"](*args, env["QueueView"](cache, len(waiting)-1), indivisible=True, project_load=True)
    assert direct == indexed, (case, direct, indexed)
    assert (fleet, waiting) == frozen

# Call only the extracted prepare transformation, with all reads mocked and
# packed() intercepted. The candidate modules are never imported.
physical = [{"seconds": x, "meters": x, "stairs_meters": 0.} for x in [100., 70., 30.]]
source = {
    "prepared": {"common": {"paths": [[[37., 127.], [37.001, 127.001]]] * 3}, "plans": {"월": []}},
    "walk_scales": {"7": .8, "11": 1.2}, "destination_keys": {"7": "station", "11": "station"},
    "alternatives": {"x": [{"walk": [0, 999.], "stages": [leg()]}]},
    "compatible_single_stage_pools": {"x": [leg()]}, "compatible_route_policies": {"x": [leg()]},
}
for uid, mass in [(7, 2.5), (11, 1.5)]:
    stage = leg();stage["continuation_stages"] = [leg(("B",), path=2)]
    source["prepared"]["plans"]["월"].append([uid, "building", "station", mass, 0., [0, 999.], [stage]])


def read_fixture(path):
    if path.name == "prepared.json.gz": return copy.deepcopy(source)
    if path.name == "supply.json": return {}
    if path.name == "input_manifest.json": return {"prepared_sha256": "SYNTHETIC_FIXTURE_ONLY"}
    if path.name == "walking_osm.json": return {}
    raise AssertionError(path)


def verify_stages(rows, factor):
    for row in rows:
        assert math.isclose(row["next_walk"][1], physical[row["next_walk"][0]]["seconds"]*factor)
        for key in ["pool", "continuation_stages"]:
            if key in row: verify_stages(row[key], factor)


fake_engine = ModuleType("engine");fake_engine.scaled_stages = env["scaled_stages"]
saved_engine = sys.modules.get("engine")
sys.modules["engine"] = fake_engine
prepare_cases = []
try:
    for origin_choice in [False, True]:
        cfg = json.loads((C / "config.json").read_text(encoding="utf-8-sig"))
        cfg.update(origin_choice=origin_choice, physics="path_local_4p8", behavior="sequential", empirical_context=False, operations="baseline", max_synthetic_packet_weight=1)
        cache_requests = []
        ns = {"copy": copy, "math": math, "hashlib": hashlib, "json": json, "ROOT": ROOT/"UNCREATED_FIXTURE_ROOT", "read": read_fixture,
              "catalog": lambda *a: copy.deepcopy(physical), "packed": lambda *a: cache_requests.append(a[0])}
        definitions(C / "prepare.py", ["stage_key", "prepare"], ns)
        bundle = ns["prepare"]({"day": "월"}, cfg)
        assert len(bundle["prepared"]["plans"]["월"]) == 5
        assert math.isclose(sum(p[3] for p in bundle["prepared"]["plans"]["월"]), 4.)
        for plan in bundle["prepared"]["plans"]["월"]:
            parent = bundle["parent_ids"][str(plan[0])];factor = source["walk_scales"][str(parent)]
            assert bundle["walk_scales"][str(plan[0])] == factor
            assert math.isclose(plan[5][1], physical[plan[5][0]]["seconds"]*factor)
            verify_stages(plan[6], factor)
        for options in bundle["alternatives"].values():
            for op in options:
                assert op["walk"][1] == physical[op["walk"][0]]["seconds"];verify_stages(op["stages"], 1.)
        for key in ["compatible_single_stage_pools", "compatible_route_policies"]:
            for rows in bundle[key].values(): verify_stages(rows, 1.)
        if origin_choice:
            assert len(bundle["origin_catalog"]) == 1
            for options in bundle["origin_catalog"].values():
                assert len(options) == 1
                for op in options:
                    assert math.isclose(op["walk"][1], physical[op["walk"][0]]["seconds"]);verify_stages(op["stages"], 1.)
            tree = ast.parse((C / "policy.py").read_text(encoding="utf-8-sig"));method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "initial_choice")
            calls = []
            policy_env = {"bundle": bundle, "config": cfg, "paths": physical, "walking_weight": lambda x: 1.,
                          "choose": lambda candidates, *a: candidates[0], "scaled_stages": env["scaled_stages"], "signature": lambda rows: tuple((s["rid"], s["board"], s["alight"]) for s in rows), "strategy_taste_key": lambda *a: "fixed-fixture"}
            exec(compile(ast.Module(body=[method], type_ignores=[]), str(C/"policy.py"), "exec"), policy_env)
            def predict(*args, **kwargs): calls.append(args);return SimpleNamespace(eta=0.)
            self = SimpleNamespace(initial_choices=0, predict=predict, generalized=lambda *a: 0.)
            for p in bundle["prepared"]["plans"]["월"]:
                f = bundle["walk_scales"][str(p[0])];state = {"plan": copy.deepcopy(p), "stages": p[6], "factor": f}
                policy_env["initial_choice"](self, state, 0.)
                assert math.isclose(calls[-1][3], physical[p[5][0]]["seconds"]*f) and calls[-1][4] == f
                assert math.isclose(state["plan"][5][1], physical[p[5][0]]["seconds"]*f);verify_stages(state["stages"], f)
        prepare_cases.append({"origin_choice": origin_choice, "synthetic_pieces": 5, "mass": 4., "factor_once": True, "writes_intercepted": len(cache_requests)})
finally:
    if saved_engine is None: sys.modules.pop("engine", None)
    else: sys.modules["engine"] = saved_engine

after = hashes();assert before == after
out = ROOT / "candidate_checks_261112164617.json";assert not out.exists()
out.write_text(json.dumps({"status": "PASS_SCOPED_AST_FIXTURES", "scope": "pure_function_and_mocked_prepare_checks_not_a_simulation_run_or_field_validation",
    "projection_probes": probes, "retained5_reserved36_case": r, "mixed_service_list_indexed_cases": 150,
    "prepare_cases": prepare_cases, "source_hashes_before": before, "source_hashes_after": after,
    "candidate_files_unchanged": True, "candidate_modules_imported": False, "model_runs_started": False,
    "new_date_outcomes_read": False, "production_writes": False}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(json.dumps({"status": "PASS_SCOPED_AST_FIXTURES", "projection_examples": len(probes)+1, "mixed_service_cases": 150, "prepare_branches": len(prepare_cases), "source_files_unchanged": len(before)}))
