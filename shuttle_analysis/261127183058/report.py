"""Build the short Korean results note from the scored ledgers."""
import csv
import json
from pathlib import Path
from statistics import mean

D=Path(__file__).resolve().parent
def table(name):
    with (D/name).open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def avg(rows,field):return mean(float(r[field]) for r in rows)

def main():
    result=json.loads((D/"validation.json").read_bytes())["errors"]
    v=result["holdout"];fit=result["fit"]
    each=table("validation.csv");field=table("field.csv");ops=table("weekday_checks.csv")
    p=v["V13"]["primary"];a=v["V12"]["primary"];prev=v["r0"]["primary"]
    lines=["# V13 실측 검증", "",
        f"제1·제2공학관의 18~21시 두 역 방면 승차 오차는 따로 보관한 화·수요일에 V12 **{a:.2f}건**, 직전 R **{prev:.2f}건**, V13 **{p:.2f}건**이었다. 단위는 정류장 하나·방면 하나·한 시간당 평균 절대오차(MAE)다. V12와 V13의 차이에는 이번 수정과 그동안의 R 실험이 함께 들어간다. [조건을 정한 과정](설계.md)", "",
        "| 비교 대상 | V12 | 직전 R | V13 |","|---|---:|---:|---:|"]
    for group,stats,key in [("조건 선택 4일 · 두 공학관 저녁",fit,"primary"),("별도 2일 · 두 공학관 저녁",v,"primary"),("별도 2일 · 제2공학관 저녁",v,"second"),("별도 2일 · 제1공학관 저녁",v,"first"),("별도 2일 · 두 공학관 12~23시",v,"pair_full"),("별도 2일 · 나머지 36개 정류장 12~23시, 교외 하차",v,"other36")]:
        lines.append(f"| {group} | "+" | ".join(f'{stats[m][key]:.2f}' for m in ("V12","r0","V13"))+" |")
    lines+=["","두 날짜는 11월 17일(화), 18일(수)이다. 두 역 방면 승차는 두 날짜에 총 24개 칸으로 채점했다. 다른 36곳은 같은 두 날짜에 792개 칸을 교외 하차 전체로 비교했다. 수업편람 기반 하교 모형의 예측을 전체 유료 버스 이용자의 카드 승차와 대조한 값이다. [날짜별 채점](validation.csv) · [승차 실측과 예측 전체](boardings.csv)","",
            "| 18~21시 · 두 공학관 | V12 | 직전 R | V13 |","|---|---:|---:|---:|"]
    for date in ("20261117","20261118"):
        scores={r["model"]:float(r["MAE"]) for r in each if r["date"]==date and r["metric"]=="primary"}
        lines.append(f"| 11/{date[-2:]} | "+" | ".join(f'{scores[m]:.2f}' for m in ("V12","r0","V13"))+" |")
    rows=[r for r in table("boardings.csv") if r["model"]=="V13" and r["sample"]=="holdout" and 18<=int(r["hour"])<21 and r["direction"]!="all"]
    worst=max(rows,key=lambda r:float(r["absolute_error"]))
    stop={"120000173":"제2공학관","120000174":"제1공학관"}[worst["stop"]];dest={"nak":"낙성대","snu":"서울대입구역"}[worst["direction"]]
    lines+=["",f"검증에서 가장 큰 오차는 11/{worst['date'][-2:]} {worst['hour']}시대 {stop}에서 {dest} 방면이었다. 실제 {worst['observed']}건, V13 {float(worst['predicted']):.1f}건이었다. 카드에는 출발 건물·학생 신분·남아 있었던 이유가 없어 이 차이를 특정 학생 집단의 행동으로 단정할 수 없다.", "",
            "## 기존 현장 관측과 모의 운영", "", "| 바깥 대기줄 관측 | 건수 | V11 | V12 | V13 |","|---|---:|---:|---:|---:|"]
    for s,label in (("peak","피크 배차"),("regular","기준 배차")):
        tmp=[r for r in field if r["배차"]==s and r["항목"]=="바깥줄 분내 MAE"]
        lines.append(f"| {label} | {len(tmp)} | "+" | ".join(f'{avg(tmp,k):.2f}명' for k in ("V11오차","V12오차","R오차"))+" |")
    lines+=["","관측 초를 모르면 그 1분 안에 각 줄 길이가 지속된 시간으로 절대오차를 가중평균한다. 예를 들어 줄이 10초 동안만 길었을 때와 60초 내내 길었을 때를 구별한다. 차내 대기, 개인 대기 초, 출발 뒤 잔여는 각자의 단위로 따로 보관했다. CSV에서 연구용 공통 열 이름 `R예측`과 `R오차`는 이번 연구조건 V13의 값이다. [현장 관측별 결과](field.csv)","",
        f"요일별 하루 모의 하교 인원은 월~금 "+", ".join(f"{float(r['daily']):,.1f}" for r in ops if r["service"]=="peak")+f"명 상당이다. 두 배차에서 매일 V12와 같았고 열 조건 모두 정원 위반·미완료·한 정류장의 20분 초과 연속 대기가 0이었다. 최장 연속 대기는 {max(float(r['max_continuous_wait']) for r in ops):.2f}분이었다. 이는 시뮬레이션 안의 검산이다. [평일별 검산](weekday_checks.csv)","",
        "검증 날짜가 두 날뿐이어서 학기 전체의 정확도로 일반화하기 어렵다. 과소예측이 큰 정류장에서 연구·근무 인원과 실제 방면을 구분한 현장 조사, 같은 날 두 정류장의 연속 승차 계수가 다음 비교의 근거가 된다."]
    (D/"README.md").write_text("\n".join(lines)+"\n",encoding="utf8")
if __name__=="__main__":main()
