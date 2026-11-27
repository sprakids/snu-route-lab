"""Combine the three dates and reconcile the November 5 counts with the prior study."""
import csv
from collections import Counter
from math import isclose
from pathlib import Path

HERE = Path(__file__).resolve().parent
STOP = "120000173"
LINE = "120900011"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def summary(date):
    counts = Counter()
    for row in read(HERE / f"카드_{date}.csv"):
        if row["boarding_stop"] == STOP and row["hour"] == "19":
            counts[row["direction"], row["measure"], row["category"]] += int(row["passengers"])
    result = {"날짜": date}
    for scope in ("전체", "낙성대", "서울대입구"):
        result[scope] = counts[scope, "승차", "계"]
    result["관악02-1 전체 승차"] = counts["전체", "노선", LINE]
    result["관악02-1 낙성대 지정 정류장 하차"] = counts["낙성대", "노선", LINE]
    for place in ("제2공학관", "제1공학관", "그 외 교내", "그 외 버스·철도", "앞선 태그 없음", "불확실"):
        result[f"직전 {place}"] = counts["전체", "직전하차", place]
    for scope in ("낙성대", "서울대입구"):
        result[f"{scope} 승객 중 직전 제2공학관"] = counts[scope, "직전하차", "제2공학관"]
    result["직전 교내 하차 후 6시간 이상"] = counts["전체", "직전교내하차_간격", "6시간 이상"]
    result["직전 교내 하차 후 3시간 이상"] = result["직전 교내 하차 후 6시간 이상"] + counts["전체", "직전교내하차_간격", "3~6시간"]
    result["19시45분 이전"] = sum(counts["전체", "승차15분", str(minute)] for minute in (0, 15, 30))
    return result


if __name__ == "__main__":
    days = [summary(date) for date in ("20261105", "20261112", "20261119")]
    first = days[0]
    saved = read(HERE.parent / "261127162719" / "11월5일_두정류장_하차지.csv")
    od = [r for r in saved if r["board_id"] == STOP and r["hour"] == "19"]
    assert sum(int(r["measured"]) for r in od) == first["전체"]
    assert sum(int(r["measured"]) for r in od if r["route_id"] == LINE) == first["관악02-1 전체 승차"]
    reference = read(HERE.parent / "261127170244" / "목요일_두역방면.csv")
    boardings = [r for r in read(HERE / "모형_19시_승객의_수업출발지.csv") if r["model"] == "체류·거리별 접근 R"]
    for row in reference:
        if (row["model"], row["service"], row["stop"], row["hour"]) != ("joint_soft", "peak", STOP, "19"):
            continue
        key = row["metric"]
        if key in ("nak", "snu"):
            assert int(row["measured"]) == first[{"nak": "낙성대", "snu": "서울대입구"}[key]]
            assert isclose(sum(float(r[key]) for r in boardings), float(row["modeled"]))
    totals = {"날짜": "합계", **{key: sum(r[key] for r in days) for key in first if key != "날짜"}}
    with (HERE / "19시_날짜별_요약.csv").open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(first))
        writer.writeheader()
        writer.writerows([*days, totals])
    print(totals)
