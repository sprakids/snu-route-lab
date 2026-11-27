"""Generate the research note from the scored ledgers."""
from collections import defaultdict
from statistics import mean
from evaluate import HERE, TARGET, read, records

LABEL = {'V12':'V12','origin':'인원만','choice':'승차 선택만','both':'두 조건 함께'}


def table(headers,rows):
    return '\n'.join('| '+' | '.join(map(str,r))+' |' for r in [headers,['---']*len(headers),*rows])


def generate():
    cards={(r['service'],r['scope'],r['model']):r for r in read(HERE/'card_scores.json')}
    design={(r['day'],r['service'],r['model']):r for r in records(HERE/'윗공대_출발과_실제승차.csv')}
    fields=records(HERE/'현장관측.csv')
    dates=read(HERE/'other_dates_scores.json')
    daily=records(HERE/'별도날짜_제2공학관_노선별.csv')
    safety=records(HERE/'운영검산.csv')
    attrib={(r['service'],r['model'],int(r['hour'])):r for r in records(HERE/'제2공학관_출발권역별.csv')}
    qbase=[r for r in fields if r['항목']=='바깥줄 분내 MAE']
    def score(service,v,col='R오차'):
        return mean(float(r[col]) for r in qbase if r['배차']==service and r['연구조건']==v)
    def card(v,s='peak',area='제2공학관'):
        return cards[s,area,v]
    peak=card('V12')
    both=card('both')
    gain=both['pred_total']-peak['pred_total']
    single=[card(v)['pred_total']-peak['pred_total'] for v in ('origin','choice')]
    sections=['# 윗공대 하교 인원과 제2공학관 승차 비율 실험',
        '연구모형 R261127160713. 대조군은 정식 V12이다. 윗공대는 300·301·302동 수업 출발자로 정의했다. 목요일의 두 배차에서 두 요인을 따로 바꾸고 함께 바꾸었고, 결합 조건은 평일 전체에서 확인했다. [실험설계](실험설계.md) · [실측자료 설명](../261125170855/comparison_20261127/실측과_V12_일대일_대조.md)',
        '## 목요일 제2공학관 승차',
        '11월 5일 제2공학관에서 시내버스에 승차해 교외에서 하차한 실측이다. 피크 배차의 모의 승차에는 출발 건물과 관계없이 같은 조건의 통행을 모두 포함했다. 소수점은 모의 승객 집단별 인원 가중치의 합이다.',
        table(['승차시각','실측(건)',*LABEL.values()],
              [[f'{15+i}~{16+i}시',peak['hourly_observed'][i],*[f"{card(v)['hourly_pred'][i]:.1f}" for v in LABEL]] for i in range(4)]
              +[['15~19시 합계',peak['obs_total'],*[f"{card(v)['pred_total']:.1f}" for v in LABEL]],
                ['17~19시 비중','64.0%',*[f"{card(v)['late_share']:.1f}%" for v in LABEL]],
                ['시간당 평균 절대오차(건)','',*[f"{card(v)['stop_hour_mae']:.2f}" for v in LABEL]]]),
        f"실측 {peak['obs_total']:,}건에 비해 V12가 적게 예측한 {peak['obs_total']-peak['pred_total']:.1f}건 중 결합 조건이 {gain:.1f}건({100*gain/(peak['obs_total']-peak['pred_total']):.1f}%)을 회복했다. 인원만 바꾼 효과는 +{single[0]:.1f}건, 승차 선택만 바꾼 효과는 +{single[1]:.1f}건이었다. 결합 효과에서 두 단독 효과의 합을 뺀 상호작용은 {gain-sum(single):+.1f}건이다. 기준 배차의 4시간 예측은 V12·인원·승차 선택·결합 순서로 "+' · '.join(f"{card(v,'regular')['pred_total']:.1f}" for v in LABEL)+'건이다.',
        '## 출발 인원과 실제로 탑승한 비율',
        '목요일 하루 단위의 피크 배차다. 최초 계획 비율과 실제 모의 승차 비율의 분모는 각각 해당 조건의 윗공대 총 하교 인원이다. 실제 모의 승차는 원장에서 학생이 탄 첫 차량을 확인했다. 이 표에는 교내에서 내린 승객도 들어가므로 위의 4시간 교외 하차 건수와 숫자가 다르다.',
        table(['조건','윗공대 하교(명 상당)','최초 계획 비율','첫 차량을 제2공학관에서 탄 인원','실제 모의 비율'],
              [[label,*[f"{float(design['thu','peak',v][k]):.1f}"+('%' if k.endswith('pct') else '') for k in
                          ('upper_mass','planned_pct','actual_first_target','actual_first_pct')]] for v,label in LABEL.items()]),
        '실험에서 두 배로 둔 것은 개별 집단의 오즈다. 인원 조건은 강의의 수강인원 범위 안에서 하교 확률을 올렸고, 선택 조건은 동일 건물·출발 좌표·목적지·30분대에 이용 가능한 사례가 있을 때 제2공학관행 도보 접근과 이후 이동 경로를 배정했다. 개인의 출발시각·보행속도·대기 중 재선택 규칙을 유지했다. 수강편람을 이용해 수업별로 만든 통행에는 같은 학생이 여러 수업에 등장할 수 있다. [요일·배차별 선택과 실제 승차](윗공대_출발과_실제승차.csv)',
        f"18~19시 제2공학관 승차 중 윗공대 수업 출발분은 V12 {float(attrib['peak','V12',18]['upper_origin']):.1f}건에서 결합 {float(attrib['peak','both',18]['upper_origin']):.1f}건, 다른 권역 출발분은 {float(attrib['peak','V12',18]['other_origin']):.1f}건에서 {float(attrib['peak','both',18]['other_origin']):.1f}건이었다. [개별 차량·수업 출발권역 대조](제2공학관_출발권역별.csv)",
        '## 다른 정류장과 기존 대기줄',
        '아래는 목요일 15~19시 정류장·시간당 평균 절대오차다. 피크 배차를 사용했다. 두 인근 정류장을 포함해 전체 38곳을 같은 단위로 비교했다.',
        table(['대상',*LABEL.values()],[[g,*[f"{card(v,area=g)['stop_hour_mae']:.2f}" for v in LABEL]]
               for g in ('제2공학관','제1공학관','공대입구','나머지 35곳','전체 38곳')]),
        '현장 바깥줄 7건은 관측 분 전체에서 오차를 시간가중하고 일곱 관측을 동등 평균했다. 아래 단위는 명이다. 기준 배차의 단독 조건은 목요일에만 실행해 월~수 현장 평균을 비워 두었다.',
        table(['배차',*LABEL.values()],[[s, f"{score(k,'both','V12오차'):.2f}",
              *[f"{score(k,v):.2f}" if k=='peak' or v=='both' else '—' for v in ('origin','choice','both')]]
              for k,s in [('regular','기준'),('peak','피크')]]),
        '[정류장별 카드 관측](목요일_38곳_시간별.csv) · [현장 바깥줄·차내·승차시간·잔여인원](현장관측.csv)',
        '## 다른 날짜와 노선으로 확인',
        '제2공학관의 동일 노선·동일 정류장 순번 하루 승차를 대조했다. 여기서는 교내 하차도 포함한다. 아래 첫 표는 11월 5일을 제외한 날짜에 네 노선의 하루 승차를 합한 뒤 날짜별 절대오차를 평균한 것이다. 같은 요일의 모형은 날짜마다 같은 예측을 쓴다.',
        table(['배차','모형','날짜 수','하루 실측 평균','하루 예측 평균','하루 평균 절대오차'],
              [['피크' if r['service']=='peak' else '기준',LABEL[r['model']],r['dates'],
                *[f"{r[k]:,.1f}" for k in ('mean_daily_observed','mean_daily_pred','daily_sum_mae')]] for r in dates]),
        '11월 5일 하루의 실제 승차와 피크 배차 모의 승차를 노선별로 대조했다. 각 노선의 방향과 순번을 일치시켰다.']
    rows=[r for r in daily if r['service']=='peak' and r['date']=='20261105']
    byroute=defaultdict(dict)
    for r in rows:
        byroute[r['route']][r['model']]=float(r['predicted'])
        byroute[r['route']]['observed']=r['observed']
    sections+=[table(['노선','실측(건)',*LABEL.values()],[[name,x['observed'],*[f'{x[v]:.1f}' for v in LABEL]] for name,x in byroute.items()]),
        '[날짜·노선·순번별 대조](별도날짜_제2공학관_노선별.csv)',
        '## 해석과 검산',
        '결합 조건에서 이른 시간대인 15~16시는 실측을 웃돌고 18~19시는 과소예측이 크게 남는다. 카드 승차에는 학생 신분·출발 건물·마지막 수업이 표시되지 않는다. 현장 자료에는 윗공대 출발자 전체라는 분모도 없어, 실험의 계수 두 개를 이 승차 건수만으로 각각 추정할 수 없다. 다음 관측은 같은 시간대에 윗공대 건물에서 하교를 시작한 사람의 수와 그중 제2공학관에서 탑승한 비율을 함께 파악하는 방식이 적절하다. 관악02-1은 노선별 잔여 오차가 커 실제 몇 명이 어느 방향으로 타는지도 우선 확인할 만하다.']
    fresh=[r for r in safety if r['model']!='V12']
    sections.append(f"연구 실행 {len(fresh)}개에서 출발 집단별 인원·선착순·차량 정원과 배차를 검산했다. 목요일 캠퍼스 하교 총량은 모든 조건에서 16,517명 상당이고, 결합 조건의 평일 합계는 배차당 78,169명 상당이다. 수업별 수강인원 상한, 요일 내 수업 종료 시간대·목적지별 합계, 신림선에 배정한 집단을 보존했다. 정원 위반 {sum(int(r['capacity_violations']) for r in fresh)}건, 미완료 {sum(float(r['unserved']) for r in fresh):.2f}명 상당, 20분 초과 연속 대기 {sum(float(r['over20_weight']) for r in fresh):.2f}건 상당이었다. 서로 다른 모의 조건을 합친 수는 감사용 집계다. [운영 검산](운영검산.csv) · [카드·현장 집계 코드](evaluate.py) · [개별 통행 독립 검산](verify_thursday.py)")
    (HERE/'README.md').write_text('\n\n'.join(sections)+'\n',encoding='utf-8')


if __name__=='__main__':
    generate()
