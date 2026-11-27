"""Render the paired Thursday comparison from the verified output tables."""
import csv
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent
TARGET = "120000173"
DATES = ("20261105", "20261112", "20261119")
MODES = ("control", "short", "long")
SERVICES = ("peak", "regular")
LABELS = {"all": "전체 승차", "nak": "낙성대 직행", "snu": "서울대입구역 직행"}
MODE_LABELS = ("기존 R", "30~60분", "60~120분")


def rows(name):
    with (HERE / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def table(headings, body):
    def line(columns):
        return "| " + " | ".join(map(str, columns)) + " |"
    return "\n".join([line(headings), line(["---"] * len(headings)), *map(line, body)])


def main():
    observed, predicted = {}, {}
    for r in rows("실측대조.csv"):
        if r["stop"] == TARGET:
            h, m = int(r["hour"]), r["metric"]
            observed[r["date"], h, m] = int(r["observed"])
            predicted[r["service"], r["condition"], h, m] = float(r["modeled"])
    total_body = []
    for h in (18, 19, 20):
        for m, title in LABELS.items():
            total_body.append((f"{h}~{h+1}시", title, *(observed[d, h, m] for d in DATES),
                               *(f"{predicted['peak', mode, h, m]:.2f}" for mode in MODES)))
    fits = {(r["service"], r["condition"], r["stop"], r["hours"], r["metrics"]): float(r["MAE"])
            for r in rows("오차요약.csv")}
    fit_body = []
    for service in SERVICES:
        for stop, place in ((TARGET, "제2"), ("120000174", "제1")):
            for hours, window in (("19", "19~20시"), ("18+19+20", "18~21시")):
                fit_body.append(("피크" if service == "peak" else "기준", place, window,
                                 *(f"{fits[service,mode,stop,hours,'nak+snu']:.2f}" for mode in MODES)))
    checks = rows("운영검산.csv")
    chosen = next(r for r in checks if r["service"] == "peak" and r["condition"] == "short")
    def focus(mode, h, m):
        return sum(float(r["modeled"]) for r in sources if (r["service"], r["condition"], r["building"], r["end_min"], r["hour"], r["metric"])
                   == ("peak", mode, "302", "1095", str(h), m))
    sources = rows("제2공학관_승차출처.csv")
    focus_body = [(h, *(f"{focus(mode,h,'all'):.2f}" for mode in MODES)) for h in (18, 19, 20, 21)]
    late_obs = rows("../261127162719/11월5일_두정류장_하차지.csv")
    late_body = []
    for h in (21, 22):
        real = sum(int(r["measured"]) for r in late_obs if r["board_id"] == TARGET and int(r["hour"]) == h)
        forecast = [sum(float(r["modeled"]) for r in sources if
                        (r["service"],r["condition"],r["hour"],r["metric"]) == ("peak",mode,str(h),"all")) for mode in MODES]
        late_body.append((f"{h}~{h+1}시", real, *(f"{n:.2f}" for n in forecast)))
    net = rows("11월5일_38곳_교외하차대조.csv")
    net_body = []
    for service in SERVICES:
        for code, name in (("pair", "제1·제2공학관"), ("other", "나머지 36곳")):
            values = []
            for mode in MODES:
                errors = [abs(float(r["modeled"])-int(r["observed"])) for r in net
                          if (r["service"],r["condition"]) == (service,mode) and 18 <= int(r["hour"]) < 21 and
                          ((r["stop"] in (TARGET, "120000174")) == (code=="pair"))]
                assert len(errors) == (6 if code=="pair" else 108)
                values.append(f"{mean(errors):.2f}")
            net_body.append(("피크" if service=="peak" else "기준", name, *values))
    head = ("배차", "정류장", "시간", *MODE_LABELS)
    base19, short19, long19 = [predicted["peak",mode,19,"all"] for mode in MODES]
    gap = mean(observed[d,19,"all"] for d in DATES) - base19
    shift18 = predicted["peak","short",18,"all"] - predicted["peak","control",18,"all"]
    fit18 = [fits["peak",mode,TARGET,"18+19+20","nak+snu"] for mode in MODES]
    sections = [
        "# 윗공대 저녁 수업 후 체류 실험 R261127173038",
        "기준은 연구 R261127170244의 체류·거리별 접근 결합 조건이다. 목요일의 하루 하교 통행 16,517건을 그대로 두고 건물 출발 시각만 바꿔, 제2공학관 19시대 승차를 앞뒤 시간과 함께 비교했다.",
        f"**30~60분 체류가 19시 한 시간에는 더 잘 맞았고, 저녁 세 시간의 두 역 방면 오차는 두 조건 모두 소폭 커졌다.** 피크 배차에서 19시 전체 승차는 {base19:.2f}건에서 {short19:.2f}건으로 늘어 세 목요일 평균과 기존 모형 사이 격차의 {(short19-base19)/gap:.1%}를 줄였다. 18시 승차는 {abs(shift18):.2f}건 줄어 이미 부족한 시간대의 격차가 커졌다. 두 역 방면 18~21시 MAE는 기존 {fit18[0]:.2f}건, 짧은 체류 {fit18[1]:.2f}건, 긴 체류 {fit18[2]:.2f}건이다. 30~60분 조건은 체류 시각을 검증하기 위한 연구 후보로 보관한다. 다음에 구분할 대상은 마지막 수업 종료 후 남았던 승객과 그날 수업 없이 연구·근무 등으로 윗공대에 있던 승객의 실제 비중이다. [현장조사표](../evening_origin_2026-11-27/현장조사표.md)",
        "## 어떤 학생의 출발을 늦췄는가",
        f"300·301·302동에서 18:00을 지나 20:00 전에 종료하는 수업 중 원래 종료 후 30분 이내 또는 일찍 출발하는 집단을 대상으로 했다. 20시 이후 종료 수업은 19시 승차의 원인을 시험하는 이번 범위 밖이다. 관악산역 도달 시각에 별도 조건이 있는 신림선 집단은 기존 출발 시각을 썼다. 대상 {float(chosen['eligible']):.2f}명 상당에게 25%의 선택 확률을 적용했으며 이번 추첨에서는 {float(chosen['delayed']):.2f}명이 선정됐다. 같은 사람에게 원래 건물 출발 시각부터 30~60분 또는 60~120분을 더했다. 어떤 시간이 실제 분포인지 보여주는 직접 관측은 없다.",
        "두 체류 조건은 같은 학생과 동일한 난수 순위를 사용한다. 하루 인원·개인별 목적지·최초 계획·차량 시각·정원이 같고, 늦어진 도착 이후 대기·재선택·승차는 사건 순서에 따라 다시 계산했다. 목요일 피크 배차는 지연 0분 조건도 재실행해 기존 R의 승차 원장 집계와 대조했다. 기준 배차의 비교군은 보관한 기존 R 원장을 읽었다. 두 배차에서 입력을 생성할 때마다 직전 연구의 개인별 입력 파일과 비교했다. [실험 코드](experiment.py) · [강좌별 적용 인원과 평균 추가 체류](강좌별_체류.csv)",
        "## 날짜별 카드 승차와 피크 배차의 예측",
        table(("시간대", "제2공학관 지표", "11월 5일", "11월 12일", "11월 19일", *MODE_LABELS), total_body),
        "실측은 제2공학관 21275번에서 승차한 유료 버스 승객이다. 낙성대는 같은 차량에서 낙성대역·낙성대입구에 내린 승객, 서울대입구역은 같은 차량에서 역 2번 출구에 내린 승객이다. 전체에는 다른 곳에 내린 승객도 포함된다. 소수점은 모의 통행 가중치다. 11월 19일은 수능일이다. 세 날짜 모두 가설을 세울 때 이미 확인한 자료이므로 외부 검증 표본으로 해석할 수 없다. 카드는 학생 신분·귀가 목적·출발 건물을 알려주지 않는다. [서울시·티머니 원자료](https://t-data.seoul.go.kr/dataprovide/trafficdataviewfile.do?data_id=20006) · [세 날짜 자료의 출처와 집계 기준](../evening_origin_2026-11-27/README.md)",
        "## 두 역 방면 승차의 오차",
        "각 날짜·정류장·승차 시간대·하차 방면에서 예측과 카드 집계 차이의 절댓값을 구하고 동등하게 평균했다. 19~20시 평균절대오차(MAE)는 정류장 한 곳당 6칸, 18~21시는 18칸으로 계산한다. 두 역 방면 지표는 각 방향 한 번씩만 더한다.",
        table(head, fit_body),
        "일부 체류 학생이 21시 이후에 탈 가능성도 있어 11월 5일 전일 카드 원표로 제2공학관 전체 승차를 추가 대조했다. 아래는 피크 배차다.",
        table(("제2공학관 전체", "11월 5일", *MODE_LABELS), late_body),
        "## 302동 18:15 종료 두 강좌에서 생성된 제2공학관 실제 모의 승차",
        table(("승차 시각대", *MODE_LABELS), focus_body),
        "건물 출발이 늦어진 뒤 해당 정류장에서 실제 차량을 탄 인원을 원장에서 합산했다. 이 두 강좌의 수강편람 등록은 97명이다. 실측 카드에는 강좌 정보가 없어 이 표의 출발지별 예측을 직접 채점할 수 없다. [정류장 승차의 출발지별 결과](제2공학관_승차출처.csv)",
        "## 주변 정류장과 운영 검산",
        "11월 5일 18~21시에 같은 차량으로 교외에서 하차한 승객을 기준으로 한 정류장·시간당 MAE다. 첫 표의 두 역 이외의 교외 하차도 포함한다.",
        table(("배차", "정류장", *MODE_LABELS), net_body),
        f"두 배차와 세 조건 모두 하루 하교 16,517건 상당을 보존했다. 정원 초과·미완료·한 정류장 연속 대기 20분 초과는 모두 0건이다. 전체 조건 최장 연속 대기는 {max(float(r['max_wait_min']) for r in checks):.2f}분이었다. 학생별 승차를 차량 사건별 승차 인원과 대조하고, 차량 정원·운행시각과 FIFO도 기존 엔진의 독립 검사로 확인했다. [운영 검산](운영검산.csv) · [38개 정류장](11월5일_38곳_교외하차대조.csv)",
        "## 재현",
        "연구용 Python으로 이 폴더의 experiment.py에 조건(short 또는 long)과 배차(peak 또는 regular)를 전달한다. 무처치 피크 배차는 control peak로 실행한다. 다섯 실행이 끝나면 compare.py, report.py 순서로 집계·검산·문서 생성을 재현할 수 있다. [비교 코드](compare.py) · [관악02-1 전체 및 두 정류장 일대일 실측 대조](실측대조.csv) · [오차 집계](오차요약.csv)",
    ]
    (HERE/"README.md").write_text("\n\n".join(sections)+"\n", encoding="utf8")


if __name__ == "__main__":
    main()
