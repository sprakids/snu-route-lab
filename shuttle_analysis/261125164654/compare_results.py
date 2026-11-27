"""Produce matched diagnostics. The field counts are read only after simulation."""
import csv
import json
import math
import statistics
from pathlib import Path

HERE=Path(__file__).resolve().parent
CONDS=('baseline','supply','release','combined')
LABELS=('기존 R','차량만','출발만','두 수정')

def read(path):
    return json.loads(path.read_text(encoding='utf8'))

def write_csv(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def plot_windows(rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.family']='Malgun Gothic'
    fig,axes=plt.subplots(2,2,figsize=(10,6),sharex=True,layout='constrained')
    for axis,(stop,metric,title) in zip(axes.flat,(
            ('admin_snu','outside','서울대입구역행 · 바깥줄'),
            ('admin_snu','aboard','서울대입구역행 · 출발 전 차내'),
            ('admin_daehak','outside','대학동행 · 바깥줄'),
            ('admin_daehak','aboard','대학동행 · 출발 전 차내'))):
        for condition,label,color in [('baseline','기존 R','#777777'),('combined','두 수정 적용','#006a86')]:
            values=[r[metric] for r in rows if r['stop']==stop and r['service']=='peak' and r['condition']==condition]
            assert len(values)==12
            axis.stairs(values,range(0,61,5),baseline=None,color=color,lw=2,label=label)
        axis.axvline(30,color='#9a8191',lw=.9,ls=':')
        observation={('admin_snu','outside'):6,('admin_daehak','aboard'):17}.get((stop,metric))
        if observation is not None:
            axis.scatter([30.5],[observation],marker='D',s=35,color='#a23b28',zorder=3,label='15:18 현장 계수')
        axis.set(title=title,ylabel='인원 (명)',ylim=(0,None))
        axis.grid(axis='y',alpha=.18)
        axis.set_xticks([0,15,30,45,60],['14:48','15:03','15:18','15:33','15:48'])
    axes[0,0].legend(frameon=False,fontsize=9)
    fig.suptitle('화요일 피크 배차 · 15:18 전후 30분\n모형은 5분 평균, 현장 계수는 해당 분 중 한 시점',fontweight='bold')
    fig.savefig(HERE/'화요일_대기_비교.png',dpi=160)
    plt.close(fig)

def main():
    summaries={(d,s,c):read(HERE/'runs'/c/f'{s}-{d}'/'summary.json')
               for d in ('mon','tue','wed','thu','fri') for s in ('regular','peak') for c in CONDS}
    checks=[]
    observations=[]
    windows=[]
    for (d,s,c),r in summaries.items():
        baseline=summaries[d,s,'baseline']
        assert r['daily']==baseline['daily'] and r['identity']==baseline['identity']
        assert r['departure_identity']==summaries[d,s,'supply' if c in ('baseline','supply') else 'combined']['departure_identity']
        assert r['departure_identity']==summaries[d,'regular',c]['departure_identity']
        checks.append({k:r[k] for k in ('day','service','condition','daily','max_continuous_wait','over20_weight','unserved','capacity_violations','time_limited_departures')})
        for oid,o in r['observations'].items():
            observations.append(dict(day=d,service=s,condition=c,observation=oid,minute=o['minute'],
                metric=o['kind'],stop=o['stop'],obs_min=o['observed'][0],obs_max=o['observed'][1],
                comparable=o['matched'],mean=o.get('mean'),minimum=o.get('minimum'),maximum=o.get('maximum'),
                abs_error=o.get('expected_abs_error')))
        windows.extend(dict(condition=c,service=s,**w) for w in r['windows'])
    write_csv(HERE/'현장비교.csv',observations)
    write_csv(HERE/'평일검증.csv',checks)
    write_csv(HERE/'화요일_5분_대기.csv',windows)
    plot_windows(windows)
    desc=[]
    episodes=[dict(day=d,service=s,condition=c,events=r['episodes'])
              for (d,s,c),r in summaries.items() if r['episodes']]
    (HERE/'승차와_출발후_잔여.json').write_text(json.dumps(episodes,indent=2,ensure_ascii=False),encoding='utf8')
    def append(*lines):
        desc.extend(lines)
    append('# 행정관 셔틀 복귀·승차와 강좌 종료시각 비교','',
           '기존 R261124160531과 R261125164654의 평일 5일 × 2배차를 같은 최초 경로·목적지·통행 집단으로 비교했다. 수치는 모의 인원 상당이다. 네 조건에서 각 요일의 원래 하교 통행량과 학생별 가중치가 일치한다.','',
           '## 분 단위 현장 비교','',
           '표는 보고된 1분의 시간가중 평균이다. [현장비교.csv](현장비교.csv)에 분 내 최소·최대와 시간가중 절대오차를 함께 기록했다. 차내 관측은 같은 방향에서 한 대만 서 있고 그 차량에 남아 있던 통과 승객이 없을 때 비교했다.','')
    for service,title in [('regular','기준 배차'),('peak','피크 배차')]:
        append('### '+title,'','| 날짜 | 시각·장소 | 실측 | '+' | '.join(LABELS)+' |',
               '|---|---|---:|---:|---:|---:|---:|')
        names={'admin_snu':'설입행 바깥','city_120000195':'문화관 바깥','city_gate':'정문 바깥','admin_daehak':'대학동행 차내'}
        for row in observations:
            if row['service']!=service or row['condition']!='baseline':
                continue
            oid=row['observation']
            vs=[summaries[row['day'],service,c]['observations'][oid] for c in CONDS]
            cells=[f"{v['mean']:.1f}" if v['matched'] else '차량 특정 불가' for v in vs]
            observed=str(row['obs_min']) if row['obs_min']==row['obs_max'] else f"{row['obs_min']}~{row['obs_max']}"
            append(f"| {oid[4:6]}/{oid[6:8]} | {row['minute']} {names[row['stop']]} | {observed} | "+' | '.join(cells)+' |')
        scores=[statistics.mean(o['abs_error'] for o in observations if o['service']==service and o['condition']==c and o['metric']=='outside') for c in CONDS]
        append('', '바깥줄 일곱 관측의 분 내 절대오차를 같은 비중으로 평균하면 위의 조건 순서대로 '+', '.join(f'{n:.2f}명' for n in scores)+'이다.','')
    append('## 승차와 차량이 떠난 뒤 남은 줄','',
           '11/23 월요일 16:59에 대학동행이 만차로 떠난 뒤 1명이 남았다. 관측 분에 출발 사건이 없는 경우 가장 가까운 편을 표에 표시했다.','',
           '| 배차 | 조건 | 비교한 출발 | 차내 / 정원 | 출발 직후 바깥 |','|---|---|---|---:|---:|')
    for s in ('regular','peak'):
        for c,label in zip(CONDS,LABELS):
            m=summaries['mon',s,c]['episodes']['16:59'][0]
            secs=int(m['time'])
            append(f"| {s} | {label} | {secs//3600:02}:{secs//60%60:02}:{secs%60:02} | {m['departing_load']:.1f} / {m['capacity']} | {m['ledger_outside_after']:.1f} |")
    append('', '아래 표는 해당 분에 승차장에 진입해서 결국 그 줄에서 탑승한 통행 중, 진입 당시 가장 가까운 출발 묶음을 탄 비율이다. 분모가 0이면 비교할 수 없다. 문을 연 채 기다리고 있던 차도 포함한다. 한 제보자의 정확한 대기시간이나 같은 두 번째 버스에 탔는지까지 식별할 수는 없다.','',
           '| 날짜·시각 | 배차 | 기존 → 두 수정 | 바깥 대기 중앙값(초) 기존 → 두 수정 | 해당 분 개문 차량 수 (기존 → 두 수정) |','|---|---|---:|---:|---:|')
    for d,dt,t in [('mon','11/23','12:20'),('tue','11/10','15:23'),('wed','11/25','16:00')]:
        for s in ('regular','peak'):
            rows=[summaries[d,s,c]['episodes'][t] for c in ('baseline','combined')]
            values=[f"{v['next_departure_group']/v['boarded_cohort']:.0%} (분모 {v['boarded_cohort']:.1f}명)" if v['boarded_cohort'] else '분모 0' for v in rows]
            doors=' → '.join(str(v['doors_opened_within_minute']) for v in rows)
            waits=' → '.join(f"{v['outside_s']['median']:.0f}" if v['outside_s'] else '미산출' for v in rows)
            append(f"| {dt} {t} | {s} | "+' → '.join(values)+f' | {waits} | {doors} |')
    append('', '## 15:18 전후 30분','',
           '화요일 14:48~15:48의 5분별 유입량과 평균 대기는 [화요일_5분_대기.csv](화요일_5분_대기.csv)에 있다. 전후 구간의 연속 현장 계수는 확보되지 않았다. 차내 열은 그 방향에서 출발을 기다리는 차들의 합이다.','',
           '![화요일 피크 배차 14시 48분부터 15시 48분까지 설입행과 대학동행의 바깥줄과 차내 인원](화요일_대기_비교.png)','',
           '| 배차 | 승차장 | 1시간 유입 기존 → 두 수정 | 평균 바깥줄 기존 → 두 수정 | 평균 차내 기존 → 두 수정 |',
           '|---|---|---:|---:|---:|')
    for s in ('regular','peak'):
        for k,label in [('admin_snu','설입행'),('admin_daehak','대학동행')]:
            cells=[]
            for metric in ('arrivals','outside','aboard'):
                points=[]
                for c in ('baseline','combined'):
                    vals=[v[metric] for v in summaries['tue',s,c]['windows'] if v['stop']==k]
                    points.append(sum(vals) if metric=='arrivals' else statistics.mean(vals))
                cells.append(' → '.join(f'{v:.1f}' for v in points))
            append(f"| {s} | {label} | "+' | '.join(cells)+' |')
    combined=[r for r in checks if r['condition']=='combined']
    total=sum(r['daily'] for r in combined if r['service']=='regular')
    append('', '## 평일 전체 검산','',f"두 수정 조건에서 기준 배차 월~금 총 {total:,.1f}명 상당이며, 기준·피크 10조건의 모든 정류장 중 최장 연속 바깥 대기는 {max(r['max_continuous_wait'] for r in combined):.2f}분이다. 20분 초과 통행 가중치의 조건별 최댓값은 {max(r['over20_weight'] for r in combined):.2f}명이다. 조건별 정원 위반은 최대 {max(r['capacity_violations'] for r in combined)}, 미완료는 최대 {max(r['unserved'] for r in combined):.2f}명이다. 개별 집단의 질량, FIFO 승차 순서, 차량별 승하차·재차, 지도 대기곡선과 개인 대기 원장을 검산했다. [평일검증.csv](평일검증.csv)",'')
    (HERE/'결과.md').write_text('\n'.join(desc),encoding='utf8')

if __name__=='__main__':
    main()
