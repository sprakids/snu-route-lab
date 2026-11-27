"""Run a matched trial, or the frozen V13 weekday engine after model selection."""
from bisect import bisect_left
from collections import Counter, defaultdict
from functools import lru_cache
import argparse
import csv
import gzip
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
spec=importlib.util.spec_from_file_location("activity_reference",ROOT/"261127174022/run_activity.py")
activity=importlib.util.module_from_spec(spec)
spec.loader.exec_module(activity)
core=activity.core
PAIR=("120000173","120000174")
ENDS={"120900119":"nak","120900110":"nak","120000150":"snu"}
GRID={"r0":(0.,1.),"r20":(.2,1.),"r40":(.4,1.),"r20g10":(.2,1.10),"r40g10":(.4,1.10),"r40g20":(.4,1.20)}
VERSION="V"+HERE.name
RESULTS=HERE


def adjust_stops(b,plans,service,strength):
    common=b["prepared"]["common"]; routes=common["city_route_stops"]; infos=common["route_info"]
    paths=common["paths"]; scales=b["walk_scales"]; targets=Counter(); counts=Counter()
    with (ROOT/"261127162719/11월5일_두정류장_하차지.csv").open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            end=ENDS.get(r["alight_id"])
            if end:targets[r["route_id"],end,int(r["hour"]),r["board_id"]]+=int(r["measured"])
    pair_index={(rid,i):i+1 for rid,rr in routes.items() for i in range(len(rr)-1)
                if (rr[i]["id"],rr[i+1]["id"])==PAIR}
    pair_index.update({(rid,j):i for (rid,i),j in list(pair_index.items())})
    @lru_cache(maxsize=None)
    def departures(rid,i):
        info=infos[rid]
        offset=info.get("origin_to_modeled_first_stop_seconds",0)+info["offsets"][i]-info["offsets"][info["anchor"]]
        return [t+offset for t in sorted(core.E.planned_departures(info["plan"]))]
    catalog=defaultdict(dict); groups=defaultdict(list)
    for i,p in enumerate(plans):
        if len(p[6])!=1:continue
        s=p[6][0];rid=s["rid"];j=s["board"]
        if (rid,j) not in pair_index or s.get("pool") or s.get("continuation_stages"):continue
        end=ENDS.get(routes[rid][s["alight"]]["id"])
        if not end:continue
        dest=b["destination_keys"][str(p[0])]
        if dest!=end:continue
        catalog_key=(p[1],tuple(paths[p[5][0]][0]),dest,rid,s["alight"],tuple(paths[s["next_walk"][0]][-1]))
        catalog[catalog_key,j].setdefault((p[5][0],s["next_walk"][0]),p)
        times=departures(rid,j);v=bisect_left(times,p[4]+p[5][1]+20)
        if v==len(times):continue
        h=int(times[v]//3600)
        if 17<=h<21:
            a=routes[rid][j]["id"];counts[rid,end,h,a]+=p[3]
            if p[1] in core.UPPER:groups[rid,end,h].append((i,j,v,catalog_key))
    changed=Counter()
    for (rid,end,h),items in groups.items():
        # Triangular three-hour smoothing; 20 prior boardings shrink toward the model.
        obs=[sum(k*targets[rid,end,h+off,stop] for off,k in ((-1,.25),(0,.5),(1,.25))) for stop in PAIR]
        volume=sum(counts[rid,end,h,s] for s in PAIR)
        current=counts[rid,end,h,PAIR[0]]/volume
        step=strength*((obs[0]+20*current)/(sum(obs)+20)-current)
        for i,j,v,key in items:
            p=plans[i];upstream=routes[rid][j]["id"]==PAIR[0]
            if not step or (step>0)==upstream:continue
            prob=abs(step)/(current if upstream else 1-current)
            if core.timing.uniform(f"v13-stop/{p[0]}")>=prob:continue
            other=pair_index[rid,j];valid=[]
            for q in catalog.get((key,other),{}).values():
                f=scales[str(p[0])]/scales[str(q[0])]
                access=q[5][1]*f;times=departures(rid,other)
                if access>p[5][1]+300 or bisect_left(times,p[4]+access+20)!=v:continue
                # Same physical bus, same alighting stop and endpoint.
                if q[6][0]["next_walk"][1]*f>p[6][0]["next_walk"][1]+1e-5:continue
                valid.append((access*(1+b["grade_excess_ratio"][q[5][0]]),q[0],q,f))
            if valid:
                _,_,q,f=min(valid,key=lambda x:x[:2])
                plans[i]=[*p[:5],[q[5][0],q[5][1]*f],core.E.scaled_stages(q[6],f)]
                changed["to_first" if upstream else "to_second"]+=p[3]
    return changed


def adjust_origin(b,plans,donors,odds):
    courses=core.timing.ref.ref.class_events(core.timing.ref.load(core.timing.ref.ref.COURSES))
    ids=[(donors.get(p[0],p[0])-1)//48 for p in plans]
    mass=Counter()
    for p,k in zip(plans,ids):mass[k]+=p[3]
    funding=Counter();demand=Counter();moves=[]
    for p,k in zip(plans,ids):
        dest=b["destination_keys"][str(p[0])];bin_key=int(p[4]//1800),dest
        move=0.;donor=False
        if 17*3600<=p[4]<21*3600 and dest!=core.RAIL:
            if p[1]=="302":
                fraction=mass[k]/courses[k]["enrollment"]
                move=max(0.,p[3]*(odds/(1+(odds-1)*fraction)-1))
                demand[bin_key]+=move
            elif p[1] not in core.UPPER:
                funding[bin_key]+=p[3];donor=True
        moves.append((bin_key,move,donor))
    net=Counter();newmass=Counter();gain=0.
    for i,(p,k,(cell,move,donor)) in enumerate(zip(plans,ids,moves)):
        funded=min(demand[cell],funding[cell]*.999)
        change=(move*funded/demand[cell] if move else 0.)-(p[3]*funded/funding[cell] if donor and funded else 0.)
        if change:
            plans[i]=[*p[:3],p[3]+change,*p[4:]]
            assert plans[i][3]>0
        net[cell]+=change;newmass[k]+=plans[i][3];gain+=max(0.,change)
    assert max(map(abs,net.values()))<1e-6
    assert all(w<=courses[k]["enrollment"]+1e-6 for k,w in newmass.items())
    return gain


def prepare(day,service,mode):
    key=service+"-"+day;out=RESULTS/"runs"/mode/key
    selected=json.loads((HERE/"selection.json").read_bytes())["chosen"] if mode=="V13" else mode
    strength,odds=GRID[selected]
    with TemporaryDirectory(dir=out) as tmp:
        activity.HERE=Path(tmp)
        sub=activity.HERE/"runs/within"/key;sub.mkdir(parents=True)
        try:b,donors,stats,upper,ref=activity.prepare(day,service,"within")
        finally:activity.HERE=ROOT/"261127174022"
        with gzip.open(sub/"students.csv.gz","rt",encoding="utf8") as f: people={int(r["uid"]):r for r in csv.DictReader(f)}
    weekday=core.official.prior.DAYS[day];plans=b["prepared"]["plans"][weekday]
    shifted=adjust_origin(b,plans,donors,odds) if odds>1 else 0.
    changed=adjust_stops(b,plans,service,strength) if strength else {}
    for p in plans:people[p[0]]["weight"]=p[3]
    with gzip.open(out/"students.csv.gz","wt",encoding="utf8",newline="") as f:
        wr=csv.DictWriter(f,fieldnames=list(next(iter(people.values()))));wr.writeheader();wr.writerows(people.values())
    common=b["prepared"]["common"];common["candidate_id"]=common["data_version"]=VERSION if mode=="V13" else "R"+HERE.name
    stats["upper_r"]=sum(p[3] for p in plans if p[0] in upper)
    stats["first_target_r"]=sum(p[3] for p in plans if p[0] in upper and core.first_target(p,common))
    core.save(out/"settings.json",dict(selected=selected,stop_fraction=strength,odds=odds,origin_gain=shifted,**changed))
    if mode=="V13":
        # Day-specific paths, including any appended walking routes, must accompany each replay.
        with gzip.open(out/"common.json.gz","wt",encoding="utf8") as f:json.dump(common,f,ensure_ascii=False,separators=(",",":"))
    return b,donors,stats,upper,ref


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("day",choices=core.official.prior.DAYS);ap.add_argument("service",choices=("peak","regular"))
    ap.add_argument("mode",nargs="?",default="V13",choices=(*GRID,"V13"))
    ap.add_argument("--output",type=Path,help="Write runs to a separate directory for an independent rerun")
    args=ap.parse_args()
    RESULTS=args.output.resolve() if args.output else HERE
    core.HERE=RESULTS;core.inputs=prepare;core.run(args.day,args.service,args.mode)
