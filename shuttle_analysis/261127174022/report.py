from collections import defaultdict
import csv
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent
TARGET, NEAR = "120000173","120000174"
MODES = ("V12","prior","base","placebo","within","half","relocate")
LABEL = dict(V12="정식 V12",prior="체류·거리별 접근 R",base="직전 R · 30~60분",placebo="집단 분할만", within="윗공대 낮 출발을 저녁으로",
             half="저녁 출발 권역 재배분 · 절반",relocate="저녁 출발 권역 재배분")
DATES={"thu":["20261105","20261112","20261119"],"wed":["20261111"]}


def read(name):
    with (HERE/name).open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def table(header, rows):
    def line(data):
        return "| "+" | ".join(map(str,data))+" |"
    return "\n".join([line(header),line(["---"]*len(header)),*map(line,rows)])


def main():
    errors={(r["day"],r["service"],r["mode"],r["stop"],int(r["from_hour"]),int(r["to_hour"]),r["metric"]):float(r["MAE"]) for r in read("오차요약.csv")}
    observed, modeled = {}, {}
    for r in read("정류장_카드대조.csv"):
        h=int(r["hour"])
        observed[r["date"],r["stop"],h,r["metric"]]=int(r["obs"])
        modeled[r["day"],r["service"],r["mode"],r["stop"],h,r["metric"]]=float(r["modeled"])
    def err(day,mode,start=18,end=21,s=TARGET,svc="peak",metric="two"):
        return errors[day,svc,mode,s,start,end,metric]
    net=defaultdict(list)
    network_rows=read("38곳_교외하차.csv")
    for r in network_rows:
        h=int(r["hour"])
        if 18<=h<21 and r["stop"] not in (TARGET,NEAR):
            net[r["date"],r["service"],r["mode"]].append(float(r["abs_error"]))
    def spill(date,mode):
        xs=net[date,"peak",mode]
        assert len(xs)==108
        return mean(xs)
    check=read("운영검산.csv")
    guard={(r["day"],r["service"],r["mode"]):r for r in check}
    display=[]
    for m in MODES:
        display.append([LABEL[m],*(f"{x:.2f}" for x in (err("thu",m),err("wed",m),err("thu",m,12,23),err("wed",m,12,23),spill("20261105",m),spill("20261111",m)))])
    hour_rows=[]
    for day,day_ko in (("thu","목"),("wed","수")):
        for h in (18,19,20):
            for metric,label in (("all","전체"),("nak","낙성대 직행"),("snu","서울대입구역 직행")):
                actual=[observed[d,TARGET,h,metric] for d in DATES[day]]
                obs=" / ".join(map(str,actual))
                hour_rows.append((day_ko,h,label,obs,*(f"{modeled[day,'peak',m,TARGET,h,metric]:.2f}" for m in ("base","within","half","relocate"))))
    baseline=read("전일_공통시간대.csv")
    daily=[(r["day"],"제2" if r["stop"]==TARGET else "제1",r["card_day"],r["card_12to23"],f"{float(r['model_12to23']):.1f}") for r in baseline if r["service"]=="peak" and r["mode"]=="base"]
    comparisons=[]
    for m in ("base","placebo","within","half","relocate"):
        comparisons.append((LABEL[m],*(f"{x:.2f}" for x in (err("thu",m,12,16),err("wed",m,12,16),
                     err("thu",m,s=NEAR),err("wed",m,s=NEAR),err("thu",m,svc="regular")))))
    fields=read("실측대기줄.csv")
    fieldtable=[(LABEL[r["mode"]],r["obs"],f"{float(r['modeled_mean']):.2f}",f"{float(r['minute_MAE']):.2f}") for r in fields if "1600" in r["observation"]]
    wt=guard["thu","peak","relocate"]; ww=guard["wed","peak","relocate"]
    worst=[]
    for date in ("20261105","20261111"):
        group=[r for r in network_rows if r["date"]==date and r["service"]=="peak" and
               r["mode"]=="relocate" and 18<=int(r["hour"])<21 and r["stop"] not in (TARGET,NEAR)]
        for r in sorted(group,key=lambda x:float(x["delta_error"]),reverse=True)[:2]:
            worst.append((date,r["name"],r["hour"],r["obs"],f"{float(r['modeled']):.2f}",f"{float(r['delta_error']):+.2f}"))
    t=read("활동집단_제2공학관승차.csv")
    cohort=[]
    for day in DATES:
        for mode in ("within","relocate"):
            for h in (18,19,20):
                cohort.append((day,LABEL[mode],h,*(f"{sum(float(r['modeled']) for r in t if (r['day'],r['service'],r['mode'],int(r['hour']),r['metric'])==(day,'peak',mode,h,m)):.2f}" for m in ("all","nak","snu"))))
    physical=[r for r in check if r["mode"] in ("base","placebo","within","half","relocate")]
    contents=[
        "# 윗공대 저녁 활동 수요 실험 R261127174022",
        "18~21시 제2공학관 승차가 부족한 이유를 시험하기 위해 같은 규모의 저녁 통행을 윗공대 낮 통행에서 옮길 때와, 이미 저녁에 일어나던 통행의 출발 권역을 옮길 때를 비교했다. 대조군은 직전 R261127173038의 30~60분 조건이다. 모형을 만들 때 사용한 세 목요일과 새로 확보한 11월 11일 수요일의 승하차를 별도로 채점했다.",
        "**후속 연구에는 윗공대 안에서 낮 출발 일부를 저녁으로 옮기는 조건(within)을 남긴다.** 같은 수의 저녁 활동 통행을 넣으면 출발 권역을 재배분해도 제2공학관의 저녁 승차는 거의 같다. 반면 낮부터 저녁까지 비교하면 within이 두 요일 모두 두 역 방면 오차를 가장 많이 줄였고, 다른 권역에서 수요를 일괄 감액할 필요도 없다. 경로 표본을 나누기만 한 대조군은 18~21시 두 방면 오차가 직전 R과 같았다. 이 판단은 통행 시간 분포에 관한 연구 후보 선택이며, 연구·근무 인구의 규모를 식별한 결과로 사용할 수 없다.",
        "남은 문제는 제1공학관과 역 방면별 차이다. within 조건에서 제1공학관 저녁 오차가 두 요일 모두 증가했다. 수요일 19시대 제2공학관→서울대입구역도 실측 38건에 기존 50.49건, 변경 57.58건으로 과대예측이 커졌다. 다음 보정 때에는 출발 총량을 추가로 키우기 전에, 같은 노선·하차 방면에서 제1공학관과 제2공학관 중 어디서 타는지를 별도 날짜 자료로 검증하는 것이 우선이다.",
        "## 실험 가정",
        f"윗공대 300·301·302동의 석박사통합 과정 강좌에서 수업 종료와 기존 모의 출발이 모두 16시 이전이며 신림선 예약 집단에 속하지 않는 통행은 목요일 {float(wt['eligible']):.2f}명, 수요일 {float(ww['eligible']):.2f}명 상당이었다. 그 가중치의 25%(목 {float(wt['activity']):.2f}명, 수 {float(ww['activity']):.2f}명)를 시나리오 규모로 삼았다. 새 활동 종료 시각은 17:00 이상 21:00 미만에서 균등하게 배정했다. 수강편람의 과정 구분은 출발 건물·경로의 표본을 얻는 데 사용했다. 실제 대학원생 인구나 연구실 퇴실 시각 분포는 관측되지 않았다.",
        table(("조건","기존 통행에서 어떤 부분을 옮겼나"),[
            (LABEL["placebo"],"해당 가중치를 별도 집단으로 나누되 출발 시각·건물·경로는 원래대로 뒀다. 통행 집단을 나눌 때 생기는 수치 효과를 확인했다."),
            (LABEL["within"],"같은 건물·목적지·경로를 유지하고 윗공대에서 16시 이전에 출발하던 몫을 17~21시로 옮겼다. 윗공대의 하루 인원은 같다."),
            (LABEL["relocate"],"윗공대의 낮 통행을 보존하고, 다른 건물에서 이미 같은 저녁 30분대·목적지로 출발하는 통행들의 가중치를 비례 감액했다. 그 합만큼 윗공대 활동 통행에 배정했다. 캠퍼스 전체의 30분대·목적지별 인원이 같다."),
            (LABEL["half"],"권역 재배분 규모만 12.5%로 줄였다. 같은 경로·시각 표본에 절반 가중치를 적용했다.")]),
        "두 전량 조건은 같은 건물·같은 도보 경로·같은 최초 노선 계획과 속도·같은 저녁 출발 시각을 갖는 집단을 투입했다. 실제 경로 변경·승차·만차 대기는 운행 엔진에서 다시 계산했다. 권역 재배분 조건의 활동 인원은 특정 강좌의 학생으로 세지 않는다. 수업과 무관한 활동 수요가 어느 권역에 있는지에 관한 가설이며, 실제 교직원·대학원생 인원이나 출발동을 추정한 값은 아니다. 하루 총량과 목적지별 인원 및 신림선 출발 수요는 보존했다. [실행 코드](run_activity.py) · [운영 검산](운영검산.csv)",
        "## 실제로 하루에 얼마나 타는가",
        "두 날짜의 버스 카드 전일 승차와 두 자료의 공통 비교가 가능한 12~23시를 나란히 놓았다. 목은 11월 5일, 수는 11월 11일이다. 모의 하교 승객과 카드에 잡히는 전체 이용객은 모집단이 다르다. 제1공학관도 함께 비교해야 인접 승차지로 수요를 옮겨 생긴 개선을 확인할 수 있다.",
        table(("요일","승차지","전일 카드","12~23시 카드","12~23시 직전 R"),daily),
        "## 세 목요일과 별도 수요일의 두 역 방면 오차",
        "단위는 정류장·시간·방면 한 칸당 평균절대오차(건)다. 낙성대역·낙성대입구와 서울대입구역 2번 출구에 같은 버스로 도달한 두 방향을 한 번씩 계산했다. 피크 배차 기준이다. 나머지 36곳은 11월 5일과 11일 18~21시에 승차해 같은 차량으로 교외 하차한 승객 수의 정류장·시간당 오차다.",
        table(("모형","제2 목 18~21시","제2 수 18~21시","제2 목 12~23시","제2 수 12~23시","다른 36곳 목","다른 36곳 수"),display),
        "## 인접 정류장·낮 시간대·기준 배차",
        table(("조건","제2 목 12~16시","제2 수 12~16시","제1 목 18~21시","제1 수 18~21시","제2 목 18~21시 기준 배차"),comparisons),
        "권역 전량 재배분 후 다른 36곳의 18~21시 교외행 승차 중 오차 증가가 가장 큰 두 칸을 날짜별로 확인했다. 평균에 가려지는 역효과를 보기 위한 표다.",
        table(("날짜","정류장","시작 시","실측","예측","직전 R 대비 절대오차 증감"),worst),
        "## 날짜별 제2공학관 승차",
        "카드는 목요일에 11월 5·12·19일 순서, 수요일에 11월 11일 값을 표시했다. 11월 19일은 수능일이다. 소수는 가중치가 있는 모의 승차다. 낙성대와 서울대입구역의 두 열은 지정 정류장까지의 직접 승하차다.",
        table(("요일","시작 시","승차","카드","직전 R","낮→저녁","권역 절반","권역 전량"),hour_rows),
        "![시간대별 승차 건수와 직전 R 대비 증감](제2공학관_승차.png)",
        "## 새 저녁 집단 중 실제 제2공학관에서 탄 사람",
        table(("요일","조건","시작 시","전체 승차","낙성대 직행","설입 직행"),cohort),
        "## 현장 대기줄과 운행 검사",
        "11월 25일 수요일 16:00 행정관 설입 셔틀 바깥줄 관측에 같은 수요일 피크 시뮬레이션을 대조했다. 분 안의 초가 알려지지 않았으므로 분 평균과 분 내 시간가중 절대오차를 함께 봤다.",
        table(("모형","실측 인원","분 평균 예측","분 내 절대오차"),fieldtable),
        f"직전 R 및 신규 조건별 최대 정원 위반 {max(float(r['capacity_violations']) for r in physical):g}건, 미완료 {max(float(r['unserved']) for r in physical):g}명, 한 정류장 연속 20분 초과 {max(float(r['over20']) for r in physical):g}명, 최장 연속 대기 {max(float(r['max_wait_min']) for r in physical):.2f}분이다. 개인별 통행 질량과 차량별 승·하차 사건, 운행 시각, 정원, 선착순 승차를 검산했다. [시간대·방면별 오차](정류장_카드대조.csv) · [38개 정류장별 파급](38곳_교외하차.csv) · [현장 관측 비교](실측대기줄.csv)",
        "## 자료와 재현",
        "서울시·티머니 승하차 원본의 날짜·정류장·승하차 방향을 확인하고 승객 수를 합산했다. 11월 11일 개별 노선 승하차 자료는 이번 활동 조건을 정한 뒤 대조했다. 수요일 한 날로 다른 요일의 효과까지 단정할 수 없다. 카드에 수강 강좌·직전 출발 건물·통행 목적은 없다. [서울시·티머니 원자료](https://t-data.seoul.go.kr/dataprovide/trafficdataviewfile.do?data_id=20006) · [수요일 원본 파일 정보](source_20261111.json) · [서울대 수강편람과 건물별 집계](../evening_origin_2026-11-27/README.md)",
        "연구용 Python에서 cards.py, wednesday_network.py로 카드 집계를 재현한다. run_activity.py에 요일(wed 또는 thu), 배차(peak 또는 regular), 조건(base·placebo·within·half·relocate)을 전달한다. 목요일 기준·피크, 수요일 피크를 비교하며 목요일 base는 검증된 직전 원장을 읽는다. evaluate.py, report.py, plot.py 순서로 비교표·보고서·그래프를 만든다. plot.py에는 Matplotlib가 필요하다. [평가 코드](evaluate.py) · [모형별 오차 집계](오차요약.csv)",
    ]
    (HERE/"README.md").write_text("\n\n".join(contents)+"\n",encoding="utf8")


if __name__=="__main__":
    main()
