"""Look up a measured hour and the matching simulated boardings, without any optional packages."""
import argparse
import csv
from pathlib import Path

HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("date",nargs="?",default="20261118")
parser.add_argument("hour",nargs="?",type=int,default=18)
args=parser.parse_args()
groups={}
with (HERE/"boardings.csv").open(encoding="utf-8-sig",newline="") as f:
    for row in csv.DictReader(f):
        if row["date"]!=args.date or int(row["hour"])!=args.hour or row["direction"]=="all":continue
        k=(row["stop"],row["direction"])
        group=groups.setdefault(k,{"observed":int(row["observed"])})
        group[row["model"]]=float(row["predicted"])
if not groups:
    parser.error("수집한 날짜와 12~22시 중 한 시간을 입력해 주세요.")
print(f"{args.date} {args.hour:02}:00~{args.hour+1:02}:00 · 피크 배차 · 실제 승차시각")
for (s,d),r in sorted(groups.items()):
    stop={"120000173":"제2공학관","120000174":"제1공학관"}[s]
    direction={"nak":"낙성대","snu":"서울대입구"}[d]
    print(f"{stop} → {direction} | 카드 {r['observed']}건 | V12 {r['V12']:.1f}건 | V13 {r['V13']:.1f}건 | V13 절대오차 {abs(r['V13']-r['observed']):.1f}건")
