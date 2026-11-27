from pathlib import Path
import hashlib,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from estimate_detours import HERE,DAYS,clock

def read(n):return json.loads((HERE/n).read_bytes())
def n(v):return f'{v:,.0f}'
def rounded_time(t):return clock(round(t/600)*600) if t is not None else '해당 없음'
def table(headers,rows):return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows])
def main():
    daily=read('daily_estimates.json');cells=read('half_hour_departures.json');specs=read('scenario_specs.json');verify=read('verification.json')
    def row(day,case='reference_reference',scope='external'):
        return next(r for r in daily if r['case']==case and r['weekday']==day and r['scope']==scope)
    def total(case,field,scope='external'):
        return sum(r[field] for r in daily if r['case']==case and r['scope']==scope)
    chosen=[row(day) for day in DAYS]
    assumption_rows=[]
    for case,label in [('low_reference','적게'),('reference_reference','기준'),('high_reference','많게')]:
        c=next(x for x in specs['cases'] if x['case']==case)
        assumption_rows.append([label,f"{c['class_related_share']*100:.0f}%",str(c['entries_per_visit']),n(c['target_weekly_library_visits']),n(total(case,'library_detour_weight')),f"{c['library_probability_given_eligible']*100:.2f}%"])
    weekday_table=table(['요일','도서관 경유 교외행','그중18시 이후 퇴실','18시 이후 집단 중앙시각','18~21시','21~24시'],[
        [d,n(r['library_detour_weight']),n(r['after18_library_exit_weight']),rounded_time(r['after18_median_exit_seconds_1min']),n(r['exit_18_21_weight']),n(r['exit_21_24_weight'])] for d,r in zip(DAYS,chosen)])
    all_table=table(['요일','기숙사 포함 전체 도서관 경유','교외행','301·302동 출발 교외행','301·302출발 중18시 이후 퇴실'],[
        [d,n(row(d,scope='all')['library_detour_weight']),n(row(d)['library_detour_weight']),n(row(d,scope='upper_external')['library_detour_weight']),n(row(d,scope='upper_external')['after18_library_exit_weight'])] for d in DAYS])
    evening_origin_table=table(['요일','18시 이후 강의동 출발→도서관→교외행','이 집단의 퇴실 중앙시각','이 집단 중21~24시 퇴실'],[
        [d,n(r['after18_origin_departure_library_weight']),rounded_time(r['after18_origin_median_exit_seconds_1min']),n(r['after18_origin_exit_21_24_weight'])] for d,r in zip(DAYS,chosen)])
    duration_rows=[]
    for case,label in [('reference_short','짧은 체류'),('reference_reference','기준 예시'),('reference_long','긴 체류')]:
        rs=[r for r in daily if r['case']==case and r['scope']=='external'];weight=total(case,'library_detour_weight')
        duration_rows.append([label,str(next(c['mean_unconstrained_dwell_hours'] for c in specs['cases'] if c['case']==case))+'시간',n(weight/5),n(total(case,'after18_library_exit_weight')/5),n(total(case,'exit_21_24_weight')/5),f"{100*total(case,'exit_21_24_weight')/weight:.1f}%"])
    baseline18=total('reference_reference','baseline_commute_phase_departures_18_19');changed18=total('reference_reference','retimed_commute_phase_departures_18_19')
    baseline21=total('reference_reference','baseline_commute_phase_departures_21_24');changed21=total('reference_reference','retimed_commute_phase_departures_21_24')
    low=total('low_reference','after18_library_exit_weight')/5;mid=total('reference_reference','after18_library_exit_weight')/5;high=total('high_reference','after18_library_exit_weight')/5
    plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':11})
    fig,ax=plt.subplots(figsize=(8.8,4.8))
    for case,label,color in [('reference_short','체류 평균 1시간','#687891'),('reference_reference','체류 평균 2시간','#177c6b'),('reference_long','체류 평균 4시간','#ae7034')]:
        values={t:0. for t in range(17*3600,25*3600,1800)}
        for c in cells:
            if c['case']==case and c['scope']=='external' and c['start_seconds'] in values:values[c['start_seconds']]+=c['library_exits']/5
        x=np.array(list(values))/3600;ax.step(x,list(values.values()),where='post',label=label,color=color,lw=2)
    ax.set_xticks(range(17,26),[f'{h%24:02d}:00' for h in range(17,26)]);ax.set_xlim(17,24.8);ax.set_ylim(bottom=0)
    ax.set_ylabel('30분별 교외행 귀가출발 가중치 / 평일 평균');ax.set_xlabel('도서관에서 출발하는 시각 (집 도착시각 아님)')
    ax.axvline(23,color='#999999',linestyle=':',lw=1);ax.text(23.05,ax.get_ylim()[1]*.88,'23시 퇴실 상한 가정',fontsize=10)
    ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True);ax.legend(frameon=False,loc='lower center',bbox_to_anchor=(.5,1.01),ncol=3)
    fig.suptitle('같은 방문량에서도 체류시간에 따라 저녁 귀가 수요가 달라집니다',fontsize=13)
    fig.text(.5,.01,'가정별 계산 · 실측 인원/퇴실시각 아님 · 23시 집중은 폐실 상한의 영향 포함',ha='center',fontsize=10)
    fig.tight_layout(rect=[0,.045,1,.88]);fig.savefig(HERE/'library_evening_departure_scenarios.png',dpi=180);fig.savefig(HERE/'library_evening_departure_scenarios.svg');plt.close(fig)
    report=f'''# 도서관 경유 후 귀가 인원·시각의 조건부 추정

분석일 2026-11-08. 할루시네이션 방지 O.

**수업 후 도서관을 거쳐 귀가하는 흐름을 가정별로 계산했습니다. 일별 출입·체류시간 실측으로 적합한 모형은 아닙니다. 기준 예시에서 월~목 도서관 경유 교외행은 하루 약980~1130명 상당, 그중18시 이후 도서관에서 출발하는 흐름은 약355~402명 상당입니다. 숫자는 고유 학생 수가 아닌 가중 통행·방문 사건입니다.**

## 1. 실제 자료가 알려주는 범위

[도서관보148호 원문](https://s-space.snu.ac.kr/handle/10371/236702) 인쇄201쪽/PDF105쪽의 2025-03-01~2026-02-28 통계에서 열람실265,935 + 관정관783,972 = **1,049,907**을 학습 공간 이용의 규모 참고값으로 사용했습니다. 자료실245,392는 이번 체류 모형에서 제외했습니다. 관정관 통계에는 학습 외 시설 이용도 섞일 수 있습니다.

이 값은 고유 재학생 수나 현재 학기 일별 이용자 수가 아닙니다. 개관350일은 정보서비스센터 기준이므로 분모로 사용하지 않았습니다. [KERIS2026 조사 지침](https://www.rinfo.kr/stat/bbs/detail/2/777) 인쇄54쪽/PDF58쪽은 반복 방문과 표본 주간의 연간 확대도 허용합니다. 서울대 개별 수치의 실제 산출 방식은 별도 확인 대상입니다.

따라서 수업 후 방문 비중·방문당 중복 기록·현재 학기 평일 이용 강도·체류시간·도서관 퇴실 뒤 목적지는 이 연간 통계 하나로 식별되지 않습니다. 다음 계산은 **연간 규모를 참고한 민감도 시나리오**입니다. 적합된 추정치, 통계적 신뢰구간, 실제 인원 범위가 아닙니다.

## 2. 인원 규모를 만드는 가정

기준 5일분 도서관 방문량을 다음과 같이 정의했습니다.

`B = 1,049,907 / 365 × 5 × s / r × k`

- `s`: 기록 중 수업 후 도서관 방문에 해당한다고 가정한 비중. **기존 수요 모형의 수업 직후 이동50%와 별개의 계수**입니다.
- `r`: 도서관 한 번 방문이 남기는 출입·시설 이용기록 수에 대한 가정입니다.
- `k`: 달력평균 대비 해당 학기 평일의 이용 강도. 기본값1, 별도 민감도1.5입니다.
- 365로 나누는 것은 규모 기준을 만들기 위한 계산이며 관측된 일별 이용자 수가 아닙니다. 5일분도 실제 학기중 한 주의 실측 합계가 아닙니다.

{table(['규모 가정','수업 후 방문 비중 s','방문당 기록 r','5일 도서관 방문(기숙사 포함)','5일 교외행','기존 출발량 중 분할 비율'],assumption_rows)}

요일·강의동·출발시각 배분은 2026-11-06 수강검색에 기초한 동결v5의 가중 출발 입자를 따릅니다. 이 때문에 수강 종료 사건이 적은 금요일에는 추정 방문량도 작습니다. 실제 도서관의 요일별 비율을 확인해서 적합한 결과가 아닙니다. 도서관 방문 선호가 출발지·요일·목적지에 따라 같다는 조건도 들어 있습니다.

## 3. 귀가 시각을 만드는 가정

1. 기존 v5의 강의동 출발시각을 유지했습니다. 이미 들어 있는 건물 이탈시간을 다시 더하지 않았습니다.
2. 보존된 SNU지도 본관62동·관정관62-1동과 OSM 보행망으로 도서관 도착시각을 구했습니다. 일반1.2m/s·표시된 계단0.7m/s의 원래 경로 비용에 v5 입자별 보행 배율을 적용했습니다. 앱 개인 길찾기의 평균4.8km/h 설정과 구분합니다. 도서관까지는 도보 접근을 가정했으며, 교내셔틀로 접근하는 선택은 이번 계산에 포함하지 않았습니다.
3. 본관 열람실과 관정관 방문 배분은 위 연간 이용 비율을 참고했습니다. 건물 간 재방문을 새로 만들지는 않았습니다.
4. 체류시간은 평균1·2·4시간을 비교했습니다. 각 경우 평균의0.5~1.5배 균등분포를 9개 중점으로 적분했습니다. 2시간 예시는1~3시간입니다. **서울대 체류 실측에서 얻은 분포가 아닙니다.**
5. 기준에서는23시 퇴실 상한을 적용하고 최소30분 체류 가능한 도착만 배정했습니다. 본관3A의24시간 운영을 반영하는 극단 민감도로, 본관 흐름의 상한을 없애고 관정관23시는 유지한 경우도 계산했습니다. 실제3A 선택 비중은 모릅니다. [운영 안내](https://www.snu.ac.kr/campuslife/facilities/library).

윗공대→도서관의 보존 경로 기준 보행은301동 약16~18분,302동 약18~19분이며 입자별 속도 배율이 추가됩니다. 출입구 연결선과 건물 대표점이 포함된 모형 시간이지 현장 보행 측정이 아닙니다. 도서관→행정관 승차지의 같은 기준 보행은 약6~6.5분입니다. 실제 셔틀 탑승까지는 해당 시각의 대기·정원·경로 선택을 추가 계산해야 합니다.

다른 대학 열람실의 공개 [로그 분석 연구](https://journal.kci.go.kr/kslis/archive/articlePdf?artiId=ART002588657)는 학기·방학·시험기간에 이용시간이 다름을 보여 줍니다. 이 자료를 서울대 체류분포나 수업 후 귀가시간으로 직접 전용하지 않았습니다. 1·2·4시간은 짧은 방문부터 긴 학습까지 결과가 어떻게 바뀌는지 보는 가정입니다.

## 4. 기준 예시의 요일별 결과

다음은 `s=50%, r=1.25, k=1, 체류평균2시간` 조건입니다. **교외행**은 기존 목적지가 서울대입구·낙성대·대학동 대표점인 흐름을 뜻합니다. 기숙사행은 제외했습니다. 실제 집 주소나 집 도착시간은 모릅니다.

{weekday_table}

‘중앙시각’은 **18시 이후 퇴실자만** 대상으로 한 중앙값입니다. 전체 도서관 방문자가19:30에 귀가한다는 뜻이 아닙니다. 전체 방문에는 오전·점심 수업 뒤 방문해 오후에 출발하는 흐름도 있습니다. 시각은 수치 계산상 분 단위로 집계했지만 가정과9점 적분의 한계가 있어10분 단위로 요약했습니다.

### 18시 이후 수업 뒤 이동에 집중하면

아래는 기존 v5의 **강의동 출발시각이18시 이상**인 흐름만 추린 것입니다. 이 시각에는 수업 종료 후 건물 이탈시간이 이미 들어 있으므로 ‘수업 종료시각18시 이상’과 완전히 같은 분류는 아닙니다.

{evening_origin_table}

이 집단의 기준 예시 퇴실 중앙시각은 월~목21:20~21:50입니다. 앞 표의19:30 전후와 다른 것은, 앞 표에는 더 이른 수업 뒤 도서관에 머물렀다가18시 이후 나오는 사람도 포함하기 때문입니다. 두 집단을 혼동하면 저녁 하교 수요의 발생 원인을 잘못 해석하게 됩니다.

21시 이후 값에는23시 퇴실 상한 때문에 몰린 흐름이 포함됩니다. 기준 예시에서 이 상한에 의해 퇴실시각이 잘린 교외행은5일 합 {n(total('reference_reference','forced_closing_weight'))}입니다. 이를 실제23시 동시 퇴실 인원으로 해석하지 않습니다.

### 기숙사·윗공대 구분

{all_table}

기숙사 비율은 기존19.4914% 참고 시나리오를 유지했습니다. 출신 강의동이301·302라는 뜻이며 공대 소속 고유 학생 수와 같지 않습니다. 기숙사행은 늦은 교내 이동에는 포함되지만 교외 셔틀 하교 수요에는 바로 합치지 않습니다.

## 5. 체류시간을 바꾸면

방문량을 기준 예시로 고정하고 시간 분포만 바꿨습니다. 아래는 월~금 합계를5로 나눈 평일 평균이며 실제 특정 날짜의 실측이 아닙니다.

{table(['체류 가정','상한 적용 전 평균','교외행 도서관 경유/일','그중18시 이후/일','그중21~24시/일','21~24시 비중'],duration_rows)}

![도서관 경유 저녁 귀가출발 시나리오](library_evening_departure_scenarios.png)

체류2시간을 유지하고 인원 가정만 바꾸면, 18시 이후 도서관에서 출발하는 교외행은 평일 평균 **{n(low)} / {n(mid)} / {n(high)}**입니다. 이 세 값은 낮음·기준·높음 가정이지 확률구간이 아닙니다.

`k=1.5`는 해당 학기 평일 강도가 달력평균보다50% 높다는 별도 가정으로, 방문 규모·시간대별 인원이 기준의1.5배가 됩니다. 이는 현재 학기 데이터를 보고 추정한 계수가 아닙니다.

본관24시간 민감도에서는 긴 체류 조건에 자정 이후 출발하는 교외행이5일 합 **{n(total('main_24h_long','exit_after24_weight'))}** 생깁니다. 기존 시뮬레이션 종료23:10을 넘는 흐름은 삭제하지 않고 별도 항목으로 보존했습니다.

## 6. 18시대 수요는 반드시 줄어드는가

아닙니다. **18시 수업 뒤 집단이 도서관으로 가는 효과**와 **더 이른 수업 뒤 도서관에 있던 집단이18시에 나오는 효과**가 함께 작용합니다.

기준 예시의 교외행 하교구간 출발 흐름은5일 합으로18~19시 **{n(baseline18)}→{n(changed18)} ({100*(changed18/baseline18-1):+.1f}%)**,21~24시 **{n(baseline21)}→{n(changed21)}**입니다.

여기서 비교하는 시각은 원래 강의동에서 하교 구간을 출발하던 시각과, 변경 후 강의동 또는 도서관에서 출발하는 시각입니다. **동일 정류장 유입·탑승·캠퍼스 경계 통과량·차내 혼잡 비교가 아닙니다.** 새 대기열과 정원 모형을 아직 재실행하지 않아 대기시간이나 버스 혼잡 개선·악화로 해석할 수 없습니다.

## 7. 식별 한계와 우선 확인할 자료

- 개인별 수강 연결·오늘의 마지막 수업이 없어 고유 학생을 식별할 수 없습니다. 같은 학생의 여러 수업 종료 사건이 포함될 수 있습니다.
- 기존 수업 직후 이동50%로 생성한78169 주간 가중 통행 중 일부를 도서관으로 전환했습니다. **기존 모형 밖 나머지50%에서 생길 야간 귀가를 추가하지 않았습니다.** 전체 서울대 학생의 완전한 야간 이동량이 아닙니다.
- 기관 연간 통계는2025-03~2026-02, 강좌는2026-11 보존본입니다. 기간·공사·시설 변화가 다릅니다. 연간 규모와 현재 학기 현실이 일치한다고 검증하지 않았습니다.
- 수업 후 방문 비중, 출입 중복, 현재 학기 평일 이용 강도, 체류시간, 방문 선호, 퇴실 후 목적지는 미관측 가정입니다. 인원·시각의 점추정은 자료만으로 식별되지 않습니다.
- 자료실 단순 방문, 분관·학과자료실, 연구실·식사·동아리 경유를 모두 포함한 모형은 아닙니다.
- 가장 필요한 추가자료는 날짜×30분×본관/관정관 입관·퇴관·체류, 재입장 중복 기준, 마지막 수업과 도서관 경유를 연결하는 익명 표본입니다. 앞선 연구의 자료 요청 초안은 발송되지 않은 상태입니다.

## 8. 산출물과 검산

- `estimate_detours.py`: 동결 입력에서 가정별 수요 재배분을 재현합니다. numpy와프로젝트보존파일이 필요하며 외부 API는 호출하지 않습니다.
- `scenario_specs.json`: 모든 가정·계수·규모 계산식.
- `daily_estimates.csv/json`: 12조건×5요일×5집단=300행. 18시 이후,21~24시,윗공대·기숙사 구분,중앙/P90,상한으로 잘린 흐름.
- `half_hour_departures.csv/json`: 모든30분별 원래 출발·남는 직접출발·도서관입관·퇴실·변화량. 24시 이후는 다음 날짜로 표시합니다.
- `walking_inputs.json`: 두 도서관 좌표·88개 출발동의 보행 경로 비용·연결선·계단.
- `integration_contract.json`: 원래 출발량에서 전환분을 빼고, 새 도서관 출발시각·위치에서 다시 경로 계산하도록 하는 계약. 새 흐름만 기존 수요에 더하면 중복입니다.
- `verification.json`: 모든 집단에서 직접출발+도서관경유=원래출발,주간목표방문량=배정량,시간대별 합계 일치. 최대 질량 오차 {verify['max_mass_error']:.2g},30분 합계 오차 {verify['max_histogram_mass_error']:.2g}. 입력 파일 해시 불변.

이번 계산은 **도서관 체류를 포함한 수요 시나리오**입니다. 실제 학생 추적·실측 적합·새 전체 교통 시뮬레이션 실행과 구분합니다. 기존 앱·원본 v5·공개 시뮬레이션 배포는 변경하지 않았습니다.
'''
    report_path=HERE/'도서관_경유_귀가인원과_시각_가정별추정.md';report_path.write_text(report,encoding='utf-8')
    highlights={'status':'PASS','case':'reference_reference','scope':'conditional weighted external trips, not unique students or home arrival',
        'weekday_rows':chosen,'low_reference_after18_per_weekday':low,'reference_after18_per_weekday':mid,'high_reference_after18_per_weekday':high,
        'commute_phase_18_19_before':baseline18,'commute_phase_18_19_after':changed18,
        'weekly_all_library_weight':sum(row(d,scope='all')['library_detour_weight'] for d in DAYS),
        'weekly_external_library_weight':sum(r['library_detour_weight'] for r in chosen),
        'figures':['library_evening_departure_scenarios.png'],'report_sha256':hashlib.sha256(report_path.read_bytes()).hexdigest(),
        'new_global_transit_queue_simulation':False,'observationally_fitted':False}
    (HERE/'result_summary.json').write_text(json.dumps(highlights,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'PASS','reference_library_external_weekly':highlights['weekly_external_library_weight'],'after18_per_weekday':mid,'report_bytes':report_path.stat().st_size}))

if __name__=='__main__':main()
