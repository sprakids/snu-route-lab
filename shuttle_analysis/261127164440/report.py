"""Generate the research summary from verified scenario scores and linked card counts."""
from collections import Counter

from score import HERE, PRIMARY, read, records


def table(headers, rows):
    return '\n'.join('| ' + ' | '.join(row) + ' |' for row in (headers, ['---'] * len(headers), *rows))


def percent(n, total):
    return f'{100 * n / total:.1f}%' if total else '—'


def main():
    all_scores = read(HERE / 'results.json')
    scores = {r['model']: r for r in all_scores if r['service'] == 'peak'}
    labels = {'baseline': '직전 R', 'station': '낙성대행 증가', 'route': '관악02-1 직행 선호 증가',
              'both': '두 조건 동시', 'law_transfer': '법대 경유 대안',
              'station_law': '낙성대행 증가 + 법대 경유 대안'}
    names = ('월', '화', '수', '목', '금')
    cohorts = records(HERE / '요일_출발시간별.csv')
    links = records(HERE / '카드연결_동일기준대조.csv')
    od = records(HERE / '두역방면_동일승하차.csv')
    safety = records(HERE / '운영검산.csv')
    cards = Counter()
    by_hour = Counter()
    for r in records(HERE / '11월5일_카드연결_시간별.csv'):
        cards[r['metric']] += int(r['passengers'])
        by_hour[int(r['first_board_hour']),r['metric']] += int(r['passengers'])
    body = ['# 저녁 윗공대 낙성대행과 관악02-1 이용',
            '연구 R261127164440. 저녁은 17~21시, 윗공대는 300·301·302동이다. 모의 인원은 통행 가중치를 합한 명 상당이다. 출발 수요를 교통카드 승차 건수에 직접 맞추면 출발동·수단을 모르는 이용자까지 학생으로 세게 되므로, 출발자 집계와 카드 기준 승하차 집계를 각각 계산했다. [가정·자료·재현](설계.md)',
            '## 목요일 저녁 건물에서 출발한 사람',
            f"피크 배차에서 윗공대 출발자는 {scores['baseline']['upper']:.1f}명 상당이다. 첫 차량에는 교내셔틀도 포함한다. 한 번 이상 이용에는 다른 수단에서 관악02-1로 환승한 사람도 포함한다."]
    rows = []
    for v in labels:
        r = scores[v]
        rows.append([labels[v], f"{r['nak']:.1f}", percent(r['nak'], r['upper']),
                     f"{r['any_line']:.1f} ({percent(r['any_line'],r['nak'])})",
                     f"{r['first_line']:.1f} ({percent(r['first_line'],r['nak'])})",
                     f"{r['single_line']:.1f}"])
    body.append(table(['조건', '낙성대행', '윗공대 출발 중', '관악02-1 한 번 이상', '첫 차량 관악02-1', '관악02-1 한 대로 도착'], rows))
    body.append('직전 R에는 이미 관악02-1을 이용하는 사람이 많아 선호를 더 높일 때 주로 달라지는 것은 환승 여부다. 반대로 5511→법대·사회대입구→관악02-2를 허용한 민감도 조건은 정류장과 운행 시간표가 맞는 대안이 어느 정도 있는지 보여준다. 기존 접근 경로만 조합한 관악02-2 대안은 허용한 시간차 안에서 선택 가능한 사람이 0명이었다.')
    body.append('## 평일별 출발 수요')
    rows = []
    for day, name in zip(('mon','tue','wed','thu','fri'), names):
        row = [name]
        for v in PRIMARY:
            subset = [x for x in cohorts if x['service']=='peak' and x['day']==day and x['model']==v]
            nak = sum(float(x['nak']) for x in subset)
            use = sum(float(x['any_line']) for x in subset)
            row.append(f'{nak:.1f} / {percent(use,nak)}')
        rows.append(row)
    body += ['각 칸은 낙성대행 인원 / 그중 관악02-1을 한 번 이상 이용한 비율이다. 시간대를 더 나눈 두 배차 전체 결과에는 최초 탑승과 단일 차량 이용도 들어 있다. [요일·출발 시간별 표](요일_출발시간별.csv)',
             table(['요일', *[labels[v] for v in PRIMARY]], rows)]
    body.append('## 11월 5일 목요일 카드 대조')
    body.append(f"두 공학관에서 17~21시에 첫 유료 승차가 찍힌 {cards['first_paid_journeys']:,}건 중 낙성대역·낙성대입구 버스 하차 또는 낙성대역 첫 지하철 승차가 확인된 통행은 {cards['confirmed_bus_or_rail']}건이었다. 이 중 관악02-1을 거친 통행은 {cards['confirmed_used_line']}건({percent(cards['confirmed_used_line'],cards['confirmed_bus_or_rail'])})이다. 버스 하차로 확인된 {cards['bus_alight']}건 중 {cards['bus_alight_first_line']}건은 첫 유료 차량도 관악02-1이었다. [시간·승차지별 카드 집계](11월5일_카드연결_시간별.csv)")
    rows = []
    for hour in range(17,21):
        values = [r for r in cohorts if r['day']=='thu' and r['service']=='peak' and int(r['hour'])==hour]
        model = {r['model']:r for r in values}
        card_n = by_hour[hour,'confirmed_bus_or_rail']
        card_g = by_hour[hour,'confirmed_used_line']
        rows.append([f'{hour}~{hour+1}시', f'{card_n} / {card_g}',
                     *[f"{float(model[v]['nak']):.1f} / {float(model[v]['any_line']):.1f}" for v in ('baseline','both')]])
    body += ['시간대별 낙성대행 / 그중 관악02-1 이용. 첫 열의 시간은 카드에서는 두 공학관 정류장의 승차시각, 모형에서는 세 공학동을 나선 시각이다. 이 표의 카드와 모형 차이는 예측 오차로 계산하지 않는다.',
             table(['시각','카드 확인 통행 / 관악02-1','직전 R 출발 인원 / 관악02-1','두 조건 동시 출발 인원 / 관악02-1'],rows)]
    rows = []
    def sum_where(data, col, **criteria):
        return sum(float(r[col]) for r in data if all(r[k]==v for k,v in criteria.items()))
    metrics = [(links, dict(metric='bus_alight'), '두 공학관 첫 유료 승차 → 환승 포함 낙성대 두 정류장 하차'),
               (links, dict(metric='bus_alight_used_line'), '위 통행 중 관악02-1 이용'),
               (links, dict(metric='bus_alight_first_line'), '위 통행 중 첫 유료 차량이 관악02-1'),
               (od, dict(gateway='낙성대역·낙성대입구'), '두 공학관 승차 → 같은 버스로 낙성대 두 정류장 하차'),
               (od, dict(gateway='서울대입구역2번출구'), '두 공학관 승차 → 같은 버스로 서울대입구역2번출구 하차')]
    for data, criteria, label in metrics:
        rows.append([label, f"{sum_where(data,'measured',model='baseline',service='peak',**criteria):.0f}",
                     *[f"{sum_where(data,'modeled',model=v,service='peak',**criteria):.1f}" for v in PRIMARY]])
    rows.append(['18~19시 제2공학관 관악02-1 승차 → 낙성대 두 정류장 하차',
                 str(scores['baseline']['observed_g_station'][1]),
                 *[f"{scores[v]['g_station_hours'][1]:.1f}" for v in PRIMARY]])
    body += [table(['승객 통행 또는 승차 건수', '카드', *[labels[v] for v in PRIMARY]], rows),
              '첫 유료 승차를 조건으로 건 행과 같은 버스의 한 승하차 구간을 센 행은 분모가 다르다. 후자에는 앞서 다른 유료 차량을 탔던 승객도 포함된다. 서울대입구역 행은 2번 출구 정류장 하차로 한정했다. 카드에는 원래 건물, 학생 신분, 최종 귀가 목적이 없다. [연결 통행 대조](카드연결_동일기준대조.csv) · [직접 승하차 양방면 대조](두역방면_동일승하차.csv)']
    body.append('## 다른 지표에 미친 영향')
    body.append('앞 네 열은 11월 5일 17~21시의 정류장·시간당 승차 평균 절대오차(건)다. 별도 4일은 11월 2·3·4·6일 제2공학관의 관악02-1 및 비교 노선 전체 하루 승차 평균 절대오차(건)다. 이 날짜들의 표에는 저녁에 어느 역에서 내렸는지까지 나오지 않는다. 바깥줄은 분 단위 현장 관측 7건을 시간가중한 평균 절대오차(명)다.')
    rows=[]
    for r in all_scores:
        if r['model'] not in PRIMARY:continue
        rows.append([{'peak':'피크','regular':'기준'}[r['service']], labels[r['model']],
                     *[f"{r[k]:.2f}" for k in ('route_station_mae','target_mae','near_mae','other36_mae','line_other_days','all_other_days','queue_mae')]])
    body.append(table(['배차','조건','제2공학관 관악02-1 낙성대 두 정류장행','제2공학관 교외행','제1공학관 교외행','기타 36곳 교외행','별도 4일 관악02-1','별도 4일 전체','현장 바깥줄'],rows))
    body += ['낙성대행을 늘리면 목요일 해당 방면 과소예측은 줄지만, 서울대입구역2번출구도 원래부터 과소예측되고 있어 그쪽 승객을 옮기면 오차가 커진다. 따라서 연구 기준선은 직전 R로 두고, 두 조건 동시 적용은 저녁 수요 원인을 더 조사하는 비교 조건으로 보관한다. 카드에 나타난 두 방향의 승차 수요가 모두 부족하므로, 후속 검토 대상은 건물별 저녁 출발량과 수업 이외의 출발 수요다. 이 실험으로 개인의 실제 하교 목적지 비율을 식별할 수는 없다.',
             '## 검산',
             f"기준과 실험을 합친 요일·배차·조건 {len(safety)}개에서 출발자별 ID·출발 시각·가중치를 대조했다. 동시에 바꿨을 때의 목적지 배정도 목적지만 바꾼 실험과 같다. 정원 위반은 {sum(int(r['capacity']) for r in safety)}건, 미완료는 {sum(float(r['unserved']) for r in safety):.0f}명 상당, 한 정류장 20분 초과 대기는 {sum(float(r['over20']) for r in safety):.0f}명 상당으로, 최장 연속 대기는 {max(float(r['maxwait']) for r in safety):.2f}분이었다. 별도의 목요일 피크 무변경 실행은 직전 R의 개별 출발, 실제 승하차와 집계값을 재현했다. [운영 검산](운영검산.csv) · [현장 관측별 비교](현장관측.csv) · [수치 원본](results.json)"]
    (HERE / 'README.md').write_text('\n\n'.join(body)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
