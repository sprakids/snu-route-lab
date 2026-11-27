"""Render the same verified field comparisons for the research map and its README."""
import csv
import html
import os
import sys
from pathlib import Path
from statistics import mean
from evaluate import HERE, read


def csv_rows(name):
    with (HERE/name).open(encoding='utf-8-sig', newline='') as file:
        return list(csv.DictReader(file))


def plot(output=HERE/'화요일_대기_비교.png',candidate_label='새 R'):
    cache = Path(os.environ.get('TEMP', '')) / 'snu-1518-plot'
    if cache.is_dir():
        sys.path.insert(0, str(cache))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.family'] = 'Malgun Gothic'
    windows = csv_rows('5분별_유입과_대기.csv')
    fig, axes = plt.subplots(2,2, figsize=(11,6), sharex=True, layout='constrained')
    for axis, (stop, label, metric) in zip(axes.flat, (
            ('admin_snu','서울대입구역행','outside'),('admin_snu','서울대입구역행','aboard'),
            ('admin_daehak','대학동행','outside'),('admin_daehak','대학동행','aboard'))):
        for cond, title, color in [('combined','이전 차량 복귀 모형','#737373'),('candidate',candidate_label,'#126d86')]:
            values = [float(r[metric]) for r in windows if r['condition']==cond
                      and r['service']=='peak' and r['stop']==stop]
            assert len(values)==12
            axis.stairs(values, range(0,61,5), baseline=None, label=title, color=color, lw=2)
        axis.set(title=label+(' 바깥줄' if metric=='outside' else ' 출발 전 차내 합계'), ylabel='명 상당', ylim=(0,None))
        axis.grid(axis='y', alpha=.2)
        axis.set_xticks([0,15,30,45,60], ['14:48','15:03','15:18','15:33','15:48'])
        if stop=='admin_snu' and metric=='outside':
            axis.scatter([30.5],[6], marker='D', color='#a03d26', s=35, label='11/24 순간 관측')
        if stop=='admin_daehak' and metric=='aboard':
            axis.scatter([30.5],[17], marker='D', color='#a03d26', s=35, label='11/24 한 대에서 센 인원')
    axes[0,0].legend(frameon=False, fontsize=8)
    axes[1,1].legend(frameon=False, fontsize=8)
    fig.suptitle('화요일 행정관 셔틀 · 피크 배차 시나리오의 5분 평균', fontweight='bold')
    fig.savefig(output, dpi=150)
    plt.close(fig)


def main():
    result = read(HERE/'검증결과.json')
    rows = csv_rows('현장비교.csv')
    cases = csv_rows('평일검증.csv')
    display = {'admin_snu':'행정관 설입행', 'admin_daehak':'행정관 대학동행',
               'culture_city':'문화관', 'city_museum':'문화관', 'gate_city':'정문'}
    headers = ['관측일·시간','노선·상태','실측','이전 피크 평균','새 기준 평균','새 피크 평균','새 피크 분 내 범위']
    lines = []
    for obs in sorted({r['source'] for r in rows}):
        subset = {(r['condition'],r['service']):r for r in rows if r['source']==obs}
        r = subset['candidate','peak']
        place = display.get(r['stop']) or ('문화관' if r['minute']=='16:55' else '서울대학교 정류장')
        label = place+(' 차내' if r['kind']=='onboard' else ' 바깥줄')
        def average(cond,service):
            x = subset[cond,service]['mean']
            return f'{float(x):.1f}' if x else '차량 특정 불가'
        lines.append([f'{obs[4:6]}/{obs[6:8]} {r["minute"]}',label,r['measured'],
                      average('combined','peak'),average('candidate','regular'),average('candidate','peak'),
                      f'{float(r["low"]):.1f}~{float(r["high"]):.1f}'])
    scores = result['scores']
    gap = result['prior_bus']['minute']
    dated = result['scenarios']
    note = []
    note.append('분 단위 제보는 그 60초 동안 각 대기 인원이 유지된 시간으로 가중해 비교했다. 모의 인원은 수강생 집단별 가중치의 합이다. 모든 평일 비교는 관측 인원을 입력하지 않은 요일별 공통 모형이다. 아래 이전 피크 평균은 앞서 차량 복귀와 학생 출발을 함께 반영했던 R이다.')
    note.append('바깥줄 관측 7건의 분 내 절대오차를 각 건에 같은 비중으로 평균했다. 이전 출발시각 수정 R → 새 R은 기준 배차 %.2f → %.2f명, 피크 배차 %.2f → %.2f명이었다. 이전 차량 복귀까지 포함한 R의 값은 각각 %.2f명과 %.2f명이었다. 이미 검토했던 현장 관측이므로 새 날짜에 대한 예측오차 추정에는 별도 자료가 필요하다.' % (scores['regular']['release'], scores['regular']['candidate'], scores['peak']['release'], scores['peak']['candidate'], scores['regular']['combined'], scores['peak']['combined']))
    note.append('11/24 차량 위치에 맞춘 재현은 15:18 대학동행 한 대에 평균 %.1f명(%.1f~%.1f명)을 냈다. 직전 시간표 차량에서 탄 모의 학생이 전부 남았다고 놓아도 평균 %.1f명(%.1f~%.1f명)이다. 이는 유입과 다른 경로를 고정한 두 조건이다. 실제로 직전 편이 운행했는지, 그날 정류장에 몇 명이 들어왔는지는 위치자료에서 확인되지 않는다.' % tuple(gap[k][m] for k in ('as_scheduled','retain_previous_riders') for m in ('mean','minimum','maximum')))
    name = '20261110-1523-admin-snu-queue-wait-01'
    final_snu = next(r for r in rows if r['source']==name and r['condition']=='candidate' and r['service']=='peak')
    note.append('11/10 15:23과 같은 화요일 피크에는 행정관 부근에 최대 네 대가 있어도 같은 방향 승차 위치에서 승객을 받는 차량은 최대 두 대였다. 두 차량에 별도 승차 줄을 허용한 감도 실험은 평균 %.1f명, 한 줄을 공유한 경우는 %.1f명이었다. 이 차이 때문에 현장에서 실제로 몇 줄로 타는지가 예측에 중요하다.' % (dated['parallel']['observations'][name]['mean'],float(final_snu['mean'])))
    values = [dated[k]['observations'][name]['mean'] for k in ('nov10_early','nov10','nov10_late')]
    note.append('11/10 현장에는 줄에 합류하고 두 대가 도착한 순서와 승차까지 189초가 기록됐다. 이 순서를 사용한 별도 재현에서 도착 시점을 앞·중간·뒤로 바꾸면 같은 분의 평균 바깥줄이 각각 '+', '.join(f'{v:.1f}명' for v in values)+'이었다. 이날의 위치 원본은 확보되지 않았고, 당시 순서를 넣은 재현과 위 표의 평일 예측은 서로 다른 비교다.')
    if 'observed_pair_joiners' in dated['nov10']:
        pair = dated['nov10']['observed_pair_joiners']
        note.append('도착시점을 중간에 둔 재현에서 15:23에 합류해 여기서 탑승한 %.1f명 상당 가운데 관측 배차의 첫 차에는 %.1f명, 두 번째 차에는 %.1f명이 탔다. 제보자 한 사람의 모형상 신원은 알 수 없다.' % (pair['cohort_boarded_here'],pair['first_vehicle'],pair['second_vehicle']))
    windows = csv_rows('5분별_유입과_대기.csv')
    def hour(stop, measure, condition):
        values=[float(r[measure]) for r in windows if r['service']=='peak' and r['condition']==condition and r['stop']==stop]
        assert len(values)==12
        return mean(values)
    note.append('화요일 14:48~15:48 한 시간의 모형 평균에서 설입행 바깥줄은 이전 차량 복귀 모형 %.1f명에서 새 R %.1f명, 대학동행 출발 전 차내 합계는 %.1f명에서 %.1f명으로 바뀌었다. 이 한 시간의 연속 현장 관측은 없다.' % (hour('admin_snu','outside','combined'),hour('admin_snu','outside','candidate'),hour('admin_daehak','aboard','combined'),hour('admin_daehak','aboard','candidate')))
    sample = csv_rows('개인승차_비교.csv')
    def episode(day, time):
        return next(r for r in sample if r['service']=='peak' and r['condition']=='candidate' and r['day']==day and r['time']==time)
    w = episode('wed','16:00')
    m = episode('mon','12:20')
    note.append('11/25 수요일 16:00 현장에서는 8명 줄 뒤에서 도착한 차에 바로 탔다. 새 피크에서 그 분 합류 후 이곳에서 탄 학생 중 다음 출발편 탑승은 %.0f%%, 바깥 대기 중앙값은 %.1f분이다. 11/23 월요일 12:20의 즉시 승차 관측에서 새 피크 모형의 바깥 대기 중앙값은 %.1f분이다. 줄의 크기와 개인의 승차시각을 따로 보아야 한다.' % (100*float(w['first_departure'])/float(w['boarded']),float(w['median_wait_seconds'])/60,float(m['median_wait_seconds'])/60))
    archive=read(HERE/'terminal_transitions.json')
    near=[e for e in archive['2026-11-25']['routes']['41841']['linked_visits'] if e['arrival'][0]<=16*3600<=e['arrival'][1]]
    def stamp(t):
        t=round(t)
        return f'{t//3600:02d}:{t//60%60:02d}:{t%60:02d}'
    if len(near)==1:
        note.append('11/25 운영사 위치 기록에도 한 차량이 행정관 부근에 들어온 구간이 '+ ' ~ '.join(stamp(t) for t in near[0]['arrival'])+'로 남아 있다. 같은 차량이 부근을 떠난 구간은 '+' ~ '.join(stamp(t) for t in near[0]['departure'])+'였다. 이 기록만으로 제보자가 어느 차에 탔는지 또는 문을 연 시각을 특정할 수는 없다.')
    residuals = csv_rows('앞배차_출발후_잔여.csv')
    r = min((r for r in residuals if r['service']=='peak' and r['condition']=='candidate'),key=lambda r:abs(float(r['time'])-(16*3600+59*60)))
    note.append('11/23 월요일 16:59 대학동행 현장에서는 만차 출발 뒤 1명이 남았다. 새 피크에서 가장 가까운 출발은 %02d:%02d, 차내 %.1f/44명, 출발 직후 바깥줄 %.1f명이다.' % (int(float(r['time'])//3600),int(float(r['time'])//60)%60,float(r['departing_load']),float(r['ledger_outside_after'])))
    card = result['card']['validation_hours']
    note.append('11/5 교내 시내버스 18개 정류장 카드자료와 비교했다. 후보 선택에서 뺀 13·15·17·19시의 시간 내 15분별 승차 비중 오차는 기존 %.1f%%p, 새 모형 %.1f%%p였다. 같은 목요일의 일부 시간대 검산이므로 다른 날짜 또는 무료 셔틀 수요에 대한 독립 검증력은 제한된다.' % (100*card['old'],100*card['candidate']))
    final = [r for r in cases if r['condition']=='candidate']
    note.append('월~금 기준 배차의 총량은 %.0f통행이다. 같은 학생 집단으로 비교한 기준·피크 10개 조건에서 미완료 %.0f명 상당, 정원 위반 %.0f건, 최장 연속 정류장 대기 %.2f분이었다. 20분 초과 대기는 기준 %.2f명 상당, 피크 %.2f명 상당이었다. 두 배차는 같은 날을 다시 실행한 대안이다.' % (sum(float(r['daily']) for r in final if r['service']=='regular'),sum(float(r['unserved']) for r in final),sum(int(r['capacity_violations']) for r in final), max(float(r['max_continuous_wait']) for r in final),*(sum(float(r['over20_weight']) for r in final if r['service']==s) for s in ('regular','peak'))))
    title = '행정관 셔틀 실측과 새 R의 비교'
    md_table = '\n'.join('| '+' | '.join(row)+' |' for row in [headers,['---']*len(headers),*lines])
    (HERE/'결과.md').write_text('# '+title+'\n\n'+note[0]+'\n\n'+md_table+'\n\n'+'\n\n'.join(note[1:])+'\n\n[연구 지도](http://127.0.0.1:8800/) · [입력과 가정](README.md) · [실측 비교 전체](현장비교.csv) · [5분별 유입·대기](5분별_유입과_대기.csv) · [평일 검증](평일검증.csv)\n',encoding='utf8')
    table = '<table><thead><tr>'+''.join('<th>'+html.escape(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(c)+'</td>' for c in row)+'</tr>' for row in lines)+'</tbody></table>'
    guide = ('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+title+'</title><style>body{font:16px/1.7 system-ui,sans-serif;max-width:960px;margin:32px auto;padding:0 18px;color:#192f3e}article{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:8px;border-bottom:1px solid #cfdae1;white-space:nowrap}a{color:#04677a}img{width:100%}</style><main><a href="/">← 하교길 지도</a><h1>'+title+'</h1><p>R261125170855 · 로컬 연구 지도</p><p>행정관에 복귀한 차량은 해당 방향 앞 배차가 떠나면 승객을 받는다. 설입행 피크에는 같은 배차의 두 대가 한 줄에서 먼저 탈 수 있는 차량부터 각각 최대 44명까지 태운다. 이 승차 순서와 1인 상당 2초는 운영 가정이다. 마지막 이용 가능 운행을 놓친 학생은 걸어서 도달할 수 있는 다른 노선과 목적지 도보를 비교한다.</p><p>'+html.escape(note[0])+'</p><article>'+table+'</article>'+''.join('<p>'+html.escape(x)+'</p>' for x in note[1:])+'<img src="/research/window.png" alt="화요일 14시 48분부터 한 시간의 5분 평균 바깥줄과 차내 인원"><p><a href="/research/guide">입력 자료와 가정</a> · <a href="/research/counts.csv">시간대별 실측 비교표</a> · <a href="/research/weekdays.csv">평일 검증표</a></p></main></html>')
    (HERE/'guide.html').write_text(guide,encoding='utf8')
    plot()


if __name__=='__main__':
    main()
