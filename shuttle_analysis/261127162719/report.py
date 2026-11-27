from score import HERE,read,records

LABEL={'V12':'정식 V12','previous':'직전 R','adjacent':'인접 정류장','direct':'다른 직행 포함','october':'10월 비율 · 네 노선','october02':'10월 비율 · 관악02-1만'}


def table(header,rows):
    return '\n'.join('| '+' | '.join(str(x) for x in r)+' |' for r in [header,['---']*len(header),*rows])


def main():
    scores={(r['service'],r['model']):r for r in read(HERE/'result.json')}
    cfg=read(HERE/'research-model.json')
    selected=cfg['policy']
    p=scores['peak',selected]; old=scores['peak','previous']
    origin={(r['model'],r['building']):float(r['target_pct']) for r in records(HERE/'출발동별_첫승차.csv')}
    lines=['# 윗공대 학생의 시내버스 승차지 선택',
        f"연구용 {cfg['model']}에서 채택한 조건은 **{LABEL[selected]}**이다. {cfg['reason']} [실험 조건과 자료](설계.md)",
        '## 11월 5일 목요일 피크 배차',
        '윗공대 300·301·302동에서 하교하는 모의 통행은 하루 2,158.8명 상당으로 모든 조건에서 같다. 아래는 실제로 제2공학관에서 시내버스에 승차해 교외 정류장에서 하차한 건수와 같은 기준으로 모의 원장을 집계한 결과다. 표의 시간은 승차 시각이다.',
        table(['조건','15~16시','16~17시','17~18시','18~19시','4시간 합계','시간당 평균 절대오차'],
              [['실측',*p['obs_hours'],sum(p['obs_hours']),'—']]+[[label,*[f'{x:.1f}' for x in scores['peak',v]['hours']],
                f"{sum(scores['peak',v]['hours']):.1f}",f"{scores['peak',v]['target_mae']:.2f}"] for v,label in LABEL.items()]),
        '목요일 하루 전체에서 제2공학관이 첫 차량 승차지였던 모의 비율은 출발 건물에 따라 달랐다. 301동 출발 통행은 1,438.4명, 302동은 710.5명 상당이었다. 인접 정류장 조건에서는 302동 집단의 승차 비율이 늘어도 더 큰 301동 집단의 감소를 상쇄하지 못했다. 이 비율은 출발 건물을 알 수 있는 모의 원장에서 계산했다.',
        table(['출발동','V12','직전 R','인접 정류장','채택 조건'],
              [[b+'동',*[f"{origin[v,b]:.1f}%" for v in ('V12','previous','adjacent',selected)]] for b in ('300','301','302')]),
        '[출발동별 첫 승차 원장 집계](출발동별_첫승차.csv)',
        '## 관악02-1의 승차지와 하차지',
        '11월 5일 18~19시 제2공학관에서 관악02-1에 타 교외에서 내린 152건 가운데 낙성대역에서 118건, 낙성대입구에서 26건이 하차했다. 다른 교외 하차지는 8건이다. 아래 비율은 해당 노선의 제1·제2공학관 승차를 합친 분모에서 제2공학관이 차지하는 몫이다. 비율 계산에는 교내 하차도 포함한다.',
        table(['조건','15~19시 제2공학관 승차','제1공학관 승차','제2공학관 비중','제2공학관 18~19시 교외 하차 승차'],
              [['실측',*[f'{x:g}' for x in p['gwanak02_obs_pair']],f"{p['gwanak02_observed_share']:.1f}%",152]]+
              [[label,*[f'{x:.1f}' for x in scores['peak',v]['gwanak02_pair']],f"{scores['peak',v]['gwanak02_modeled_share']:.1f}%",
                f"{scores['peak',v]['gwanak02_out_hours'][3]:.1f}"] for v,label in LABEL.items()]),
        f"채택 조건의 두 정류장 관악02-1 전체 모의 승차는 4시간에 {sum(p['gwanak02_pair']):.1f}건이다. 실측은 제2공학관 한 곳에서만 {p['gwanak02_obs_pair'][0]}건이었다. 같은 시간대와 같은 두 정류장의 총량을 고정하면, 두 곳 사이 재배분만으로는 이 차이를 채울 수 없다. 카드에는 수업 출발지나 학생 신분이 없다. 이 격차를 윗공대 학생 수 부족으로 바로 환산할 수 없는 이유다. [11월 카드 하차지 원표](11월5일_두정류장_하차지.csv) · [모형별 노선·하차지 대조](목요일_노선과하차지.csv)",
        '## 인근 정류장과 다른 날짜',
        '오차는 모두 작은 값이 실측에 가깝다. 제1공학관과 38곳 평균은 11월 5일 15~19시의 정류장·시간당 승차 오차다. 11월 2·3·4·6일은 제2공학관 네 노선의 하루 합계 승차 오차다(모든 하차지). 줄 7건은 관측한 분 안의 바깥줄을 시간가중해 비교했고, 관측별 오차를 동등 평균했다.',
        '별도 4일의 관악02-1 비중 오차는 각 날짜의 두 정류장 하루 승차 합계를 분모로 계산한 제2공학관 승차 비중의 평균 절대편차다.',
        table(['배차','조건','제1공학관(건)','38곳 평균(건)','별도 4일 하루(건)','별도 4일 관악02-1 비중(%p)','현장 바깥줄(명)'],
              [['피크' if s=='peak' else '기준',label,*[f"{scores[s,v][k]:.2f}" for k in ('near_mae','campus_mae','other_november_mae','other_november_route_share_mae_pp','queue_mae')]]
               for s in ('peak','regular') for v,label in LABEL.items()]),
        f"기준 배차에서도 제2공학관 15~19시 예측은 직전 R {sum(scores['regular','previous']['hours']):.1f}건, 채택 조건 {sum(scores['regular',selected]['hours']):.1f}건이었다. [38개 승차지 원표](목요일_승차지.csv) · [날짜별 두 정류장](일별_두정류장.csv) · [개별 현장 관측](현장관측.csv)",
        '## 검산과 재현']
    safety=records(HERE/'운영검산.csv')
    fresh=[r for r in safety if r['model'] in ('adjacent','direct','october','october02')]
    assert len(fresh)==40
    lines.append(f"새 규칙 네 가지의 월~금 × 두 배차 총 40회에서 개인별 원장 ID·출발 시각과 통행 무게를 V12와 대조했다. 차량 시간표·정원·FIFO·출발지와 최종 목적지 좌표도 검산했다. 미완료 통행 {sum(float(r['unserved']) for r in fresh):g}명 상당, 정원 위반 {sum(int(r['capacity']) for r in fresh)}건, 한 정류장에서 20분을 넘긴 연속 대기 {sum(float(r['over20']) for r in fresh):g}건 상당이었다. [운영 검산](운영검산.csv)")
    lines.append('연구 기본 조건은 [research-model.json](research-model.json)에 기록했다. 이 폴더에서 프로젝트 Python(NumPy 포함)으로 `python -B run.py thu peak`를 실행하면 해당 조건의 목요일 피크 배차를 사용한다. 세 번째 인수로 `adjacent`, `direct`, `october`, `october02`, `previous`를 지정해 각 조건을 재현할 수 있다. [계산 코드](run.py) · [실측 대조 코드](score.py)')
    (HERE/'README.md').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
