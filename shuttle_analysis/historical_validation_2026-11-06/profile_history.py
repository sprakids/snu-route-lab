"""Profile real monthly boardings and make a qualified spatial diagnostic.

No accuracy score: observed monthly card boardings and simulated weekday stop
arrivals differ in population, calendar and event timing.
"""
from pathlib import Path
import json, re, hashlib
import pandas as pd

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'outputs';OUT.mkdir(exist_ok=True)
SOURCE=ROOT/'sources/boardings_hourly_202610.csv'
df=pd.read_csv(SOURCE,encoding='cp949',dtype=str)
network=json.loads((ROOT.parent/'app/data/network.json').read_text(encoding='utf-8'))
meta=[];id_to_number={}
for r in network['routes']:
    id_to_number[r['id']]=r['name']
    for s in r['stops']:
        meta.append({'노선번호':r['name'],'표준버스정류장ID':s['id'],'stop_sequence':int(s['seq']),
                     'route_id':r['id'],'lat':s['lat'],'lon':s['lon'],'direction':s.get('direction','')})
meta=pd.DataFrame(meta)
selected=df[df['노선번호'].isin(id_to_number.values())].copy()
selected['stop_sequence']=selected['역명'].str.extract(r'\((\d+)\)$')[0].astype(int)
numeric=[c for c in selected.columns if re.search(r'시[승하]차총승객수$',c)]
assert len(numeric)==48
for c in numeric:
    selected[c]=pd.to_numeric(selected[c],errors='raise')
    assert selected[c].notna().all()
    assert selected[c].ge(0).all()
assert set(selected['사용년월'])=={'202610'}
source_keys=['사용년월','노선번호','표준버스정류장ID','역명','교통수단타입코드']
assert not selected.duplicated(source_keys).any()
joined=selected.merge(meta,on=['노선번호','표준버스정류장ID','stop_sequence'],
                       how='left',validate='many_to_one',indicator=True)
assert joined['_merge'].eq('both').all()
joined.to_csv(OUT/'five_routes_historical_202610.csv',encoding='utf-8-sig',index=False)
collision_keys=['노선번호','표준버스정류장ID','stop_sequence']
aliases=joined[joined.duplicated(collision_keys,keep=False)][collision_keys+['역명']].to_dict('records')
regions={'lat_min':37.444,'lat_max':37.468,'lon_min':126.944,'lon_max':126.962,
         'meaning':'Provisional rectangular campus-and-nearby region; not an official campus boundary'}
regional=joined[joined.lat.between(regions['lat_min'],regions['lat_max'])&
                joined.lon.between(regions['lon_min'],regions['lon_max'])].copy()
regional['stop_name']=regional['역명'].str.replace(r'\(\d+\)$','',regex=True)
hourly=[]
for r in regional.to_dict('records'):
    for hour in range(24):
        prefix='00' if hour==0 else str(hour)
        hourly.append({'month':r['사용년월'],'route_id':r['route_id'],'route_number':r['노선번호'],
            'stop_id':r['표준버스정류장ID'],'stop_name':r['stop_name'],
            'ars_id':r['버스정류장ARS번호'],'stop_sequence':r['stop_sequence'],'direction':r['direction'],
            'hour':hour,'boardings_month':int(r[f'{prefix}시승차총승객수']),
            'alightings_month':int(r[f'{prefix}시하차총승객수'])})
hourly=pd.DataFrame(hourly)
hourly.to_csv(OUT/'campus_region_hourly_202610.csv',index=False,encoding='utf-8-sig')
window=hourly[hourly.hour.between(12,22)]
observed=window.groupby(['stop_id','stop_name','ars_id'],as_index=False).boardings_month.sum()
observed=observed.sort_values('boardings_month',ascending=False)
observed['observed_rank']=range(1,len(observed)+1)
observed['observed_boarding_share']=observed.boardings_month/observed.boardings_month.sum()

sim=pd.read_csv(ROOT.parent/'course_demand_2026-11-06/outputs/stop_inflow_5min_scenarios.csv',
                dtype={'stop_id':str,'route_id':str})
sim=sim[(sim.scenario=='reference_dorm19p49_depart50')&sim.route_id.isin(id_to_number)&
        sim.bin_minute.between(12*60,23*60-1)&sim.stop_id.isin(observed.stop_id)].copy()
sim['hour']=sim.bin_minute//60
predicted=sim.groupby('stop_id',as_index=False).expected_trip_events.sum()
predicted['modeled_weekday_arrival_share']=predicted.expected_trip_events/predicted.expected_trip_events.sum()
predicted['modeled_rank']=predicted.expected_trip_events.rank(method='min',ascending=False).astype(int)
diagnostic=observed.merge(predicted,on='stop_id',how='left',validate='one_to_one')
diagnostic[['expected_trip_events','modeled_weekday_arrival_share']]=diagnostic[['expected_trip_events','modeled_weekday_arrival_share']].fillna(0)
diagnostic.to_csv(OUT/'spatial_proxy_diagnostic_not_accuracy.csv',index=False,encoding='utf-8-sig')
example=hourly[hourly.stop_id=='120000174'].groupby('hour',as_index=False).boardings_month.sum()
example=example[example.hour.between(12,22)]
predicted_example=sim[sim.stop_id=='120000174'].groupby('hour',as_index=False).expected_trip_events.sum()
example=example.merge(predicted_example,on='hour',how='left')
example['modeled_mean_weekday_arrivals']=example.expected_trip_events/5
example.to_csv(OUT/'301_hourly_proxy_diagnostic.csv',index=False,encoding='utf-8-sig')
peak_observed=example.sort_values('boardings_month',ascending=False).iloc[0]
peak_model=example.sort_values('expected_trip_events',ascending=False).iloc[0]
result={'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'source_rows':len(df),
        'source_months':df['사용년월'].unique().tolist(),'source_registered_dates':df['등록일자'].unique().tolist(),
        'source_encoding':'cp949','source_field_count':len(df.columns),
        'selected_hourly_value_missing_count':int(selected[numeric].isna().sum().sum()),
        'selected_route_row_counts':selected.groupby('노선번호').size().to_dict(),
        'historical_rows_matched_to_current_route_occurrence':len(joined),
        'historical_join_missing':0,'station_name_alias_rows':aliases,
        'region':regions,'regional_route_stop_rows':len(regional),'regional_physical_stops':len(observed),
        'comparison_hour_window':'12:00 inclusive to 23:00 exclusive, KST',
        'hour_11_and_23_excluded_reason':'Simulation only covers 11:20 through 23:10; those two hourly bins are incomplete.',
        '301_observed_max_hour':int(peak_observed.hour),'301_observed_month_boardings_at_max_hour':int(peak_observed.boardings_month),
        '301_model_max_hour':int(peak_model.hour),
        'accuracy_metrics_computed':False,'actual_onboard_load_records_obtained':False,
        'historical_api_status':'Official T-data 1025 schema verified; private-key live query not performed.',
        'caveats':['Monthly aggregate mixes weekdays, weekends and holidays.',
                   'Observed card boardings include non-students and non-class trips.',
                   'The simulation currently emits stop arrival events, not validated vehicle boardings or onboard load.',
                   'Do not compare monthly counts with per-weekday model weights as an absolute error.',
                   'Station-name aliases outside study region are retained; do not deduplicate by name or drop rows.',
                   'T-data API sample fields include nulls; null means unknown, never an empty vehicle.']}
(OUT/'historical_data_quality.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['| 정류장 | ARS | 10월 12–23시 승차 합계 | 시뮬레이션 유입 비중 순위 |',
       '| --- | --- | ---: | ---: |']
for r in diagnostic.head(8).itertuples():
    lines.append(f'| {r.stop_name} | {r.ars_id} | {r.boardings_month:,} | {int(r.modeled_rank) if pd.notna(r.modeled_rank) else "배정 없음"} |')
report='''# 과거 버스 자료 접근 및 시뮬레이션 대조

확인일: 2026-11-06 KST. **서울시 공개 승하차 파일은 실제 확보했으며, 과거 구간 재차인원 API는 공식 명세를 확인했습니다. 재차인원 원자료를 우리 인증키로 조회한 단계까지 완료한 것은 아닙니다.**

## 1. 필요한 과거 API

[서울교통빅데이터: 일자별-시간대별-버스노선별-구간별-승객수](https://t-data.seoul.go.kr/dataprovide/trafficdataviewopenapi.do?data_id=1025)

- 요청: T-data에서 발급한 `apikey`, `stdrDe`(YYYYMMDD), `startRow`, `rowCnt`.
- 공식 표시 엔드포인트: `http://t-data.seoul.go.kr/apig/apiman-gateway/tapi/TaimsTpssA18RouteSection/1.0`.
- 출력: 노선 ID, 출발/도착 정류장 ID, 정류장 순서, 시간별 평균·최대 재차인원, 운행횟수, 재차인원합, 용량초과 운행횟수·거리.
- 업데이트 주기는 월 1회지만 요청 기준은 날짜입니다. 따라서 요일별 묶음 분석을 설계할 수 있습니다. 실제 제공 날짜 범위·서울대 5개 노선별 결측률은 인증된 응답으로 확인해야 합니다. 수정일이나 명세의 샘플 연도를 데이터 수록 범위로 해석하지 않습니다.
- 실시간 위치조회 API의 과거 모드를 사용하는 구조가 아닙니다. 별도의 과거 통계 서비스이며 T-data 키가 요구됩니다. 기존 공공데이터포털 키의 호환성을 가정하지 않습니다.
- 공식 샘플에는 평균·최대 재차인원 및 운행횟수가 null인 항목도 있습니다. null을 0으로 바꾸거나 `재차인원합/운행횟수`를 분모 확인 없이 계산하면 안 됩니다. 원 응답은 camelCase, 명세 일부는 snake_case로 표시돼 있어 실제 응답 스키마도 확인해야 합니다.

보조 자료인 [정류장 운행 통계](https://t-data.seoul.go.kr/dataprovide/trafficdataviewopenapi.do?data_id=1083)는 날짜·노선·경유순번·정류장별 승차/하차·재차·여행시간 등을 제시합니다. 출력에 시간대 열이 명시돼 있지 않아 이를 시간대별 재차 자료의 대체로 단정하지 않습니다.

## 2. 이번에 실제 확보한 자료

[서울 열린데이터광장: 버스노선별 정류장별 시간대별 승하차 인원](https://data.seoul.go.kr/dataList/OA-12913/A/1/datasetView.do)의 공식 파일 목록에서 2026년 10월 CSV를 내려받았습니다. API 키를 사용하지 않은 공개 파일 다운로드입니다. 현재 실시간 위치 API 950회 예산을 소비하지 않았습니다.

원본 42,782행·57열 중 대상 5개 노선의 265개 기록을 추출했습니다. 5511 73개, 5513 44개, 5516 75개, 관악02-1 39개, 관악02-2 34개입니다. 현재 노선의 정류장 ID와 정류장 순번으로 265개 모두 연결했습니다. 순환 노선은 같은 정류장을 여러 번 지날 수 있어 이름이나 정류장 ID만으로 합치지 않았습니다.

5516의 동일 정류장·순번에 이름이 다른 2개 원본 행이 있어 별도 표시했습니다. 해당 위치는 아래 교내·인근 분석 영역 밖입니다. 원본 행을 임의 삭제하지 않았습니다. `사용년월=202610`, `등록일자=20261103`, 인코딩 CP949, 48개 시간별 승하차 수치의 음수·숫자 변환 오류는 없었습니다.

## 3. 예비 대조: 교내·인근 정류장

공식 캠퍼스 경계 폴리곤을 확보한 상태가 아니므로 위도 37.444–37.468, 경도 126.944–126.962의 명시적인 직사각형 범위로 한정했습니다. 노선 전체에서 노량진역 등 교외 정류장이 상위에 올라오는 것을 피하기 위한 임시 분석 범위입니다. 시내버스 5개 노선만 비교하며 셔틀은 포함하지 않습니다. 시간은 시뮬레이션과 공통으로 완전하게 존재하는 12:00–23:00입니다.

'''+'\n'.join(lines)+f'''

**이 표의 좌측은 월 전체 실제 카드 승차 건수, 우측은 전형적 평일 모형의 정류장 도착 사건 분포 순위입니다. 달력·대상·사건시각이 달라 정확도 평가표가 아닌 진단표입니다.**

301동 인근 정류장(21276)의 실제 승차는 이 시간 범위에서 **{int(peak_observed.hour):02d}:00–{int(peak_observed.hour)+1:02d}:00에 월 합계 {int(peak_observed.boardings_month):,}건**으로 가장 많았습니다. 시뮬레이션을 월~금 합쳐 시간 단위로 집계한 최대 구간은 {int(peak_model.hour):02d}:00–{int(peak_model.hour)+1:02d}:00입니다. 차이는 수업 종료 인원에 시간대에 관계없이 동일한 즉시 귀가율을 준 가정, 보행/대기, 배차·탑승 제약, 실제 이용자 범위 등을 점검할 단서입니다. 원인을 이 자료만으로 하나로 확정하지 않습니다.

## 4. 실제 검증 설계

1. **시공간을 맞춥니다.** 2026-2학기 중 자료가 제공되는 날짜를 선택하고, 요일·공휴일·학사일정 조건을 명시합니다. 노선 ID + 정류장 순번 + 출발/도착 정류장 ID로 방향과 반복 경유를 구분합니다. 날짜별 운행 노선 변경도 확인합니다.
2. **동일한 값을 비교합니다.** 승차 실측은 시뮬레이션의 실제 승차 사건과, 구간 재차 실측은 차량별 재차인원 모형과 비교해야 합니다. 현재 모델의 정류장 유입량을 그대로 차내 인원과 비교하지 않습니다. 실측은 학생 외 이용자와 수업 외 이동도 포함하므로, 수업 직후 학생 이동만 생성하는 모형에 배경 수요를 추가하거나 일치하는 학생 표본을 확보해야 절대 인원 오차를 평가할 수 있습니다. 구간 재차 모형에는 기존 탑승자와 승차·하차, 운행횟수와 잔여 용량이 필요합니다.
3. **시간 해상도를 맞춥니다.** 기존 5분 모델 결과를 실측의 1시간 단위로 합칩니다. 시간별 자료를 12개로 나눠 5분 실측처럼 만들지 않습니다. 이 자료만으로 15초/5분 피크나 정확한 혼잡 지속 분수를 검증할 수 없습니다.
4. **규모와 패턴을 나눠 봅니다.** 동일 정의가 확보되면 정류장·노선·요일·시간별 절대오차(MAE), WAPE(합계 실측이 양수인 경우), 공간 순위 상관과 상위 집중 정류장 일치율, 피크 시간 오차를 계산합니다. 현재 서로 다른 집계끼리 그럴듯한 정확도 백분율을 만들지 않았습니다.
5. **보정과 검증 날짜를 분리합니다.** 일부 날짜로 즉시 귀가율·목적지 비율·실제 배차/대기 가정을 보정하고, 사용하지 않은 날짜로 재평가합니다. 같은 기록으로 계수를 조정한 뒤 그 기록에 잘 맞는 것을 검증 성공으로 부르지 않습니다.
6. **셔틀은 별도 관측으로 검증합니다.** 서울시 유료 버스 카드 데이터만으로 무료 교내셔틀 대기열이나 승차 인원을 실측했다고 볼 수 없습니다. 행정관·302동 등에서 시간대별 줄 길이·승차·출발·탑승 실패를 별도 관측하고 시내버스 혼잡과의 관계를 추정합니다.

## 결론

과거 데이터 접근 경로는 확인했고, 5개 노선의 2026년 10월 승하차 원자료는 확보했습니다. 원하는 ‘어느 정류장 이후 차내 혼잡이 높고 얼마나 이어지는가’에는 날짜·시간대·구간별 재차 API가 핵심입니다. 다음 실데이터 단계는 해당 T-data 활용 권한으로 응답·수록 기간·결측을 확인하는 것입니다. 현재 모델 정확도가 검증됐다고 보고하지 않습니다.

산출물은 `outputs/five_routes_historical_202610.csv`, `campus_region_hourly_202610.csv`, `spatial_proxy_diagnostic_not_accuracy.csv`, `301_hourly_proxy_diagnostic.csv`, `historical_data_quality.json`입니다. 다운로드 출처·파일 해시는 `sources/download_receipt.json`에 보존했습니다.
'''
(ROOT/'과거자료_접근과_실측검증.md').write_text(report,encoding='utf-8')
print(json.dumps({'profile':result,'top_observed':diagnostic.head(5).to_dict('records')},ensure_ascii=False,indent=2))
