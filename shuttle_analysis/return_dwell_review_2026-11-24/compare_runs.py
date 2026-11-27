"""Publish the 15:18 and surrounding-hour comparison once the four runs verify."""
import csv
import gzip
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def write_summary():
    rows = []
    for service,variant in (("peak","narrow"),("peak","middle"),("peak","wide"),("regular","middle")):
        run = HERE/"runs"/f"{service}-{variant}"
        values = json.loads((run/"comparison.json").read_text(encoding="utf8"))
        with gzip.open(run/f"audit-{service}-tue.json.gz","rt",encoding="utf8") as f:
            waits = json.load(f)["wait_audit"]
        volume = sum(r["weight"] for r in waits if r["node"]==42 and 910*60<=r["physical_stop_entry"]<919*60)
        longest = max((r["end"]-r["physical_stop_entry"])/60 for r in waits)
        over20 = sum(r["weight"] for r in waits if r["end"]-r["physical_stop_entry"]>1200+1e-6)
        clock = {float(slot): pair for slot,pair in values["windows"].items()}[920*60]
        before = values["baseline_1518"]["daehak"]
        after = values["replay_1518"]["daehak"]
        rows.append(dict(service=service,variant=variant,arrival_minute=clock["arrival"]/60,
            departure_minute=clock["departure"]/60,matched_departures=values["matched_departures"],
            old_onboard_min=before["inside_1518"][0],old_onboard_max=before["inside_1518"][1],
            onboard_min=values["same_vehicle_1518"][0],onboard_max=values["same_vehicle_1518"][1],
            load_at_simulated_departure=values["simulated_load_at_departure"],
            model_platform_entries_1510_1519=volume,
            old_mean_outside_1448_1548=before["outside_hour_mean"],new_mean_outside_1448_1548=after["outside_hour_mean"],
            old_mean_inside_1448_1548=before["inside_hour_mean"],new_mean_inside_1448_1548=after["inside_hour_mean"],
            daily_demand=values["observed_return_case_weight"],capacity_violations=values["capacity_violations"],
            unserved=values["unserved"],max_outside_wait_minutes=longest,over_20_outside_wait_weight=over20))
    with (HERE/"비교_결과.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(row["service"],row["variant"],*[round(row[k],2) for k in ("onboard_min","onboard_max",
              "load_at_simulated_departure","model_platform_entries_1510_1519")])


if __name__=="__main__":
    write_summary()
