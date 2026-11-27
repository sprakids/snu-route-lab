"""Build CSVs, figure and a Korean evidence report from both read-only comparison extracts."""
from statistics import mean

from compare import HERE, OLD, NEW, DAYS, SERVICES, field_records, hhmm, read, seconds, write_csv

MODELS = (OLD, NEW)
LABEL = {'admin_snu':'행정관 설입행', 'admin_daehak':'행정관 대학동행', 'city_gate':'정문 21128',
         'city_120000195':'문화관입구 21297','regular':'기준','peak':'피크','outside':'바깥줄','onboard':'차내'}


def num(value):
    return '미산출' if value is None else f'{value:,.1f}'


def interval(r):
    if r['mean'] is None:
        return '차내 상태 미기록'
    return f"{num(r['mean'])} ({num(r['minimum'])}~{num(r['maximum'])})"


def rider_stat(e, field):
    s = e[field]
    return '표본 없음' if s is None else f"{s['median']:.0f} ({s['p10']:.0f}~{s['p90']:.0f})"


def lookup(series, **fields):
    found = [r for r in series if all(r[k]==v for k,v in fields.items())]
    assert len(found)==1,(fields,len(found))
    return found[0]


def plot(windows,counts):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':10})
    colors = {OLD:'#707c8e', NEW:'#005b9a'}
    fig, axes=plt.subplots(4,2,figsize=(12.2,10.8),sharex=True,sharey='row')
    groups=[('admin_snu','outside'),('admin_daehak','outside'),('admin_snu','onboard'),('admin_daehak','onboard')]
    start=seconds('14:48')
    for i,(node,kind) in enumerate(groups):
        for j,service in enumerate(SERVICES):
            ax=axes[i][j]
            for m in MODELS:
                if m==OLD and kind=='onboard':
                    continue
                series=[r for r in windows if (r['model'],r['service'],r['stop'],r['metric'],r['bin_seconds'])
                        ==(m,service,node,kind,60) and r['start']<'15:48']
                assert len(series)==60 and series[0]['start']=='14:48'
                ax.stairs([r['mean'] for r in series],range(61),baseline=None,color=colors[m],
                          linewidth=1.8 if m==NEW else 1.5,linestyle='-' if m==NEW else '--')
            for r in counts:
                if r['observation'][:8] not in ('20261110','20261124') or (r['model'],r['service'],r['stop'],r['metric'])!=(NEW,service,node,kind):
                    continue
                minute=(seconds(r['time'])-start)/60
                if not 0<=minute<60:
                    continue
                y=r['observed_low']
                ax.plot([minute,minute+1],[y,y],c='#aa3900',lw=3,zorder=5)
                ax.scatter(minute+.5,y,c='#aa3900',s=29,zorder=6)
                ax.annotate(str(y),(minute+.5,y),xytext=(6,6),textcoords='offset points',color='#873200',fontsize=9)
            ax.axvline(30,color='#aa3900',lw=.9,ls=':',alpha=.6)
            ax.grid(axis='y',color='#dae2e6',lw=.6)
            ax.spines[['top','right']].set_visible(False)
            ax.set_xlim(0,60)
            ax.set_ylim(bottom=0)
            if j==0:
                ax.set_ylabel(f"{LABEL[node]} {LABEL[kind]}\n(명 상당)")
            if i==0:
                ax.set_title(f'{LABEL[service]} 배차',fontweight='bold')
            if i==3:
                ax.set_xticks(range(0,61,10),[hhmm(start+m*60) for m in range(0,61,10)])
                ax.set_xlabel('화요일 시각')
    fig.suptitle('행정관 셔틀의 출발 전 대기 인원',fontsize=19,fontweight='bold',y=.99)
    handles=[Line2D([],[],color=colors[OLD],ls='--',label='이전 R'),Line2D([],[],color=colors[NEW],label='새 R'),
             Line2D([],[],marker='o',color='#aa3900',ls='',label='현장 계수')]
    fig.legend(handles=handles,loc='upper center',ncol=3,bbox_to_anchor=(.5,.96),frameon=False)
    fig.text(.08,.012,'각 선은 모형의 1분 시간가중 평균입니다. 실측 15:18은 11월 24일, 15:23은 11월 10일 관측입니다. 이전 R은 출발 전 차내 인원을 기록하지 않았습니다.',fontsize=9)
    fig.tight_layout(rect=(.015,.035,.99,.92))
    fig.savefig(HERE/'화요일_행정관_대기.png',dpi=145,bbox_inches='tight')
    plt.close(fig)


def publish():
    blobs=[read(HERE/f'R{m}.json') for m in MODELS]
    def combine(key):
        return [r for b in blobs for r in b[key]]
    counts,windows,episodes,checks=map(combine,('minute_counts','windows','episodes','checks'))
    field=field_records()
    for b in blobs:
        assert b['source_sha256'].items()>=field['files'].items()
    assert len(checks)==20 and len(counts)==len(field['records'])*len(MODELS)*len(SERVICES)
    for day in DAYS:
        values=[r['demand'] for r in checks if r['day']==day]
        assert len(values)==4 and max(values)-min(values)<1e-5
    for r in (r for r in windows if r['bin_seconds']==3600 and r['mean'] is not None):
        for width,n in [(60,60),(300,12)]:
            bins=[v['mean'] for v in windows if v['bin_seconds']==width and v['start']<'15:48'
                  and all(r[k]==v[k] for k in ('model','service','stop','metric'))]
            assert len(bins)==n and abs(mean(bins)-r['mean'])<1e-6
    for e in (e for e in episodes if 'departures' in e):
        for d in e['departures']:
            assert abs(d['ledger_outside_after']-d['map_outside_after'])<1e-4
    write_csv('실측_인원_비교.csv',counts)
    write_csv('화요일_시간대별.csv',windows)
    write_csv('평일_검증.csv',checks)
    plot(windows,counts)
    text=['# 행정관 셔틀 대기 예측과 현장 관측 비교','',
         f'이전 R{OLD}과 새 후보 R{NEW}의 검증 완료 원장을 같은 요일·배차로 짝지었다. 시뮬레이션 인원은 학생 집단의 가중치를 합한 명 상당이다. 두 배차는 같은 학생을 대상으로 한 별개 가정이다.',
         '', '새 R은 약 25%의 강좌가 2~10분(최빈 5분) 일찍 끝나고, 약 25%의 하교 이동이 5~40분(최빈 15분) 추가로 머문 뒤 출발한다고 가정한다. 두 효과는 겹칠 수 있다. 행정관 두 방향 셔틀은 직전 서로 다른 출발시각 간격의 절반과 180초 중 짧은 시간만큼 일찍 문을 연다. 이 숫자는 모형 가정이다.',
         '', '## 현장에서 센 인원','',
         '모형 값은 보고된 1분 동안의 평균 (최소~최대)이다. 각 상태가 실제로 지속된 시간만큼 평균에 반영했다. 괄호는 해당 분의 모형 변동 폭이다. 날짜별 실제 차량의 초 단위 운행은 알려져 있지 않다.','',
         '| 날짜·시각 | 위치와 관측 대상 | 실측 | 기준 이전 R | 기준 새 R | 피크 이전 R | 피크 새 R |',
         '|---|---|---:|---:|---:|---:|---:|']
    for obsid,_,stop,time,kind,tgt in field['records']:
        values=[interval(lookup(counts,observation=obsid,model=m,service=s)) for s in SERVICES for m in MODELS]
        text.append('| '+' | '.join([f'11/{obsid[6:8]} {time}',f'{LABEL[stop]} {LABEL[kind]}',
                      str(tgt[0]) if tgt[0]==tgt[1] else f'{tgt[0]}~{tgt[1]}',*values])+' |')
    arrival_id=field['arrival_boarding']['observation_id']
    loss={(m,s):mean(r['expected_abs_error'] for r in counts
                     if r['model']==m and r['service']==s and r['metric']=='outside' and r['observation']!=arrival_id) for m in MODELS for s in SERVICES}
    text[2:2]=[f"**6건의 바깥줄 관측에서 기준 배차의 평균절대오차는 {loss[OLD,'regular']:.2f}명에서 {loss[NEW,'regular']:.2f}명으로 줄었지만, 피크 배차는 {loss[OLD,'peak']:.2f}명에서 {loss[NEW,'peak']:.2f}명으로 커졌다.** 15:18 설입행의 개선과 15:23 설입행의 과소예측이 함께 나타났다. 이번 비교 결과는 후보의 전면 교체를 뒷받침하지 않는다.",'']
    text+=['','문화관은 제보의 정류장 명칭을 21297로 대응했다. 정문은 설입 방면 여러 노선을 함께 기다리는 줄이다. 15:23의 67명은 관측자 포함이다. 15:18 차내 실측 17명은 당시 한 대에 타 있던 인원이다. 새 R에서도 이 1분 동안 대기 중인 해당 방향 차량이 한 대이고, 직전 정류장에서 계속 타고 온 승객이 0명임을 확인했다.',
           '', '### 11월 25일 수요일 16:00 차가 도착했을 때','',
           '행정관 설입행 바깥줄은 8명이었고 제보자는 도착한 차에 바로 탔다. 시간을 초 단위로 재지 않았다. 제보자 포함 여부와 함께 승차한 총원은 미상이다. 이 관측은 도착 직전의 줄과 이어진 승차 순서로 평가한다. 분 안의 임의 시각을 가정하는 종전 6건 오차 평균에서는 별도로 다룬다.','']
    def exact_clock(t):
        return f'{int(t)//3600:02d}:{int(t)//60%60:02d}:{int(t)%60:02d}'
    for s in SERVICES:
        e=lookup(episodes,kind='arriving_vehicle_1600',model=NEW,service=s)
        queue=lookup(counts,observation=arrival_id,model=NEW,service=s)
        openings=', '.join(map(exact_clock,e['boardable_arrivals_in_minute']))
        phase=f"그 1분의 개문 시각은 {openings}이다." if openings else "그 1분에 새로 문을 연 차량은 0대다."
        text.append(f"- {LABEL[s]} 배차에서 바깥줄은 평균 {interval(queue)}명 상당이다. {phase} 앞뒤 개문은 "
                    +f"{exact_clock(e['opening_before'])}, {exact_clock(e['opening_after'])}이다.")
    text+=['', '[관측 원문과 현장 확인](../../field_observations_2026-11-25/boarding_admin_snu_1600.json) · [당일 위치 기록을 적용한 재현](../../field_observations_2026-11-25/README.md)',
           '', '### 15:23에 줄이 얼마나 줄었는지 해석할 때','']
    for s in SERVICES:
        outside,inside=[lookup(windows,model=NEW,service=s,stop='admin_snu',metric=k,start='15:23',bin_seconds=60)['mean'] for k in ('outside','onboard')]
        text.append(f"- {LABEL[s]} 배차의 새 R에서는 분평균 {outside:.1f}명이 밖에 서 있고 {inside:.1f}명이 이미 차에 타 있다. 합계 {outside+inside:.1f}명 상당이 출발을 기다린다.")
    text+=['', '11월 10일 현장에서는 관측자가 줄에 선 뒤에 두 대가 함께 도착했다. 도착시각은 15:24 이후였다는 대략적인 기억이다. 반면 새 R의 15:24 출발 두 대는 기준 배차에서 15:22:00, 피크에서 15:22:30에 문을 연다. 같은 시간에 정류장에 도달한 학생 수도, 도착한 사람 중 바깥에 남는 비율도 바뀔 수 있다. 실측 67명과 비교할 값은 바깥줄이다. 두 모형의 차이에는 수요 시각 변경과 사전 승차가 함께 작용하므로 두 효과의 기여율은 이 비교만으로 분리하기 어렵다.',
           '', '## 바깥줄 오차와 전후 30분','',
           '직접 계수한 바깥줄 6건에 각각 같은 비중을 주었다. 초가 미상이므로 분 안에서 균일하게 관측했다고 가정하고, 각 순간의 절대오차를 시간가중했다. 33~39명은 해당 범위까지의 거리로 계산했다. 차량 출발 후 잔여, 차내 인원, 개인 대기시간은 이 집계와 별도로 평가했다.','',
           '| 배차 | 이전 R 평균절대오차 | 새 R 평균절대오차 | 개선 / 악화 / 동일 |','|---|---:|---:|---:|']
    for s in SERVICES:
        a,b=[[lookup(counts,model=m,service=s,observation=row[0])['expected_abs_error']
              for row in field['records'] if row[4]=='outside' and row[0]!=arrival_id] for m in MODELS]
        changes=[y-x for x,y in zip(a,b)]
        text.append(f'| {LABEL[s]} | {mean(a):.2f}명 | {mean(b):.2f}명 | {sum(x < -1e-6 for x in changes)} / {sum(x > 1e-6 for x in changes)} / {sum(abs(x)<=1e-6 for x in changes)} |')
    text+=['','먼저 캠퍼스 전체에서 실제로 건물을 나선 모의 하교 인원을 집계했다. 같은 준비 수요를 사용하므로 배차별 출발량이 같다.','',
           '| 출발 시간대 (끝 시각 제외) | 이전 R | 새 R |','|---|---:|---:|']
    for window in ('14:48-15:48','15:00-15:16','15:16-15:19'):
        vals=[]
        for m in MODELS:
            amounts=[lookup(episodes,kind='campus_departures',model=m,service=s)['departures_by_window'][window] for s in SERVICES]
            assert abs(amounts[0]-amounts[1])<1e-6
            vals.append(num(amounts[0]))
        text.append('| '+' | '.join([window,*vals])+' |')
    text+=['','| 14:48 이상~15:48 미만 | 배차 | 이전 R 평균 | 새 R 평균 | 이전 R 최고 | 새 R 최고 |','|---|---|---:|---:|---:|---:|']
    for s in SERVICES:
        for stop in ('admin_snu','admin_daehak'):
            for kind in ('outside','onboard'):
                a,b=[lookup(windows,model=m,service=s,stop=stop,metric=kind,bin_seconds=3600) for m in MODELS]
                text.append(f"| {LABEL[stop]} {LABEL[kind]} | {LABEL[s]} | {num(a['mean'])} | {num(b['mean'])} | {num(a['maximum'])} | {num(b['maximum'])} |")
    text+=['','시간대 전체에는 연속 현장 계수가 없어 모형끼리 비교했다. 그래프 선은 1분 평균이고, 위 표의 최고는 짧은 구간까지 포함한 순간 최고다. CSV는 1분·5분·한 시간 요약을 담으며 15:48분은 별도 1분 행으로 제공한다.',
           '','![화요일 행정관 셔틀 대기 인원](화요일_행정관_대기.png)','',
           '## 개인 탑승 경험과 차량 출발 직후','',
           '11월 10일 15:23 행정관 설입행 관측자는 줄 합류부터 두 번째 차에 타기까지 189초, 탑승 후 출발까지 30초, 합계 219초를 쟀다. 아래는 같은 분에 해당 승차장에 도착해 그곳에서 승차한 모의 집단의 가중 중앙값 (10~90백분위), 단위는 초다. 한 사람의 실측과 같은 사람을 추적한 비교는 할 수 없다. 이전 R은 승차와 출발을 같은 사건으로 처리했다.','',
           '| 배차 | 모형 | 비교 집단(명 상당) | 줄 합류→승차 | 승차→출발 | 줄 합류→출발 |','|---|---|---:|---:|---:|---:|']
    for s in SERVICES:
        for m in MODELS:
            e=lookup(episodes,kind='individual_1523',model=m,service=s)
            dwell=rider_stat(e,'onboard_s') if m==NEW else '동시 처리'
            text.append(f"| {LABEL[s]} | {'이전' if m==OLD else '새'} R | {num(e['boarded_mass'])} | {rider_stat(e,'outside_s')} | {dwell} | {rider_stat(e,'combined_s')} |")
    text+=['','관측자는 함께 온 두 대 중 두 번째 차에 탔다. 15:23에 줄에 섰고 219초 후 출발했으므로 관측 차량의 출발 가능 구간은 15:26:39 이상~15:27:39 미만이다. 실제 차량의 도착 초는 미측정이다.','',
           '| 배차 | 이전 R의 해당 구간 출발 | 새 R의 해당 구간 출발 |','|---|---|---|']
    for s in SERVICES:
        desc=[]
        for m in MODELS:
            deps=lookup(episodes,kind='individual_1523',model=m,service=s)['compatible_departures']
            desc.append(', '.join(hhmm(t)+f' {sum(e["departure"]==t for e in deps)}대' for t in sorted({e['departure'] for e in deps})) or '0대')
        text.append('| '+' | '.join([LABEL[s],*desc])+' |')
    text+=['','11월 23일 12:20 행정관 설입행은 줄이 있었고 제보자가 곧바로 탔다. 정확한 인원과 초는 미측정이다. 같은 분에 도착한 뒤 그 정류장에서 셔틀에 탄 모의 집단으로 비교했다.','',
           '| 배차 | 모형 | 관측 분 바깥줄 평균 (범위) | 해당 분에 도착해 탄 집단 | 그 분 안에 도착·탑승 완료 | 개인 줄 대기 중앙값 (10~90백분위), 초 |','|---|---|---:|---:|---:|---:|']
    for s in SERVICES:
        for m in MODELS:
            e=lookup(episodes,kind='immediate',model=m,service=s)
            text.append(f"| {LABEL[s]} | {'이전' if m==OLD else '새'} R | {interval(e['queue'])} | {num(e['boarded_mass'])} | {num(e['same_minute_boards_mass'])} | {rider_stat(e,'outside_s')} |")
    text+=['','11월 23일 16:59 대학동행은 만차 출발 뒤 바깥에 1명이 남았다. 같은 분에 모형 출발이 없으면 가장 가까운 편에서 출발 단계를 맞춰 비교했다. 현장 차량의 개인별 승차시각과 출발 당시 정확한 탑승 인원은 미측정이다.',
           '','| 배차 | 모형 | 모형 출발시각 | 실측 분과 일치 | 차내/정원 | 출발 직후 바깥 전체 | 그중 승차 준비를 마치고 남은 줄 |','|---|---|---|---|---:|---:|---:|']
    for s in SERVICES:
        for m in MODELS:
            for d in lookup(episodes,kind='residual',model=m,service=s)['departures']:
                text.append(f"| {LABEL[s]} | {'이전' if m==OLD else '새'} R | {hhmm(d['time'])} | {'예' if d['time_matched'] else '아니요'} | {num(d['departing_load'])}/{d['capacity']} | {num(d['ledger_outside_after'])} | {num(d['compatible_left'])} |")
    text+=['','바깥 전체는 학생별 정류장 도착부터 퇴장까지의 원장에서 해당 출발 처리 직후에 남은 가중 인원이다. 화면용 곡선의 출발 직후 값과도 대조했다. 승차 준비 중인 사람을 포함하므로 차량 사건의 준비 완료 줄과 차이가 생길 수 있다.',
           '', '## 평일 운행 검증','',
           '| 모형 | 평일 기준 배차 하교 합계 | 최장 한 정류장 대기 | 20분 초과 가중 대기 | 정원 위반 | 미완료 이동 |','|---|---:|---:|---:|---:|---:|']
    for m in MODELS:
        rows=[r for r in checks if r['model']==m]
        text.append(f"| R{m} | {sum(r['demand'] for r in rows if r['service']=='regular'):,.1f} | {max(r['max_wait_min'] for r in rows):.2f}분 | {sum(r['over20_mass'] for r in rows):.3f} | {sum(r['capacity_violations'] for r in rows)} | {sum(r['unserved'] for r in rows):.3f} |")
    text+=['','하교 합계는 5개 요일의 기준 배차에서만 합산했다. 나머지 열은 모형별 10개 실행에서 집계한 내부 검증 지표다. 각 요일의 네 조건에서 하루 하교 인원이 일치했다. 20분은 한 정류장에서 이어진 바깥 대기를 기준으로 한다.',
           '', '아래는 15~19시 전체 정류장의 바깥 대기 누계(명·분)다. 10명이 3분씩 기다리면 30명·분이다. 차에 미리 타면 출발 전까지 차 안에서 보내는 시간이 생기므로 바깥 대기 감소만으로 귀가가 그만큼 빨라졌다고 해석할 수 없다.',
           '','| 요일 | 기준 이전 R | 기준 새 R | 피크 이전 R | 피크 새 R |','|---|---:|---:|---:|---:|']
    for day,label in zip(DAYS,'월화수목금'):
        vals=[num(lookup(checks,model=m,service=s,day=day)['network_outside_person_min_1500_1900']) for s in SERVICES for m in MODELS]
        text.append('| '+' | '.join([label,*vals])+' |')
    text+=['', '## 재현과 자료','',
           '시간대별 바깥줄의 평균은 개인별 원장의 정류장 체류시간과 가중치로, 차내 평균은 출발 전 승차 기록으로 별도로 검산했다. 관측을 이미 참조해 만든 연구 후보의 비교이므로 새 날짜에 대한 예측 정확도는 추가 관측으로 평가해야 한다.',
           '', '- [현장 인원 비교 CSV](실측_인원_비교.csv) · [화요일 시간대별 CSV](화요일_시간대별.csv) · [평일 검증 CSV](평일_검증.csv)',
           '- [이전 R 집계와 원본 SHA-256](R261124110718.json) · [새 R 집계와 원본 SHA-256](R261124160531.json)',
           '- [실측 대조 코드](compare.py) · [표와 그래프 생성 코드](publish.py)',
           '', '같은 폴더에서 Python 3.11 이상으로 아래 명령을 순서대로 실행한다. 그래프 생성에는 Matplotlib와 한글 글꼴 맑은 고딕이 필요하다. 기존 검증 원장만 읽는다.','',
           '```powershell','python compare.py --model 261124110718','python compare.py --model 261124160531','python publish.py','```','']
    (HERE/'실측_비교.md').write_text('\n'.join(text),encoding='utf8')


if __name__=='__main__':
    publish()
