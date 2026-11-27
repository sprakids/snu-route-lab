"""Export verified corrected supply and a traceable, explicitly limited explanation."""
from pathlib import Path
from collections import Counter
import json,csv,shutil,math
import capacity_model as base
from prepare_walk_choices import read
from build_walk_choice_documentation import render_md

ROOT=Path(__file__).resolve().parent
WORK=ROOT/'peak_pair_correction_2026-11-10'
CAP=ROOT/'capacity44_correction_2026-11-10'
H=ROOT/'crowding_walk_choices_2026-11-10/initial_refit_H'

def copy_once(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():assert target.read_bytes()==source.read_bytes(),str(target)
    else:shutil.copy2(source,target)

def build():
    verified=read(WORK/'independent_verification.json');assert verified['status']=='PASS' and verified['simulation_runs']==10
    assert read(WORK/'export_completion.json')['status']=='PASS'
    public=ROOT/'public';dataset=public/'data/capacity_v11'
    for name in ['common','charts',*[f'{s}-{d}' for s in ('regular','peak') for d in base.DAYS.values()]]:
        for suffix in ('.json','.json.gz'):copy_once(WORK/'public_data'/f'{name}{suffix}',dataset/f'{name}{suffix}')
    for suffix in ('.json','.json.gz'):copy_once(WORK/'public_data'/f'half_hour{suffix}',public/'data/half_hour_v1'/f'capacity_v11{suffix}')
    review=read(WORK/'all_stops_waits.json');review['route_change_distribution']={}
    for s in ('regular','peak'):
        review['route_change_distribution'][s]={}
        for d in base.DAYS.values():
            audit=read(WORK/f'audit-{s}-{d}.json.gz');hist=Counter()
            for trip in audit['legs']:hist[len(trip['history'])]+=trip['weight']
            total=sum(hist.values());review['route_change_distribution'][s][d]={'mean':sum(n*w for n,w in hist.items())/total,
                    'input_weight':total,'weight_by_count':dict(sorted(hist.items())),'maximum_observed_changes':max(hist),'hard_limit':None}
            old=read(WORK/f'analysis-{s}-{d}.json')['baseline_all_stops']
            for row in review['rows']:
                if row['scenario']==s and row['weekday']==d:row['before_max_wait_min']=old.get(str(row['node']),{}).get('max_continuous_wait_min',0.)
    review['walking_curve']=read(public/'data/walk_review_v1/report.json')['walking_curve']
    base.OUT=public/'data/capacity_review_v1';base.OUT.mkdir(exist_ok=True);base.public('report.json',review)
    csv_path=public/'capacity-correction-waits.csv'
    with csv_path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,list(review['rows'][0]));writer.writeheader();writer.writerows(review['rows'])
    comparisons=[];labels={'mon':'월','tue':'화','wed':'수','thu':'목','fri':'금'}
    for s in ('regular','peak'):
        for d in base.DAYS.values():
            a=read(CAP/f'analysis-{s}-{d}.json');b=read(WORK/f'analysis-{s}-{d}.json')
            a,b=a['paired_metrics'],b['paired_metrics']
            comparisons.append({'scenario':s,'weekday':d,'old_wait':a['wait_seconds']['before'],'cap_wait':a['wait_seconds']['after'],
                 'pair_wait':b['wait_seconds']['after'],'old_total':a['total_seconds']['before'],'cap_total':a['total_seconds']['after'],
                 'pair_total':b['total_seconds']['after'],'old_walk':a['walking_seconds']['before'],'cap_walk':a['walking_seconds']['after'],
                 'pair_walk':b['walking_seconds']['after']})
    table='\n'.join(f"| {'기준4분' if r['scenario']=='regular' else '피크3분'} | {labels[r['weekday']]} | {r['old_wait']:.2f} / {r['cap_wait']:.2f} / {r['pair_wait']:.2f} | {r['old_walk']:.2f} / {r['cap_walk']:.2f} / {r['pair_walk']:.2f} | {r['old_total']:.2f} / {r['cap_total']:.2f} / {r['pair_total']:.2f} |" for r in comparisons)
    diagnostic=read(WORK/'new_field_diagnostic.json')
    names={'v9_60_single':'이전60·1대','capacity44_single':'44·1대','capacity44_pair':'44·피크2대'}
    fields='\n'.join(f"| {names[r['model']]} | {'기준4분' if r['scenario']=='regular' else '피크3분'} | {r['uniform_minute_mean']:.2f} | {r['minute_range'][0]:.2f}~{r['minute_range'][1]:.2f} | {r['expected_absolute_count_error']:.2f} |" for r in diagnostic['queue_minute_comparison'])
    max_wait=verified['all_stop_review']['maximum_continuous_wait_min'];over=verified['all_stop_review']['over_20_minute_weight']
    md=f'''# 설입 셔틀 정원44명과 피크 두 대 묶음 · v11

행정관→서울대입구역 통학셔틀의 주간 정원을 사용자 최종 정정에 따라 60명 가정에서 44명/차로 바꿨습니다. 피크 두 대 묶음 운행은 반복 탑승 경험과 사용자께서 전달한 이용자 공통 증언을 근거로 공급 시나리오에 반영했습니다. 수강 기반 가중 수요·목적지·출발시각·행동계수·속도·보행망은 유지했습니다.

## 정원과 묶음의 적용 범위

설입 행정관 노선에만 주간44명/차를 적용합니다. 다른 통학60·역순환25·시내50·마을24 참고정원은 유지합니다. 21시 이후 도서관 야간 그룹의60명은 별도 확인되지 않은 기존 가정입니다. 해당 차량이 터미널에서 출발할 때 정원을 정하며 이동 중21시가 지나도 같은 차량의 정원이 바뀌지 않습니다.

가정한15:00~19:00 창의 각 명목 배차에44명 차량 두 대를 동시에 생성합니다. 이 창은 기존 모형의 피크 창이며 실제 피크 시작·종료를 새로 실측한 값이 아닙니다. 두 대를88명짜리 한 대로 합치거나 간격을 반으로 균등화하지 않습니다. 차량별 재차·하차·여석·FIFO·남은 줄을 각각 계산합니다. 지도에서는 같은 위치의 두 차량을 옆으로 구분해 표시합니다.

기준 시나리오의 기존4분과 피크 시나리오의 기존3분 명목 시계를 각각 유지했습니다. 매3분 정확히 두 대가 온다는 실측이 확보된 것은 아닙니다. 경로 추천 사이트에는 기준 regular 결과를 사용하며4분 시계를 유지합니다. 실제 배차는 시간표와 차량 운행일지로 추가 확인해야 합니다.

## 효과를 분리한 재계산

이전 v9의60명·1대, 정원만44명인 비교안,44명·피크2대인 공급안을 분리했습니다. 아래 값은 같은 원래 가중 통행 집단의 모형 평균이며 실제 고유 학생 수·실측 소요시간이 아닙니다. 각 칸은 이전60·1대 / 44·1대 / 44·피크2대 순서입니다. 대기는 여러 정류장의 누적값이고 총시간은 모형 출발부터 같은 목적지까지입니다. 줄에서 이탈한 통행과 추가 도보도 포함합니다. 단위는 분입니다.

| 명목 배차 | 요일 | 누적 대기 | 도보 | 총시간 |
|---|---|---:|---:|---:|
{table}

이는 공급 가정을 바꾼 모형 비교입니다. 실제 대기 개선이나 새 행동 알고리즘의 우월성을 입증하는 표가 아닙니다. 선호비용·확률·승차 과정을 분리한 새 알고리즘 프로토타입은 별도 오프라인 실험이며 이 운영 공급 정정에 섞지 않았습니다.

## 화요일15:23 현장 보고

최종 보고는 버스 밖 줄에 본인 포함67명, 앞66명, 줄 합류→탑승189초, 탑승→출발30초, 합류→출발219초입니다. 날짜11/10은 대화일과 화요일을 근거로 기록했으며 별도 날짜 확답은 없었습니다. 이미 버스에 탄 사람은67명에 포함하지 않습니다. 두 대가 함께 도착했고 그중 두 번째에 탔습니다. 15:23은 줄 합류 시각이고, 차량은 그 후에 도착한 것으로 회상했습니다. ‘아마15:24 이후’는 정확한 시각이나 엄격한 하한이 아닙니다.

합류 시각은[15:23:00,15:24:00)로 유지합니다. 보고한 상대시간으로 유도한 탑승 창은[15:26:09,15:27:09), 출발 창은[15:26:39,15:27:39)입니다. 특정 초를 골라 적합도를 높이지 않았습니다. 아래 표는 분내 균등 합류 시각 가정으로 계산한 대기열 비교입니다. 분 평균은 실제 관측 순간의 인원과 다른 통계입니다.

| 모형 | 명목 배차 | 분 평균 줄 | 분내 줄 범위 |67명과 기대 절대차 |
|---|---|---:|---:|---:|
{fields}

기대 절대차는 분 안의 각 시각에서 |예측 줄−67|을 적분한 값이며, 분 평균과67명의 차이와는 구분합니다. 기준4분 모형에서는15:23:00 초기 줄66.38명, 다음 출발 전 유입49.34명, 해당 분의 승차0명이 세 비교안에서 같았습니다. 그 사이 경로 전환 이탈은 이전60·1대17.71명,44·1대24.84명,44·피크2대7.43명이었습니다. 예상 공급이 커지면 모형 여행자가 줄에 더 남기 때문에 두 대안의 분 평균 줄이 오히려 커질 수 있습니다. 이는 같은 모형 안의 수지 설명이며 실제 관측 오차의 원인이 입증된 것은 아닙니다. 두 대 공급안이 이 관측을 더 잘 맞혔다고 판단하지 않습니다.

인원 계수 방법과 오차 범위는 보고되지 않았고,67명 정정과44명 정원 정정의 통계적 독립성도 확인되지 않았습니다. 한 사건의 사진 두 장을 두 표본으로 세거나189초를67명 모두의 대기로 확대하지 않습니다.67/44만으로 놓친 버스 수·실제 배차간격을 정하지 않습니다.

현재 전역 모형은 차량 도착·승차·출발을 한 사건으로 근사합니다.189초를 차량 도착 대기와 도착 후 승차 처리로 나눌 자료가 없으며, 탑승 후30초는 차량 전체 정차시간도 아닙니다. 따라서 이 모형이 관측의 세 시각을 각각 재현했다고 주장하지 않습니다. 모형 준비20초를189초에서 임의 차감하거나 중복 가산하지 않았습니다. 새 보고에 맞추어 유입·초기 정문 계수·행동 확률·배차 위상을 다시 맞추지 않았습니다.

## 유지한 경로 변경 규칙과 전체 대기 검사

변경 횟수에는 상한·예산·소진이 없습니다. 두 번째부터 기본 성향이0.3배씩 감소하고 본인의 만차 경험과 긴 대기는 재판단 가능성을 높입니다.0~500m의 기본 도보 고려도는 같고1km 이후 빠르게 감소합니다. 같은 노선의 뒤 정류장으로 걷는 선택도 낮은 가중치로 남아 있습니다. 다른 시내노선·교내 셔틀·직접 도보를 함께 고려합니다. 평균1회는 강제 할당값이 아닙니다.

월~금×두 배차의10개 경우를 전체 가중 흐름으로 다시 계산했습니다.990개 정류장·요일·배차 조합에서 이번 계산의 최대 연속 대기는 {max_wait:.2f}분,20분 초과는 {over:.2f}명 상당·회입니다.20분은 검토 기준이며 강제 이탈이나 대기시간 보장이 아닙니다. 준비 전 취소는 방문에는 남고 준비완료 유입에는 들어가지 않습니다. 약40명은 서울대정문·법대사회대입구에 대한 사용자 기억 참고값이며 실측 상한이 아닙니다.

차량 정원·승하차 수지·적격FIFO·개별 통행 질량·시간 연결을 별도로 검산했습니다. 이는 내부 정합성 검사이며 독립 현장 정확도 검증은 아닙니다. 교외 배경 승객과 실제 전체 학생 수요·출석·개인 목적지·도보 선호의 불확실성은 남아 있습니다. 시내버스50/24는 실제 투입 차종을 확인한 값이 아닌 보존한 참고정원입니다.

## 근거와 자료

- 사용자 최종 정원 정정: 행정관→설입44명. 등록정원을 별도로 확인한 자료는 아닙니다. 종전 정원46명과 대기인원83·69명 보고는 이력에만 보존하고 분석에는 최종44·67명을 사용합니다.
- 사용자 피크 묶음 운행 정보: 반복 개인 경험 및 전달한 공통 증언. 독립 증언자 수·횟수·정확한 시각·반복 간격은 미확인입니다.
- 화요일 현장 한 사건: 외부 줄67명/개인189초/탑승 후30초. 원본 사진과 수정 이력은 비공개 원본에 보존하고 사진에서 인원을 자동 재계수하지 않았습니다.
- 기존 수강·건물·목적지 참고비중·기숙사 참고비율·보행/도로망 및 운행계획을 유지했습니다. 실제 개인별 목적지나 고유 학생 이동을 추적한 자료가 아닙니다.
- 공식 운행 안내는 [서울대학교 학내외 버스 정류장·시간](https://www.snu.ac.kr/about/gwanak/shuttles/shuttle_stops)과 [교내순환 셔틀](https://www.snu.ac.kr/about/gwanak/shuttles/campus_shuttles)을 참고합니다. 학기·계절학기·방학 기간을 구분합니다. 이번 두 시나리오의 정확한 명목 시각을 실제 회차별 실적으로 표시하지 않습니다.
- 서울시 일별 승하차와 월별 시간대 승하차는 집계 단위가 다릅니다. 이번 공급 정정에서 이를 날짜×시간별 학생 도착 수요로 바꾸거나 새로운 학생량으로 더하지 않았습니다.
- [기존 행동 가정과 v9 결과](walk-choice-methodology.html) · [기초 자료·출처](methodology.html) · [이전 v9 지도](./?dataset=walk_choices_v1) · [전체990행CSV](capacity-correction-waits.csv).
'''
    (public/'capacity-correction.md').write_text(md,encoding='utf8')
    template=(public/'walk-choice-methodology.html').read_text(encoding='utf8')
    start=template.index('<details>');end=template.index('</details>',start)+len('</details>')
    template=template[:start]+'<details><summary>정원·공급·관측·한계 전체 설명 펼치기</summary><div class="sources">'+render_md(md)+'</div></details>'+template[end:]
    template=template.replace('walk-choice-methodology.md','capacity-correction.md').replace('walk-choice-waits.csv','capacity-correction-waits.csv').replace('walk-choice-review.js','capacity-correction-review.js')
    template=template.replace('경로 변경 가정·전 정류장 대기검사','정원44·피크2대 가정과 전체 대기검사').replace('혼잡에 따른 경로 변경과 대기 검사','설입44명·피크2대 공급과 대기 검사')
    template=template.replace('<h1>설입44명·피크2대 공급과 대기 검사</h1>','<h1>설입44명·피크2대 공급과 대기 검사</h1><p>행정관→설입 주간44명/차. 가정한15~19시 피크 창의 명목 배차마다 두 대를 개별 운행합니다. 정확한 반복 주기와 피크 경계는 추가 확인 대상입니다. 기존 행동계수는 유지했습니다.</p>')
    template=template.replace('./?dataset=gate_access_v1','./?dataset=walk_choices_v1').replace('이전 v7 지도','이전 v9 지도')
    (public/'capacity-correction.html').write_text(template,encoding='utf8')
    js=(public/'walk-choice-review.js').read_text(encoding='utf8').replace('data/walk_review_v1/report.json','data/capacity_review_v1/report.json')
    (public/'capacity-correction-review.js').write_text(js,encoding='utf8')
    base.save(WORK/'supply_comparison.json',{'units':'minutes, same original weighted cohorts; not observed improvement','rows':comparisons,'field_diagnostic':diagnostic})
    print('Exported capacity_v11, 990 reviewed rows and corrected source documentation; production latest unchanged')

if __name__=='__main__':build()
