"""Write a Korean summary from the checked ledgers."""
from collections import Counter
from statistics import mean
from score import HERE, LAST, MAIN, FOLLOWUP, read, records

LABEL={'base':'직전 R','stay':'수업 후 추가 체류','access':'다른 건물에서 접근','joint':'두 조건 동시','joint_soft':'체류 + 거리별 접근 확률'}


def table(head,rows):
    return '\n'.join('| '+' | '.join(row)+' |' for row in [head,['---']*len(head),*rows])


def main():
    scores=records(HERE/'조건별_결과.csv');days=records(HERE/'요일별_수요.csv')
    hourly=records(HERE/'목요일_두역방면.csv')
    supply=records(HERE/'운영검산.csv');wide=records(HERE/'접근조건_민감도.csv')
    rows={r['model']:r for r in scores if r['service']=='peak'}
    cohort={r['model']:r for r in days if r['service']=='peak' and r['day']=='thu'}
    def num(r,k):return f"{float(r[k]):,.1f}"
    def values(r,keys):return [num(r,k) for k in keys]
    def hour(v,k,h,measured=False):
        return sum(float(r['measured' if measured else 'modeled']) for r in hourly if
                   r['model']==v and r['service']=='peak' and r['metric']==k and int(r['hour'])==h)
    direct_baseline={k:sum(hour('base',k,h,True) for h in range(17,21)) for k in ('nak','snu')}
    assert direct_baseline=={'nak':483,'snu':331}
    matched=sum(int(r['passengers']) for r in records(LAST/'11월5일_카드연결_시간별.csv') if r['metric']=='bus_alight')
    assert matched==475
    text=['# 수업 후 체류와 다른 건물의 두 공학관 승차 실험',
          '연구 R261127170244. 같은 학생의 하루 출발 건물·목적지·가중치를 고정하고, 수업을 마친 뒤 얼마나 머무는지와 다른 건물에서 어느 정류장으로 걸어가는지를 독립적으로 바꿨다. 목요일 17~21시의 양방면 승차를 함께 개선한 효과는 대부분 체류 집단에서 나왔다. [실험 설정과 재현 방법](설계.md)',
          '## 11월 5일 목요일 승차',
          '피크 배차 · 제1·제2공학관 합계. 두 역 방면은 해당 정류장에서 탄 차량과 같은 차량으로 지정 정류장에 내린 승차다. 세 번째 지표는 두 공학관에서 첫 유료 차량을 타고 환승을 거쳐 낙성대역·낙성대입구에 내린 통행도 포함한다. 마지막 지표는 제2공학관 한 곳의 18~19시 관악02-1 직행이다. 소수점은 모의 통행 가중치에서 나왔다.',
          table(['조건','낙성대역·낙성대입구','서울대입구역2번출구','낙성대행 첫 유료 승차·환승 포함','제2공학관 18~19시 관악02-1'],
                [['카드 실측','483','331','475','144']]+[[LABEL[v],*values(rows[v],('nak','snu','linked_nak','line18'))] for v in (*MAIN,FOLLOWUP)])]
    missing=sum(direct_baseline.values())-sum(float(rows['base'][k]) for k in direct_baseline)
    gain=sum(float(rows['joint'][k])-float(rows['base'][k]) for k in direct_baseline)
    soft_gain=sum(float(rows[FOLLOWUP][k])-float(rows['base'][k]) for k in direct_baseline)
    text.append(f'직전 R이 두 방면에서 적게 예측한 합계 {missing:.1f}건 중 두 기본 조건을 함께 적용하여 {gain:.1f}건({100*gain/missing:.1f}%)이 줄었다. 체류와 거리별 접근 확률을 함께 적용하면 감소폭은 {soft_gain:.1f}건({100*soft_gain/missing:.1f}%)이다. 이 수치는 해당 저녁의 두 승하차 쌍에서 줄어든 격차를 뜻한다. 캠퍼스 전체 예측 정확도와는 분모가 다르다.')
    text.append(f"정류장 2곳 × 저녁 4시간 × 역 방면 2개를 각각 평가한 16칸의 평균 절대오차는 직전 R {float(rows['base']['od_cell_mae']):.2f}건, 체류만 변경 {float(rows['stay']['od_cell_mae']):.2f}건, 체류와 거리별 접근 동시 {float(rows[FOLLOWUP]['od_cell_mae']):.2f}건이다. 이 지표에서는 과대예측한 칸과 과소예측한 칸을 따로 계산한다.")
    by_stop=[]
    for stop,title in [('120000173','제2공학관'),('120000174','제1공학관')]:
        for metric,station in [('nak','낙성대'),('snu','서울대입구역')]:
            group=[r for r in hourly if r['service']=='peak' and r['stop']==stop and r['metric']==metric and 17<=int(r['hour'])<21]
            measured=sum(int(r['measured']) for r in group if r['model']=='base')
            by_stop.append([title,station,str(measured),*[f"{sum(float(r['modeled']) for r in group if r['model']==v):.1f}" for v in ('base','stay',FOLLOWUP)]])
    text.append(table(['승차지','하차 방면','카드','직전 R','체류만','체류 + 거리별 접근'],by_stop))
    text += ['## 학생의 출발과 실제 첫 승차',
             f"목요일 윗공대에서 15~17시에 수업이 끝난 조기 출발 집단 중 {num(cohort['joint'],'stay_changed')}명 상당의 출발을 늦췄다. 이 중 {num(cohort['joint'],'moved_into_evening')}명이 17시 이전 출발에서 17~21시 출발로 이동했다. 저녁 낙성대행 출발자는 {num(cohort['base'],'nak')}→{num(cohort['joint'],'nak')}명 상당이고, 그중 실제 관악02-1을 한 번 이상 이용한 비율은 {100*float(cohort['base']['nak_line'])/float(cohort['base']['nak']):.1f}%→{100*float(cohort['joint']['nak_line'])/float(cohort['joint']['nak']):.1f}%다.",
             table(['피크 배차 요일','윗공대 저녁 출발 직전 R → 동시','낙성대행 직전 R → 동시','서울대입구역행 직전 R → 동시','다른 건물에서 두 공학관 첫 승차(기본 접근 / 거리별 확률)'],
                   [[label,*[f"{num(a,k)} → {num(b,k)}" for k in ('upper','nak','snu')],f"{num(b,'other_changed_first')} / {num(c,'other_changed_first')}"]
                    for day,label in zip(('mon','tue','wed','thu','fri'),('월','화','수','목','금'))
                    for a,b,c in [(next(r for r in days if r['day']==day and r['service']=='peak' and r['model']=='base'),
                                   next(r for r in days if r['day']==day and r['service']=='peak' and r['model']=='joint'),
                                   next(r for r in days if r['day']==day and r['service']=='peak' and r['model']==FOLLOWUP))]]),
             '건물 출발표와 카드 승차는 시간이 다르다. 도보 접근·대기시간을 거친 실제 승차를 확인할 때에는 첫 번째 표와 아래 시간표를 사용한다. [요일별 수요](요일별_수요.csv) · [실제 첫 승차의 출발 건물](출발건물별_첫승차.csv)']
    wider=next(r for r in wide if r['service']=='peak' and r['model']=='access_wide')
    soft=next(r for r in wide if r['service']=='peak' and r['model']=='access_soft')
    diagnostic=read(HERE/'walking_access_peak_thu.json')['total']
    access_results=Counter();selected_stops=Counter()
    for r in records(HERE/'목요일_접근선택후_행동.csv'):
        access_results[r['outcome']]+=float(r['weight'])
        if r['outcome']=='두 공학관에서 17~21시 첫 승차':selected_stops[r['stop']]+=float(r['weight'])
    assert abs(diagnostic['access_changed']-float(cohort['access']['access_changed']))<1e-6
    text+=['## 다른 건물에서 걸어올 수 있는 범위',
           f"목요일 경로 탐색 대상 중 {num(cohort['access'],'access_800m')}명 상당에게 800m 이내 보행 경로가 있었다. 이 중 체감거리 1km 이하는 {diagnostic['felt_under_1km']:.1f}명, 기본 보행 부담과 버스 시각을 모두 만족한 사람은 {num(cohort['access'],'access_eligible')}명, 실제 새 정류장에서 첫 승차한 사람은 {num(cohort['access'],'other_changed_first')}명이었다. 기본 조건에서 새 승차지를 택한 출발동은 29동 약학관2였다. [단계별·출발동별 후보](walking_access_peak_thu.json)",
           f"버스 시각과 추가 도보 한도를 완화하면 시간표까지 맞는 후보는 {num(wider,'access_eligible')}명, 선택은 {num(wider,'access_changed')}명이었다. 여기에 체감 1km 초과도 허용해 선택확률만 거리와 함께 줄이면 후보는 {num(soft,'access_eligible')}명, 선택은 {num(soft,'access_changed')}명이고, 그중 17~21시에 두 공학관에서 실제 첫 차량을 탄 인원은 {num(soft,'other_first')}명 상당이다. 승차지 접근 선호만 조정한 이 마지막 조건의 저녁 직접 승하차는 낙성대 {num(soft,'nak')}건, 서울대입구역2번출구 {num(soft,'snu')}건이었다. 이 비교는 모형에서 어느 가정이 후보를 줄이는지 보여준다. 실제 보행 거부율은 출발 건물과 승차지를 함께 기록해야 검증할 수 있다. [목요일 접근 조건 민감도](접근조건_민감도.csv)",
           f"체류까지 함께 적용한 목요일 피크에서는 추가 접근을 선택한 사람 중 {access_results['두 공학관에서 17~21시 첫 승차']:.1f}명이 21시 전에, {access_results['두 공학관에서 21시 이후 첫 승차']:.1f}명이 21시 이후에 두 공학관에서 첫 차량을 탔다. 21시 이전 추가 첫 승차는 제1공학관 {selected_stops['120000174']:.1f}명, 제2공학관 {selected_stops['120000173']:.1f}명이다. 다른 건물에서 걸어오는 경로를 늘리는 가정은 저녁 제2공학관 과소예측을 설명하는 데 한계가 있다. [선택 후 실제 승차](목요일_접근선택후_행동.csv)",
           '## 어느 시간대가 개선됐는가',
           table(['승차 시간','낙성대 실측','낙성대 직전 R → 동시','서울대입구역 실측','서울대입구역 직전 R → 동시'],
                 [[f'{h}~{h+1}시',f"{hour('base','nak',h,True):.0f}",f"{hour('base','nak',h):.1f} → {hour('joint','nak',h):.1f}",
                   f"{hour('base','snu',h,True):.0f}",f"{hour('base','snu',h):.1f} → {hour('joint','snu',h):.1f}"] for h in range(15,23)]),
           f"거리별 접근까지 적용한 조건에서 18~19시 낙성대 방면은 {hour(FOLLOWUP,'nak',18):.1f}건(실측 {hour('base','nak',18,True):.0f}), 서울대입구역 방면은 {hour(FOLLOWUP,'snu',18):.1f}건(실측 {hour('base','snu',18,True):.0f})이다. 19~20시에는 낙성대 {hour(FOLLOWUP,'nak',19):.1f}건 대 실측 {hour('base','nak',19,True):.0f}건, 서울대입구역 {hour(FOLLOWUP,'snu',19):.1f}건 대 실측 {hour('base','snu',19,True):.0f}건으로 두 방향 모두 부족하다. 현재 체류 가정으로 옮겨진 학생의 출발이 17~19시에 집중되어 있어 19시 이후 이용자를 설명하는 데 한계가 있다. [시간대별 그래프](목요일_두역방면.png) · [정류장·노선별 원표](목요일_두역방면.csv)"]
    keys=('two_afternoon','two_evening','two_late','two_window','other36','date2','date1','field_mae')
    text+=['## 다른 시간·장소·날짜의 오차',
           '승차 오차는 정류장·시간별 절대오차의 평균(건)이다. 다른 4일은 각각 제2·제1공학관의 하루 전체 승차 절대오차 평균(건)이고, 현장 바깥줄은 제보 7건의 분 내 시간가중 평균 절대오차(명)다.',
           table(['배차','조건','두 곳 15~17시','두 곳 17~21시','두 곳 21~23시','두 곳 15~23시','기타 36곳 17~21시','4일 제2','4일 제1','현장 줄'],
                 [[{'peak':'피크','regular':'기준'}[r['service']],LABEL[r['model']],*[f'{float(r[k]):.2f}' for k in keys]] for r in scores]),
           '[38곳 시간대별](목요일_38개정류장.csv) · [다른 날짜의 노선별 승차](다른날_승차.csv) · [현장 관측](현장관측.csv)',
           '## 판단과 검산',
           '수업 후 추가 체류는 양방면 과소예측을 줄이는 연구 후보로 보관한다. 25%와 60~120분은 연구 가정이므로, 다른 날짜의 시간대별 승하차나 출발 건물·수업 종료·퇴실 시각 관측이 있어야 계수를 추정할 수 있다. 두 공학관 이용객에는 연구실·야간 활동·교직원 등 편람만으로 잡히지 않는 통행이 있을 수 있다. 이번 실험으로 그 사람 수나 목적을 구분할 수는 없다.',
           f"평일 5일 × 배차 2종 × 5개 조건(기준·기본 실험 세 조건·거리별 접근과 체류 동시)에서 개인별 가중치·목적지·출발 건물을 대조했다. 별도 목요일 민감도 표에는 이 중 목요일 거리별 접근·체류 동시 두 배차도 포함한다. 목요일 피크 배차 무변경 재실행은 직전 R의 승차를 재현했다. 정원 위반·미완료 0, 연속 20분 초과 대기는 평일 비교 전체 {sum(float(r['over20']) for r in supply):g}명 상당, 목요일 민감도 표 전체 {sum(float(r['over20']) for r in wide):g}명 상당이다. [운영 검산](운영검산.csv)"]
    (HERE/'README.md').write_text('\n\n'.join(text)+'\n',encoding='utf8')


if __name__=='__main__':main()
