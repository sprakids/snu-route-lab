"""Select on four disclosed dates, then evaluate the locked model on two other dates."""
from collections import Counter
import csv
import importlib.util
import json
from pathlib import Path
from statistics import mean
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
PREV=ROOT/"261127174022"
spec=importlib.util.spec_from_file_location("activity_eval",PREV/"evaluate.py")
old=importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
load,rows=old.load,old.rows
MODES=("r0","r20","r40","r20g10","r40g10","r40g20")
RESERVED={"tue":("20261117",),"wed":("20261118",)}
scope=load(ROOT/"seoul_boardings_2026-11-10/stop_scope.json")["stops"]
campus={s["stop_id"] for s in scope if s["zone"] in ("campus_core","campus_annex")}
base_net=load(ROOT/"261125170855/viewer-data/common.json.gz")

def write(path,data):
    with (HERE/path).open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)

def store(name,obj):
    (HERE/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf8")

def predict(mode,day):
    key="peak-"+day
    if mode=="V12":
        folder=ROOT/"261125170855/runs/candidate"/key
        students={int(r["uid"]):dict(r,start=r["old_start"],end_min=-99) for r in rows(ROOT/"261127170244/runs/joint_soft"/key/"inputs.csv.gz")}
    else:
        folder=(PREV/"runs/within"/key if mode=="r0" and day in ("wed","thu") else HERE/"runs"/mode/key)
        students={int(r["uid"]):r for r in rows(folder/"students.csv.gz")}
    summary=load(folder/"summary.json")
    assert not any(summary[k] for k in ("capacity_violations","unserved","over20_weight"))
    assert abs(summary["daily"]-sum(float(r["weight"]) for r in students.values()))<1e-5
    return old.previous.extract(folder,key,"actual",students,base_net,campus)[0]

def metrics(pred,day,dates,obs,net,names):
    result=[]
    for d in dates:
        for start,end,kind,sites,measures in (
            (18,21,"primary",old.previous.STOPS,("nak","snu")),
            (18,21,"second",(old.TARGET,),("nak","snu")),
            (18,21,"first",(old.NEAR,),("nak","snu")),
            (12,23,"pair_full",old.previous.STOPS,("nak","snu")),
            (12,23,"other36",tuple(set(names)-set(old.previous.STOPS)),("outside",)),
        ):
            if kind=="other36" and not any(k[0]==d for k in net):continue
            errors=[]
            for s in sites:
                for h in range(start,end):
                    for m in measures:
                        actual=net[d,s,h] if m=="outside" else obs[d,s,h,m]
                        errors.append(abs(actual-pred[s,h,m]))
            result.append(dict(date=d,day=day,metric=kind,n=len(errors),MAE=mean(errors)))
    return result

def pooled(records,metric):
    days=sorted(set(r["day"] for r in records))
    return mean(mean(r["MAE"] for r in records if r["day"]==day and r["metric"]==metric) for day in days)

def fit():
    obs,net,names=old.read_observations()
    scores=[];full=[]
    for mode in MODES:
        m=[]
        for day,dates in old.DATES.items():
            m.extend(metrics(predict(mode,day),day,dates,obs,net,names))
        full.extend(dict(model=mode,**r) for r in m)
        scores.append(dict(model=mode,**{k:pooled(m,k) for k in ("primary","second","first","pair_full","other36")}))
    ref=scores[0]
    for s in scores:s["eligible"]=all(s[k]<=ref[k]+.25 for k in ("pair_full","other36"))
    chosen=min((r for r in scores if r["eligible"]),key=lambda r:r["primary"])["model"]
    write("fit.csv",scores);write("fit_by_date.csv",full)
    store("selection.json",dict(chosen=chosen,settings_compared=list(MODES),dates=old.DATES,held_out=RESERVED,
        objective="Equal-weight weekday mean absolute error at two stops x two destination areas x 18,19,20h. Guard: full-day pair and 36 other stops may increase by at most 0.25 per cell vs r0. Ties use grid order."))
    print("locked",chosen,flush=True)

def final():
    selection=load(HERE/"selection.json")
    obs,net,names=old.read_observations()
    for dates in RESERVED.values():
        for d in dates:
            for r in rows(HERE/f"holdout_{d}.csv"):
                s,h,m,v=r["stop"],int(r["hour"]),r["metric"],int(r["observed"])
                if m=="outside":net[d,s,h]=v
                else:obs[d,s,h,m]=v
    out=[];cells=[]
    for mode in ("V12","r0","V13"):
        for day in ("tue","wed","thu"):
            p=predict(mode,day)
            for sample,ds in (("fit",old.DATES.get(day,())),("holdout",RESERVED.get(day,()))):
                out.extend(dict(model=mode,sample=sample,**r) for r in metrics(p,day,ds,obs,net,names))
                for d in ds:
                    for s in old.previous.STOPS:
                        for h in range(12,23):
                            for m in ("nak","snu","all"):
                                a=obs[d,s,h,m];v=p[s,h,m]
                                cells.append(dict(model=mode,sample=sample,date=d,stop=s,hour=h,direction=m,observed=a,predicted=v,absolute_error=abs(a-v)))
    write("validation.csv",out);write("boardings.csv",cells)
    result={sample:{m:{k:pooled([r for r in out if r["sample"]==sample and r["model"]==m],k)
        for k in ("primary","first","second","pair_full","other36")} for m in ("V12","r0","V13")} for sample in ("fit","holdout")}
    write("weekday_checks.csv",check_days())
    path=ROOT/"261125170855/comparison_20261127/accuracy"
    sys.path.insert(0,str(path))
    import check_r_regressions as check
    fields=[]
    for s in ("peak","regular"):
        fields.extend(check.field_rows([HERE/"runs"],"V13",s,*(rows(path/n) for n in ("queue.csv","departures.csv","personal.csv"))))
    write("field.csv",fields)
    store("validation.json",dict(selection=selection["chosen"],errors=result))
    print(json.dumps(result,indent=1),flush=True)

def check_days():
    result=[]
    for d in ("mon","tue","wed","thu","fri"):
        for s in ("peak","regular"):
            key=f"{s}-{d}";folder=HERE/"runs/V13"/key
            r=load(folder/"summary.json")
            assert abs(r["daily"]-load(ROOT/"261125170855/runs/candidate"/key/"summary.json")["daily"])<1e-6
            assert not any(r[k] for k in ("capacity_violations","unserved","over20_weight"))
            common=load(folder/"common.json.gz")
            assert common["data_version"]=="V"+HERE.name
            result.append(dict(day=d,service=s,**{k:r[k] for k in ("daily","capacity_violations","unserved","over20_weight","max_continuous_wait")}))
    return result

if __name__=="__main__":
    {"fit":fit,"final":final}[sys.argv[1]]()
