"""Compare matched vehicle boardings, service checks and spillovers on each date."""
from collections import Counter
import csv
import importlib.util
from pathlib import Path
from statistics import mean
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PREV = ROOT / "261127173038"
spec = importlib.util.spec_from_file_location("evening_comparison", PREV / "compare.py")
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
rows, load = previous.csv_rows, previous.load
TARGET, NEAR = previous.STOPS
DATES = {"wed": ("20261111",), "thu": ("20261105","20261112","20261119")}
CASES = ("base","V12","prior","placebo","within","half","relocate")
METRICS = ("all","nak","snu","line_nak")
WINDOWS = ((12,16),(16,17),(17,18),(18,19),(19,20),(20,21),(18,21),(17,21),(21,23),(12,23))


def write(name, header, data):
    with (HERE/name).open("w",encoding="utf-8-sig",newline="") as out:
        writer = csv.writer(out)
        writer.writerow(header.split())
        writer.writerows(data)


def read_observations():
    obs = {(d,r["stop"],int(r["hour"]),r["metric"]): int(r["passengers"])
           for ds in DATES.values() for d in ds for r in rows(HERE/f"cards_{d}.csv")}
    earlier = previous.card_counts()
    for (d,s,h,m),v in earlier.items():
        if m in METRICS:
            assert obs.get((d,s,h,m),0)==v
    net = Counter({("20261111",r["stop"],int(r["hour"])):int(r["observed"])
                   for r in rows(HERE/"network_cards_20261111.csv")})
    frozen = rows(ROOT/"261127170244/목요일_38개정류장.csv")
    names = {}
    for r in frozen:
        if r["model"]=="joint_soft" and r["service"]=="peak":
            names[r["stop"]]=r["name"]
            net["20261105",r["stop"],int(r["hour"])]=int(r["measured"])
    assert len(names)==38
    return Counter(obs),net,names


def main():
    obs, net_obs, names = read_observations()
    common = load(ROOT/"261125170855/viewer-data/common.json.gz")
    campus = {s["stop_id"] for s in load(ROOT/"seoul_boardings_2026-11-10/stop_scope.json")["stops"]
              if s["zone"] in ("campus_core","campus_annex")}
    guard, cells, errors, network, audit, field, cohort = [], [], [], [], [], [], []
    for day,service in (("thu","peak"),("wed","peak"),("thu","regular")):
        key = f"{service}-{day}"
        for mode in CASES:
            stage = HERE/"runs"/mode/key
            if mode in ("V12","prior"):
                before = ROOT/"261127170244/runs/joint_soft"/key
                stage = before if mode=="prior" else ROOT/"261125170855/runs/candidate"/key
                people = {int(r["uid"]): dict(r,end_min=-99,start=r["old_start" if mode=="V12" else "start"])
                          for r in rows(before/"inputs.csv.gz")}
            elif mode=="base" and day=="thu":
                stage = PREV/"runs/short"/key
                people = {int(r["uid"]):r for r in rows(stage/"students.csv.gz")}
            else:
                if "--follow" in sys.argv:
                    until = time.monotonic()+480
                    while not (stage/"summary.json").is_file() and time.monotonic()<until:
                        time.sleep(2)
                people = {int(r["uid"]):r for r in rows(stage/"students.csv.gz")}
            summary = load(stage/"summary.json")
            for r in people.values():
                if r.get("activity")=="1":
                    r["end_min"]=-2
            pred,source = previous.extract(stage,key,"actual",people,common,campus)
            if mode=="base":
                baseline=pred
            if mode in ("base","placebo"):
                date_id="20261105" if day=="thu" else "20261111"
                for s in (TARGET,NEAR):
                    guard.append((day,service,mode,s,sum(obs[date_id,s,h,"all"] for h in range(24)),
                                  sum(obs[date_id,s,h,"all"] for h in range(12,23)),
                                  sum(pred[s,h,"all"] for h in range(12,23)),sum(pred[s,h,"all"] for h in range(24))))
            treat=load(stage/"treatment.json") if (stage/"treatment.json").exists() else {}
            flags=(summary["capacity_violations"],summary["unserved"],summary["over20_weight"],summary["max_continuous_wait"])
            upper_mass = sum(float(r["weight"]) for r in people.values() if r["building"] in ("300","301","302"))
            if "upper_actual" in summary:
                assert abs(upper_mass-summary["upper_actual"]["upper_mass"])<1e-6
            audit.append((day,service,mode,summary["daily"],upper_mass,treat.get("eligible",""),
                          treat.get("activity",0),treat.get("funding_other_evening",0),treat.get("max_halfhour_dest_delta",0),*flags))
            for name,o in summary["observations"].items():
                if o["kind"]=="outside":
                    field.append((day,service,mode,name,o["observed"][0],o["mean"],o["expected_abs_error"]))
            for s in (TARGET,NEAR):
                for h in range(12,23):
                    for m in METRICS:
                        for d in DATES[day]:
                            actual = obs[d,s,h,m]
                            p = pred[s,h,m]
                            cells.append((d,day,service,mode,s,h,m,actual,p,abs(p-actual),abs(p-actual)-abs(baseline[s,h,m]-actual)))
                for start,end in WINDOWS:
                    for label,measures in (("all",("all",)),("two",("nak","snu"))):
                        keys=[(d,h,m) for d in DATES[day] for h in range(start,end) for m in measures]
                        mae=mean(abs(obs[d,s,h,m]-pred[s,h,m]) for d,h,m in keys)
                        errors.append((day,service,mode,s,start,end,label,len(keys),mae))
            net_date="20261105" if day=="thu" else "20261111"
            for s,name in sorted(names.items()):
                for h in range(12,23):
                    actual=net_obs[net_date,s,h];p=pred[s,h,"outside"]
                    network.append((net_date,service,mode,s,name,h,actual,p,abs(actual-p),abs(actual-p)-abs(actual-baseline[s,h,"outside"])))
            for (b,end,h,m),v in source.items():
                if end==-2:
                    cohort.append((day,service,mode,b,h,m,v))
            print(key, mode, "verified", flush=True)
    write("정류장_카드대조.csv","date day service mode stop hour metric obs modeled abs_error delta_error",cells)
    write("오차요약.csv","day service mode stop from_hour to_hour metric cells MAE",errors)
    write("38곳_교외하차.csv","date service mode stop name hour obs modeled abs_error delta_error",network)
    write("운영검산.csv","day service mode daily upper eligible activity funding_elsewhere max_cell_delta capacity_violations unserved over20 max_wait_min",audit)
    write("실측대기줄.csv","day service mode observation obs modeled_mean minute_MAE",field)
    write("활동집단_제2공학관승차.csv","day service mode building hour metric modeled",cohort)
    write("전일_공통시간대.csv","day service mode stop card_day card_12to23 model_12to23 model_day",guard)


if __name__=="__main__":
    main()
