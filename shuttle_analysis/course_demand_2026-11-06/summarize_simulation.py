"""Review model outputs and create a Korean report and compact chart payloads."""
from pathlib import Path
from collections import Counter
import json, hashlib, csv, math
import pandas as pd

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'outputs'
VIS=Path(r'C:\Users\김예준\.codex\visualizations\2026\11\03\01a1a1e8-54cf-7243-9ad9-0a31e6f31a06')
REFERENCE='reference_dorm19p49_depart50'
RHO=5772/29613
DAYS='월화수목금'
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def clock(m):return f'{int(m)//60:02d}:{int(m)%60:02d}'
def md_table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
                     ['| '+' | '.join(map(str,r))+' |' for r in rows])

def main():
    df=pd.read_csv(OUT/'stop_inflow_5min_scenarios.csv',dtype={'stop_id':str,'route_id':str})
    canonical_names={'snu-901':'302동','snu-1001':'301동','snu-300':'문화관입구','snu-410':'행정관'}
    for sid,name in canonical_names.items():df.loc[df.stop_id==sid,'stop_name']=name
    # Separate residence from today's destination: half/three-quarters of residents
    # return to dorm, the remainder use the assumed external destination distribution.
    base10=df[df.scenario=='dorm10_depart50'].copy()
    base30=df[df.scenario=='dorm30_depart50'].copy()
    keys=['weekday','stop_id','direction','route_id','bin_minute','boarding_stage']
    pair=base10.merge(base30[keys+['expected_trip_events']],on=keys,suffixes=('','_30'),validate='one_to_one')
    extra=[]
    for q in (.5,.75):
        d=pair[list(df.columns)].copy()
        coefficient=(RHO*q-.1)/.2
        values=pair.expected_trip_events+coefficient*(pair.expected_trip_events_30-pair.expected_trip_events)
        assert values.min()>-1e-5
        d['expected_trip_events']=values.clip(lower=0).round(6)
        d['scenario']=f'residents_return{int(q*100)}'
        extra.append(d)
    df=pd.concat([df[~df.scenario.str.startswith('residents_return')],*extra],ignore_index=True)
    df.to_csv(OUT/'stop_inflow_5min_scenarios.csv',encoding='utf-8-sig',index=False)
    peak=df.groupby(['scenario','weekday','stop_id','stop_name','bin_minute'],as_index=False).expected_trip_events.sum()
    top_by_stop=(peak.sort_values('expected_trip_events',ascending=False)
                .drop_duplicates(['scenario','weekday','stop_id']))
    main_peak=peak[peak.scenario==REFERENCE]
    top_main=top_by_stop[top_by_stop.scenario==REFERENCE]
    top_main.to_csv(OUT/'reference_stop_peaks.csv',index=False,encoding='utf-8-sig')
    sensitivity=[]
    for (scenario,day),rows in top_by_stop.groupby(['scenario','weekday']):
        top=rows.sort_values('expected_trip_events',ascending=False).iloc[0]
        sensitivity.append({'scenario':scenario,'weekday':day,'top_stop_id':top.stop_id,
            'top_stop_name':top.stop_name,'time':clock(top.bin_minute),
            'expected_events_5min':round(top.expected_trip_events,2)})
    pd.DataFrame(sensitivity).to_csv(OUT/'sensitivity_peak_comparison.csv',index=False,encoding='utf-8-sig')
    validation=load(OUT/'simulation_validation.json');quality=load(OUT/'course_quality.json')
    mode=pd.read_csv(OUT/'scenario_summary.csv')
    main_mode=mode[mode.scenario==REFERENCE]
    assert len(main_mode)==5
    assert all(abs(r.generated_trip_events-r.walk-r.city_first-r.shuttle_first-r.unassigned)<.005 for r in main_mode.itertuples())
    assert df.expected_trip_events.ge(0).all()
    assert df.expected_trip_events.map(math.isfinite).all()
    assert not df.duplicated(['scenario',*keys]).any()
    polling=pd.read_csv(OUT/'polling_schedule_proposal.csv')
    calls=polling.groupby('weekday').route_calls.sum().to_dict()
    assert all(n<=950 for n in calls.values())
    assert not polling.duplicated(['weekday','seconds_after_midnight']).any()
    original=Path(quality['source']);archive=Path(quality['source_archive'])
    assert hashlib.sha256(original.read_bytes()).hexdigest()==quality['source_sha256']==hashlib.sha256(archive.read_bytes()).hexdigest()
    candidates=pd.read_csv(OUT/'route_candidates.csv',dtype={'building':str})
    samples=[]
    for building in ['301','302','43','200']:
        for stop in ['120000174','snu-410']:
            subset=candidates[(candidates.building==building)&(candidates.boarding_stops.fillna('').str.split(' / ').str[0]==stop)]
            if len(subset):
                r=subset.sort_values('access_walk_seconds').iloc[0]
                samples.append({'building':building,'stop_id':stop,'walk_m':int(r.access_walk_m),
                                'base_walk_minutes':round(r.access_walk_seconds/60,1)})
    dump(OUT/'walking_examples.json',samples)
    hist=pd.read_csv(OUT/'class_end_histogram.csv')
    hist=hist[hist.scope=='관악 지도대응·공동개설 제외']
    endings=[];dayrows=[]
    for day in DAYS:
        h=hist[hist.weekday==day].sort_values('enrollment_sum',ascending=False).iloc[0]
        endings.append([day,h.end,f'{int(h.enrollment_sum):,}',int(h.ending_course_events)])
        tops=top_main[top_main.weekday==day].sort_values('expected_trip_events',ascending=False).head(4)
        dayrows.extend([day,r.stop_name,r.stop_id,f'{clock(r.bin_minute)}–{clock(r.bin_minute+5)}',f'{r.expected_trip_events:.1f}'] for r in tops.itertuples())
    poll=validation['polling']
    scenerows=[]
    for scenario in [REFERENCE,'dorm10_depart50','dorm30_depart50','snu_dominant','nak_dominant','daehak_dominant','residents_return50','residents_return75']:
        for day in ['월','금']:
            r=next(r for r in sensitivity if r['scenario']==scenario and r['weekday']==day)
            scenerows.append([scenario,day,r['top_stop_name'],r['time'],r['expected_events_5min']])
    total=main_mode.generated_trip_events.sum()
    unknown=main_mode.unassigned.sum()
    review={'checks':'PASS','reference_dorm_share':RHO,'latest_dorm_total':3122+2650,
            'source_original_unchanged':True,'duplicate_scenario_stop_route_stage_bins':0,
            'scenario_count':df.scenario.nunique(),'weekday_count':5,
            'week_input_enrollment_event_sum':int(main_mode.input_enrollment_events.sum()),
            'generated_homeward_trip_event_weight':float(total),'unassigned_event_weight':float(unknown),
            'assigned_fraction':float(1-unknown/total),'planned_daily_api_calls':calls,
            'residence_vs_destination_sensitivity':{'resident_fraction':RHO,'dorm_return_fractions':[.5,.75,1.0]},
            'spatial_coverage':{'buildings':validation['building_count'],
                'unreachable_building_destination_pairs':validation['unreachable_building_destination_pairs']},
            'rounding':'CSV weights rounded to 6 decimals; no people-count precision implied'}
    dump(OUT/'review_checks.json',review)

    report=f'''# 서울대 수업 종료·보행·정류장 유입 시뮬레이션

확인일: 2026-11-06. **오프라인 예비 시뮬레이션을 실제 실행했습니다. 결과는 관측 승객 수나 실제 대기열이 아니라, 강좌 수강인원에 이동 가정을 적용한 통행 사건의 예상 가중치입니다.**

## 입력과 적용 범위

- 원본 강좌검색: 2026학년도 2학기 전체 8,654개 강좌. 수강인원이 모두 0인 7월 공개본과 구분했습니다.
- 설강·양의 수강인원·공식 지도 건물 대응 조건을 적용하고 공동개설·원격 표지·인원 배분이 불명확한 분반을 제외한 4,442개 강좌의 6,274개 종료 사건을 정리했습니다. 이 중 평일·23:10 이전 종료 사건 **{validation['eligible_weekday_ending_events']:,}개**, 수강인원 가중치 합계 **{validation['eligible_weekday_enrollment_event_sum']:,}**를 시뮬레이션했습니다. 같은 학생의 여러 수업이 포함되므로 학생 수로 읽으면 안 됩니다.
- 건물은 개설 학과가 아니라 강의실 동 번호로 판별했습니다. [서울대 공개 지도](https://map.snu.ac.kr/web/main.action)의 237개 건물 좌표 중 해당 강좌가 있는 **{validation['building_count']}개 건물**을 연결했습니다. 좌표는 건물 대표점이며 실제 강의실 출입구·층별 이동은 미확인입니다.
- 시내버스 5511·5513·5516·관악02-1·관악02-2, 행정관↔서울대입구, 행정관↔대학동, 교내 순환·역순환을 사용했습니다. 11:20 이후의 하교 분석이므로 오전 전용 등교셔틀은 분석 운행에서 제외했습니다. 외부 목적지는 서울대입구역·낙성대역·대학동고시촌입구 대표점입니다.

## 생활관 수치: 사용자 최신 선택 반영

학부 **3,122명**, 대학원 **2,650명**, 합계 **5,772명**을 사용합니다. 앞선 6,511명은 기준 시나리오에서 제외했습니다. 분모 29,613명으로 나눈 **{RHO*100:.4f}%**는 **사용자 채택 기준 시나리오**입니다.

이 비율을 현재 관악 수강생의 실측 거주율로 확정하지 않습니다. [관악학생생활관 현황](https://snudorm.snu.ac.kr/기관-소개/현황/)의 5,772명 표에는 기준일과 정원/실거주 정의가 명시돼 있지 않고, 29,613명은 [2025년판 통계연보](https://www.snu.ac.kr/about/downloads?bbsidx=165605&md=v) 203쪽의 2025.4.1. 전교 재학생 수입니다. 관악 수강생과 동일 범위인지 미확인입니다.

3,122/5,772와 2,650/5,772는 생활관 인원의 학부·대학원 구성비입니다. 과정별 전체 재학생 분모가 없어 과정별 거주율로 바꾸지 않았습니다. 기준에서는 모든 강좌 집단에 동일 거주율을 가정하고, 기숙사 목적지 대표점만 강좌 이수과정이 학사이면 919동, 그 밖이면 900동으로 구분했습니다. 이는 목적지 대표점을 정하는 편의 가정이며, 개별 수강생의 실제 학위과정·생활관 동을 확인했다는 뜻이 아닙니다.

기숙사 거주 여부와 오늘의 목적지도 구분합니다. 기준 시나리오는 기숙사생이 곧바로 기숙사로 귀가한다고 가정하며, 추가로 **기숙사생의 50%·75%만 기숙사로 향하고 나머지는 교외로 이동**하는 경우도 계산했습니다. 이때 거주비율 자체는 {RHO*100:.2f}%로 유지됩니다. 기숙사행 학생도 도보·시내버스·교내셔틀을 선택할 수 있습니다.

## 계산 방법과 이유

1. **통행 생성:** 종료 강좌 수강인원 × 바로 거주방향으로 이동하는 비율(25·50·75%, 기준 50%)로 잠재 통행을 만듭니다. 개인 시간표가 없어 오늘의 마지막 수업과 출석을 알 수 없기 때문입니다. 따라서 이 비율은 추정된 사실이 아니라 민감도 가정입니다.
2. **시공간 이동:** 수업 종료 뒤 건물 이탈시간을 삼각분포 1·3·8분, 평지 보행속도를 0.9·1.2·1.5m/s(최소·최빈·최대)로 둡니다. OSM 보행망의 계단은 기본 0.7m/s로 더 느리게 계산합니다. 실제 출입구·경사 측량값은 아닙니다.
3. **보행망 연결:** 건물 대표점에서 연결 가능한 기존 공공 보행망의 주 연결망으로 스냅합니다. 끊어진 작은 지도 조각을 가장 가까운 길로 오인하지 않기 위한 보정입니다. 연결부는 110m를 넘기지 않으며, 도로·보행로 사이에 임의 연결 간선을 만들지 않았습니다. 주 연결망까지 직선 연결부의 통행 가능성은 현장 확인 전입니다.
4. **경로 선택:** 직접 도보·버스/셔틀 직행·1회 환승 후보를 비교합니다. 시간 외에 환승 1회당 2분의 선택 비용과 Gumbel(scale 90초) 취향 차이를 가정합니다. 승차까지 20초 여유를 줍니다. 시내버스는 저장된 노선 자료의 대표 배차간격을 쓰고 위상은 미관측이므로 무작위이며, 실제 당일 배차·GPS를 반영한 결과는 아닙니다. 차내시간은 구간거리와 18km/h·정류장당 15초 가정입니다.
5. **셔틀 출발:** [2026-2 공식 시간표](https://cse.snu.ac.kr/ko/community/notice/25464)의 운행시간·배차간격을 사용합니다. 행정관 야간 출발시각과 302동 역순환 출발시각은 정해진 시각을 기다리도록 했습니다. 주간에 간격만 공개된 셔틀은 간격의 중간값으로 대기시간을 모형화했습니다. 시간표는 계획이며 실제 운행이나 차량 위치가 아닙니다.
6. **정류장 유입:** 출입 지연과 실제 보행망 이동을 더해 첫 승차·환승 정류장 도착을 5분 구간으로 집계합니다. 같은 통행의 환승은 별도 승차 사건으로 기록해, 통행 수와 승차 횟수를 혼동하지 않게 했습니다.
7. **반복과 검증:** 난수시드 {validation['seed']}, {validation['replications']}회 반복, 강좌·목적지당 {validation['weighted_particles_per_cohort_destination']}개의 가중 입자를 사용했습니다. 수강인원이 작은 강좌와 큰 강좌의 입자 수가 같아도 가중치가 달라 전체 인원 가중치는 보존됩니다. 반복은 계산 안정성 확인이며 현장 예측 정확도의 검증이 아닙니다.

보행망 계산 예시는 다음과 같습니다. 건물 이탈시간 1·3·8분은 아래 값에 별도로 더해집니다. 직선 연결부와 계단을 포함한 모형값이며 현장 실측 시간이 아닙니다.

{md_table(['강의동','정류장 ID','보행망 거리(m)','기본 보행시간(분)'],[[x['building'],x['stop_id'],x['walk_m'],x['base_walk_minutes']] for x in samples])}

기존 자료에서 역순환 문화관 정류장이 행정관(snu-410) 좌표와 잘못 연결된 것을 발견해, 이번 분석에서는 학교 지도의 문화관입구(snu-300) 좌표로 바로잡았습니다. 이 수정은 분석용 노선에 적용했으며 운영 앱 파일은 변경하지 않았습니다. 수정 전 실행도 `runs/v2_legacy_culture_anchor`에 보존했습니다.

기숙사 비중은 10·20·30%도 비교했습니다. 실제 교외 방향 비중이 없으므로 기준은 세 방향을 동일하게 두고, 서울대입구·낙성대·대학동을 각각 60%, 다른 두 방향을 20%씩 두는 경우를 비교했습니다. 이 비율들은 설문 결과가 아닙니다. 사당 등 네 목적지 밖으로 가는 통행은 모델 범위 밖입니다.

## 먼저 확인한 수업 종료 집중

{md_table(['요일','최대 종료시각','종료 강좌 수강인원 합계','종료 강좌 사건'],endings)}

종료시각의 인원을 그대로 버스 이용자로 옮기지 않았습니다. 정류장별 피크가 이 시각 이후로 이동하는지 확인하는 입력입니다.

## 기준 시나리오: 정류장별 유입

바로 귀가 50%, 기숙사 기준 {RHO*100:.2f}%, 교외 세 방향 동일 비중일 때입니다. 각 행은 해당 정류장의 하루 중 최대 5분 구간입니다. **‘300’은 실제로 300명이 줄에 서 있다는 뜻이 아닙니다.**

{md_table(['요일','정류장','정류장 ID','피크 5분 구간','예상 통행 사건 가중치'],dayrows)}

정류장 ID는 방향이 다른 맞은편 정류장을 구별하기 위해 남겼습니다. 시내버스·셔틀의 가까운 승차점도 임의로 하나의 대기열로 합치지 않습니다.

## 가정이 바뀔 때

{md_table(['시나리오 ID','요일','최대 정류장','피크 시작','5분 가중치'],scenerows)}

바로 이동 비율은 같은 공간 배정에 선형으로 적용되므로 인원 규모를 바꿉니다. 반면 목적지 비율은 유리한 노선·정류장을 바꿀 수 있습니다. 기준 가정의 절대 인원과 순위를 확정 수요로 사용하면 안 됩니다.

## API 950회 안에서의 집중 갱신 제안

노선별 버스 위치 API를 한 번씩 호출하는 설계에서, 모든 5개 노선 동시 조회는 1회 갱신당 API 5회입니다. 기본은 10분마다 전체 갱신하고, 예상 유입이 큰 5분 구간 6개(합계 30분)에 15초마다 전체 갱신하는 예시를 생성했습니다. 기본·집중 시간이 겹치면 한 번만 요청하도록 중복 제거했습니다. 이 장부는 해당 위치 API 호출만의 예산이며 별도 도착정보·셔틀 제공자의 요청 한도를 대신하지 않습니다.

{md_table(['요일','15초 갱신 구간','계획 API 호출','950회 내 재시도 여유'],[[p['weekday'],' / '.join(p['peak_windows']),p['planned_api_calls'],p['within_950_retry_reserve']] for p in poll])}

위 스케줄은 전체 승차 유입이 큰 구간을 우선하는 **오프라인 제안**입니다. 전 시간대 예측오차·실제 앱 이용량·혼잡도를 함께 최적화한 최종 해는 아닙니다. 실제 적용 시 서버 공용 캐시와 원자적 일일 호출 장부를 두고, 재시도도 950회에 포함해 예산이 소진되면 저장된 마지막 결과를 제공해야 합니다. 이번 분석에서 운영 스케줄러·데이터베이스·배포 설정은 변경하지 않았습니다.

## 정합성 검증과 남은 한계

- 원본 XLS와 보존 사본의 SHA-256 일치, 원본 미변경 확인: `{quality['source_sha256']}`.
- 수업 시각 파싱 오류 0, 강좌-분반 키 중복 0. 연속 강의·실습의 10분 이하 휴식은 같은 종료 사건으로 묶었습니다.
- 기준 시나리오 잠재 통행 가중치 {total:,.1f} = 도보 + 시내버스 우선 + 셔틀 우선 + 배정 불가. 배정 불가 {unknown:,.1f}를 별도 기록했습니다. 0명 수요로 바꾸지 않았습니다.
- 보행망 대응 후 경로 후보 없는 건물-목적지 조합은 {len(validation['unreachable_building_destination_pairs'])}개입니다. 후보가 존재한다는 사실은 현장 통행 가능성 검증을 대신하지 않습니다.
- 반복 계산의 1위 정류장·시각 분포는 `simulation_validation.json`에 보존했습니다. 신뢰구간이나 현실 정확도로 해석하지 않습니다.
- 차량별 수용 인원·기존 탑승자·배차 지연·실제 대기열이 없으므로, 탑승 실패 확률과 혼잡 지속시간을 실측치처럼 계산하지 않았습니다. 현장 관측으로 보정할 우선 대상은 **행정관과 301동 인근 정류장**이며, 기숙사행·낙성대행은 별도 방향으로 기록해야 합니다.
- 다음 보정 변수는 바로 귀가 비율, 거주 여부별 당일 목적지, 실제 출입구·보행속도, 시간대별 차내 여유 좌석입니다. 과거 설문 문항이 있다는 사실을 실제 방향별 응답 비율로 바꾸지 않습니다.

## 재현 및 산출물

Python 환경에서 numpy/pandas 및 `deps`의 xlrd를 사용합니다. `prepare_courses.py` → `simulate_stop_inflow.py` → `summarize_simulation.py` 순서입니다. 분석은 외부 버스 API를 호출하지 않습니다.

- `outputs/course_endings_current.csv`: 강좌·요일·실제 강의동·종료시각·포함 여부.
- `outputs/stop_inflow_5min_scenarios.csv`: 시나리오·요일·정류장·방향·노선·첫 승차/환승별 5분 유입량.
- `outputs/reference_stop_peaks.csv`, `sensitivity_peak_comparison.csv`: 기준·민감도 비교.
- `outputs/route_candidates.csv`, `route_candidate_coverage.csv`: 보행시간·후보 경로·누락 범위.
- `outputs/polling_schedule_proposal.csv`: 노선 5개를 조회할 정확한 초 단위 스케줄.
- `outputs/review_checks.json`, `simulation_validation.json`: 검산·가정·반복 결과.
- `sources/`: 원본 XLS 보존 사본과 학교 공개 지도 원문, 사용자 생활관 선택 수치.
- `runs/v1_disconnected_nearest_snap`: 보행망 조각 문제를 발견했던 첫 실행을 보존한 비교 자료. 최신 결과로 사용하지 않습니다.
'''
    (ROOT/'시뮬레이션_결과와_가정.md').write_text(report,encoding='utf-8')
    selected=[REFERENCE,'dorm10_depart50','dorm20_depart50','dorm30_depart50',
              'snu_dominant','nak_dominant','daehak_dominant','residents_return50','residents_return75']
    labels={REFERENCE:'기준: 기숙사행 19.49%', 'dorm10_depart50':'기숙사행 10%',
        'dorm20_depart50':'기숙사행 20%','dorm30_depart50':'기숙사행 30%',
        'snu_dominant':'교외: 서울대입구 60%', 'nak_dominant':'교외: 낙성대 60%',
        'daehak_dominant':'교외: 대학동 60%', 'residents_return50':'기숙사생 50%만 기숙사 귀가',
        'residents_return75':'기숙사생 75%만 기숙사 귀가'}
    configs=[]
    maximum=float(top_by_stop[top_by_stop.scenario.isin(selected)].expected_trip_events.max())
    xmaximum=math.ceil(maximum/50)*50
    for scenario in selected:
        for day in DAYS:
            tops=top_by_stop[(top_by_stop.scenario==scenario)&(top_by_stop.weekday==day)].sort_values('expected_trip_events',ascending=False).head(8)
            rows=[[f'{r.stop_name} [{r.stop_id}] · {clock(r.bin_minute)}',round(r.expected_trip_events,6)] for r in tops.itertuples()]
            configs.append({'id':f'stop-inflow-{scenario}-{day}','title':f'{day}요일 정류장별 최대 5분 유입',
                'description':f'{labels[scenario]} · 종료인원 중 50%가 바로 이동하는 모형. 승차·환승 사건이며 실제 대기열이 아닙니다.',
                'height':460,'spec':{'type':'horizontalBar','x':'expected_events','y':'stop_and_peak_time',
                    'xLabel':'최대 5분 유입량 · 통행 사건 가중치(모형)', 'yLabel':'정류장 ID · 피크 시작',
                    'xDomain':[0,xmaximum],'showValues':True,'sortOrder':'original',
                    'valueFormat':{'style':'decimal','maximumFractionDigits':1}},
                'columns':['stop_and_peak_time','expected_events'],'rows':rows})
    dump(OUT/'chart_configs.json',configs)
    template=VIS/'course-stop-inflow.html'
    if template.exists():
        text=template.read_text(encoding='utf-8')
        start=text.index('<!-- START_CONFIGS -->');end=text.index('<!-- END_CONFIGS -->')
        blocks='\n'.join('<script type="application/json" data-viz-chart>'+json.dumps(c,ensure_ascii=False).replace('<','\\u003c')+'</script>' for c in configs)
        text=text[:start]+'<!-- START_CONFIGS -->\n'+blocks+'\n'+text[end:]
        template.write_text(text,encoding='utf-8')
    print(json.dumps({'review':review,'top_reference':{d:[r for r in sensitivity if r['scenario']==REFERENCE and r['weekday']==d] for d in DAYS},
                      'walking_examples':samples,'chart_configs':len(configs)},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
