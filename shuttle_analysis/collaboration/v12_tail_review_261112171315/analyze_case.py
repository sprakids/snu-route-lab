"""Read an existing audit for one lineage; no simulated event is rerun."""
from pathlib import Path
from collections import defaultdict
import gzip
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent.parent
source = json.loads((ROOT/"case_evidence.json").read_text(encoding="utf-8"))


def close(a,b):
    assert abs(a-b)<2e-5, (a,b)


def distance(a,b):
    r=math.pi/180
    return 6371000*math.hypot((b[0]-a[0])*r,(b[1]-a[1])*r*math.cos((a[0]+b[0])/2*r))


summaries={};decision_details=[]
for label in ["new","previous"]:
    data=source[label];assert len(data["legs"])==1
    trip=data["legs"][0];durations=defaultdict(float)
    for leg in trip["legs"]: durations[leg[0]]+=leg[2]-leg[1]
    assert set(durations)<={0,1,3}
    close(sum(durations.values()),trip["finish_time"]-trip["start"])
    for a,b in zip(trip["legs"],trip["legs"][1:]): close(a[2],b[1])
    close(durations[1],trip["completed_wait_seconds"])
    prepare=sum(max(0.,min(w["ready"],w["end"])-w["arrival"]) for w in data["wait_audit"])
    pure=sum(max(0.,w["end"]-max(w["ready"],w["arrival"])) for w in data["wait_audit"])
    close(prepare+pure,durations[1])
    f=source["source_parent_walk_factor"] if data["config"].get("restore_source_walking_variation") else 1.
    walked=0.;walk_checks=[]
    for leg in trip["legs"]:
        if leg[0]!=0:continue
        path=source["used_physical_paths"][str(leg[3])];expected=path["seconds"]*f
        close(leg[2]-leg[1],expected);walked+=path["meters"]
        walk_checks.append({"path":leg[3],"meters":path["meters"],"actual_seconds":leg[2]-leg[1],"base_seconds":path["seconds"],"factor":f})
    summaries[label]={"duration_min":(trip["finish_time"]-trip["start"])/60,
        "walk_min":durations[0]/60,"stop_dwell_including_preparation_min":durations[1]/60,"ride_min":durations[3]/60,
        "preparation_within_stop_dwell_min":prepare/60,"after_ready_wait_min":pure/60,
        "maximum_continuous_stop_dwell_min":max(w["end"]-w["arrival"] for w in data["wait_audit"])/60,
        "walking_meters":walked,"route_changes":len(trip["history"]),"weight":trip["weight"],"walk_factor":f,
        "walk_checks":walk_checks}
    cfg=data["config"];traits=trip["traits"]
    for d in data["behavior_decisions"]:
        p=d["physical_prediction"];at=d["time"]
        close(p["eta"]-at,p["walk"]+p["wait"]+p["ride"]+p["prep"])
        past_wait=sum(max(0.,min(at,leg[2])-leg[1]) for leg in trip["legs"] if leg[0]==1 and leg[1]<=at)
        base=(p["ride"]+traits["walk"]*p["walk"]+traits["wait"]*(p["wait"]+p["prep"]))/60
        base+=traits["transfer"]*p["transfers"]+traits["change"]*(1+.5*d["change_count_before"])
        base+=traits["crowd"]*p["crowd_exposure"]/60+traits["fatigue"]*p["fatigue"]/60
        if cfg["fare_in_choice"]:base+=60*p["fare"]/traits["vot"]
        future=p["wait"]+p["prep"]
        quad=cfg.get("predicted_queue_curvature_coefficient",0.)*(2*past_wait*future+future*future)/cfg.get("predicted_queue_curvature_scale_seconds",600.)
        cube=(past_wait*past_wait*future+past_wait*future*future+future**3/3)/cfg.get("waiting_discomfort_age_scale_seconds",600.)**2 if cfg.get("integrate_future_wait_discomfort") else 0.
        burden=traits["wait"]*(quad+cube)/60
        close(base+burden,d["generalized_cost_minutes"])
        decision_details.append({"case":label,"time":at,"origin":d["origin"],"target":d["target"],"reason":d["reason"],
            "past_wait_seconds":past_wait,"physical_future_walk_min":p["walk"]/60,"physical_future_wait_prep_min":future/60,
            "base_generalized_cost_min":base,"extra_cumulative_wait_burden_min":burden,"selected_generalized_cost_min":d["generalized_cost_minutes"],
            "prediction_eta":p["eta"],"old_eta":d["old_eta"]})

# Retrospective queue/ready-flow check using the completed simulation audit.
# This is diagnostic evidence, not permitted future information for routing.
path=BASE/"261112171315/runs/release1p125-combined-regular-tue/attempt_01/audit-regular-tue.json.gz"
assert hashlib.sha256(path.read_bytes()).hexdigest()==source["provenance"]["input_hashes"]["new_audit"]
audit=json.loads(gzip.decompress(path.read_bytes()));waits=audit["wait_audit"]
projections=[]
for d in source["new"]["behavior_decisions"]:
    rows=d["physical_prediction"]["boarding_load_projections"]
    if not rows:continue
    p=rows[0];matches=[e for e in source["new"]["events_at_visited_nodes"] if e[2]==p["vehicle"] and e[12]==p["board_index"]]
    assert len(matches)==1
    event=matches[0];node=event[1];t0=d["time"];t1=event[0]
    close(t1,p["time"])
    service=[p["route"],p["board_index"]]
    eligible=[w for w in waits if w["node"]==node and service in w["eligibility"]]
    # These three flags are evaluated strictly before the future target event.
    active=lambda w,t:w["ready"]<=t<w["end"]
    before=sum(w["weight"] for w in eligible if active(w,t0))
    just_before=sum(w["weight"] for w in eligible if active(w,t1-1e-5))
    new_ready=sum(w["weight"] for w in eligible if t0<w["ready"]<t1 and w["ready"]<w["end"])
    exits=sum(w["weight"] for w in eligible if t0<w["end"]<t1 and w["ready"]<=w["end"])
    # t0 equality with a preceding vehicle event can include ordering effects;
    # report, rather than force, the remaining identity residual.
    residual=just_before-(before+new_ready-exits)
    personal=[w for w in source["new"]["wait_audit"] if w["node"]==node and w["arrival"]<=t1<=w["end"]+2e-3]
    declines=[r for r in source["new"]["boarding_choices"] if r["vehicle"]==p["vehicle"] and abs(r["time"]-t1)<1e-5]
    classification="voluntary_decline" if declines else "not_resolved"
    if not declines and personal and personal[0]["ready"]<=t1 and event[7]>=event[3]-1e-6:
        classification="target_vehicle_filled_before_this_lineage_boarded"
    projections.append({"decision_time":t0,"target_time":t1,"node":node,"vehicle":p["vehicle"],"route":p["route"],"board_index":p["board_index"],
        "predicted_known_entry_load":p["projected_after_self"],"reserved_capacity_proxy":p.get("unidentified_reserved_capacity"),
        "realized_simulated_event":event,"same_clock_as_forecast":True,
        "eligible_ready_queue_at_prediction":before,"eligible_ready_queue_before_vehicle":just_before,
        "eligible_becoming_ready_before_vehicle":new_ready,"eligible_exiting_before_vehicle":exits,
        "flow_identity_residual":residual,"lineage_outcome":classification,
        "is_measured_real_world_data":False})
del audit,waits
endpoint=source["used_path_geometry"][str(source["new"]["legs"][0]["legs"][-1][3])][-1]
visited=[]
for w in source["new"]["wait_audit"]:
    n=source["nodes"][w["node"]];visited.append({"node":w["node"],"name":n["name"],"ars":n.get("ars"),
        "lat":n["lat"],"lon":n["lon"],"straight_line_to_destination_m":distance([n["lat"],n["lon"]],endpoint)})
assert len({x["node"] for x in visited})==len(visited)
pair_distances=[]
for a,b in [(77,12),(92,88),(77,71)]:
    na,nb=source["nodes"][a],source["nodes"][b]
    pair_distances.append({"nodes":[a,b],"names":[na["name"],nb["name"]],"straight_line_m":distance([na["lat"],na["lon"]],[nb["lat"],nb["lon"]])})
latest=BASE/"261112171315/tail_regression_diagnosis_final.json"
latest_data=json.loads(latest.read_text(encoding="utf-8-sig"))
for rel,h in source["provenance"]["source_hashes"].items():assert hashlib.sha256((BASE/rel).read_bytes()).hexdigest()==h
differences={key:summaries["new"][key]-summaries["previous"][key] for key in ["duration_min","walk_min","stop_dwell_including_preparation_min","ride_min"]}
out=ROOT/"tail_diagnosis.json";assert not out.exists()
out.write_text(json.dumps({"status":"READ_ONLY_SINGLE_LINEAGE_DIAGNOSTIC_NOT_CAUSAL_ISOLATION","summaries":summaries,"duration_differences":differences,
    "selected_cost_reconstruction":decision_details,"forecast_targets_and_realized_flows":projections,
    "visited_nodes":visited,"nearby_different_node_pairs":pair_distances,
    "latest_peer_final_snapshot":latest_data,"latest_peer_final_sha256":hashlib.sha256(latest.read_bytes()).hexdigest(),
    "latest_peer_final_changed_since_intake":hashlib.sha256(latest.read_bytes()).hexdigest()!=source["provenance"]["input_hashes"]["peer_final_diagnostic"],
    "change_scope":"peer diagnostic labels corrected; diagnosis is recomputed from immutable audit0/1/3 legs",
    "source_files_unchanged":True,"new_date_outcomes_read":False,"simulator_rerun":False,"production_writes":False},ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"status":"READ_ONLY_SINGLE_LINEAGE_DIAGNOSTIC","new_duration_min":summaries["new"]["duration_min"],"selected_costs_reconstructed":len(decision_details),
    "capacity_missed_forecast_targets":sum(p["lineage_outcome"]=="target_vehicle_filled_before_this_lineage_boarded" for p in projections),
    "voluntarily_declined_forecast_targets":sum(p["lineage_outcome"]=="voluntary_decline" for p in projections)},ensure_ascii=False))
