"""Publish verified aggregate replay and human-readable assumptions only."""
from collections import Counter
from pathlib import Path
import csv, gzip, html, json, re, shutil
import weekday_operations as o
import gate_access_calibration as gate


def main():
    verified=o.read(o.WORK/'independent_verification.json')
    assert verified['status']=='PASS' and verified['simulation_runs']==10
    public=o.ROOT/'public';target=public/'data/capacity_v8';target.mkdir(exist_ok=True)
    files=[]
    for name in ['common','charts',*[f'{s}-{d}' for s in ('regular','peak') for d in ('mon','tue','wed','thu','fri')]]:
        for suffix in ('.json','.json.gz'):
            src=o.OUT/(name+suffix);dst=target/src.name
            if dst.exists():assert dst.read_bytes()==src.read_bytes(), 'Preserve differing v8 export first'
            shutil.copy2(src,dst);files.append(dst.relative_to(public).as_posix())
    for suffix in ('.json','.json.gz'):
        dst=public/'data/half_hour_v1'/('capacity_v8'+suffix)
        shutil.copy2(o.OUT/('half_hour'+suffix),dst);files.append(dst.relative_to(public).as_posix())
    common=o.read(o.OUT/'common.json');bundle=o.read(o.WORK/'prepared.json.gz')
    fits=[]
    for scenario in ('regular','peak'):
        data=o.read(o.OUT/f'{scenario}-mon.json')
        before=o.read(public/f'data/capacity_v7/{scenario}-mon.json')
        for old,new in zip(gate.minute_summary(before,common),gate.minute_summary(data,common)):
            fits.append({'scenario':scenario,'id':new['id'],'reported_people_interval':new['people_interval'],
                'v7_minute_mean':old['uniform_minute_mean'],'v8_minute_mean':new['uniform_minute_mean'],
                'v8_temporal_min_max':new['temporal_min_max'],'independent_validation':False})
    with (o.WORK/'headway_transfer_summary.csv').open(encoding='utf-8-sig') as f:
        headways=[r for r in csv.DictReader(f) if r['band']=='15:00-19:00']
    with (o.WORK/'segment_profile_changes.csv').open(encoding='utf-8-sig') as f:profiles=list(csv.DictReader(f))
    source_counts=dict(Counter(r['source'] for r in profiles))
    with (o.WORK/'daily_before_after.csv').open(encoding='utf-8-sig') as f:comparisons=list(csv.DictReader(f))
    summary={'dataset':'capacity_v8','revision':o.REVISION,'applied_weekdays':['월','화','수','목','금'],
        'source_dates':['2026-11-09'],'all_weekdays_are_transfer_estimates':True,
        'independent_actual_wait_accuracy_validated':False,'headway_transfer_window_seconds':[54000,68400],
        'travel_time_coverage_seconds':[40800,83400],'profile_source_counts':source_counts,
        'campus_max_kmh':40,'external_max_kmh':65,'headways':headways,
        'demand_unchanged':True,'destination_shares_unchanged':True,'gate_access_rule_unchanged':True,
        'shuttle_clocks_unchanged':True,'capacity_scenarios_unchanged':True,
        'external_background_people_included':False,'source_vehicle_ids_published':False,
        'simulation_runs':10,'maximum_particle_mass_error':verified['maximum_particle_mass_error'],
        'three_old_queue_cases_are_not_independent_validation':True,'old_queue_case_comparison':fits,
        'daily_fixed_cohort_comparison':comparisons}
    o.save(public/'weekday-operations-summary.json',summary)
    def reference_stop(r):
        return next(s['name'] for s in bundle['prepared']['routes'][r['route_id']]['stops'] if int(s['seq'])==int(r['reference_seq']))
    table='\n'.join(f"| {r['route']} | {reference_stop(r)} | {float(r['official_seconds'])/60:.2f} | {float(r['applied_median_seconds'])/60:.2f} | {r['n']} |" for r in headways)
    daily='\n'.join(f"| {r['weekday']} | {float(r['old_cumulative_wait_min']):.2f} | {float(r['new_cumulative_wait_min']):.2f} | {float(r['old_total_time_completed_min']):.2f} | {float(r['new_total_time_completed_min']):.2f} |" for r in comparisons if r['scope']=='snu' and r['scenario']=='peak')
    fit_labels={'admin_snu_1653':'16:53 행정관 설입 셔틀','culture_1655':'16:55 문화관입구','snu_gate_1703':'17:03 서울대학교21128'}
    fit_table='\n'.join(f"| {fit_labels[r['id']]} | {r['reported_people_interval'][0]}~{r['reported_people_interval'][1]} | {r['v7_minute_mean']:.2f} | {r['v8_minute_mean']:.2f} |" for r in fits if r['scenario']=='peak')
    md=f'''# 평일 운행 보정: 가정·자료·출처

**월요일 한 날의 운행 관측을 월~금에 확장한 추정 모형입니다. 실제 요일별 대기시간·승객 수를 검증한 결과는 아닙니다.** 기본 지도와 30분 그래프는 capacity_v8을 사용합니다. 기존 정문 접근 보정은 유지했습니다.

## 적용 범위

학생의 출발지·목적지·수강 기반 가중 이동량·출발시각·보행 배율·정문 접근 선택 규칙은 v7과 같습니다. 시내버스 8개 노선의 배차 변동과 시간대별 구간 소요시간을 바꿨습니다. 행정관·순환·역순환·대학동 셔틀의 시각과 정원은 기존 값을 유지했습니다. 직접 셔틀 운행 이력이 확보되지 않아 시내버스 시간을 셔틀에 일괄 복사하지 않았습니다.

적용 요일은 월·화·수·목·금입니다. 학기·주말 운영 범위는 경로 사이트의 기존 규칙을 따릅니다. 주말 실측에 적용하거나 새 주말 운행계획을 만든 것이 아닙니다. 다른 요일에도 사용할 수 있는 공통 운행 규칙을 요청에 따라 확장했으며, 화~금의 실제 교통상황이 월요일과 같다고 확인한 것은 아닙니다.

## 배차: 15~19시 분포를 반영

같은 노선·차량의 정류장 순번이 바뀌는 관측 사이에서 통과시각을 추정했습니다. 45초 이내 관측창·3개 이하 순번 점프·서로 겹치지 않는 연속 차량의 간격을 사용합니다. 참조 지점은 노선별로 고정했습니다. 분포를 사용할 최소 간격 수는 5개이며, 진단용으로 1분 미만 또는 대표간격 3배/30분 중 작은 값보다 큰 간격을 제외했습니다. 공식적인 운행 오차 기준은 아닙니다.

| 노선 | 참조 정류장 | 공개 대표 간격(분) | 사용 분포 중앙값(분) | 관측 간격 수 |
|---|---:|---:|---:|---:|
{table}

이 수치는 실제 운영사의 모든 차량 출발시각표가 아닙니다. 참조 지점의 간격 분포를 이용해 새로운 운행 시나리오를 만들었습니다. 노선·요일별 고정된 배차 순서를 사용해 같은 조건을 다시 열면 같은 결과를 재현합니다. 관측 순서의 간격 목록을 순환 이동해 사용하며 실제 차량 식별자는 공개하지 않았습니다.

15~19시 밖에는 공개 대표 배차를 유지했습니다. 그 시간의 2분 간격 조회는 짧은 구간 통과를 놓쳐 운행간격이 실제보다 길게 보일 수 있기 때문입니다. 참조 지점 도착이 피크에 해당하는 차량의 간격을 바꾸므로 기점 출발시각의 변경 구간은 노선별로 달라질 수 있습니다. 공개 첫차·막차 기점 시각과 부분 노선의 기점→모형 첫 정류장 추정시간은 유지했습니다.

## 소요시간: 구간에 진입한 시각으로 선택

각 인접 정류장 구간은 진입 시각의 시간대별 총소요시간을 사용합니다. 한 차량의 전체 구간에 출발 시각의 단일 속도를 적용하지 않습니다. 이 시각표와 구간시간 계약을 지도와 경로 계산에서 함께 사용합니다.

1. 같은 차량이 인접 정류장 60m 안에서 정차 표지를 처음 보인 시각을 연결했습니다. 양 끝의 직전 관측 간격이 45초 이내이고, 유효 사례 5개 이상이면 해당 시간대의 중앙값을 총소요시간으로 사용했습니다. 이는 GPS·탐지 지연이 있는 근사치이며, 구간 주행과 정차를 따로 실측한 결과가 아닙니다.
2. 이 조건이 부족하면 시간대별 제공 구간속도 지표가 3개 이상인 경우 중앙값을 도로 길이에 적용했습니다. 제공 구간속도는 개별 버스의 순간속도가 아닙니다.
3. 자료가 부족하거나 관측 범위인 11:20~23:10 밖이면 보존된 v7 구간시간을 유지했습니다.

총소요시간은 기존의 정차를 포함하는 운동학적 최소시간보다 짧아지지 않게 했습니다. 교내 최고40km/h·교외 최고65km/h 상한을 유지했습니다. 총시간에 별도 정차시간을 다시 더하지 않습니다. 기존의 도착 정차 가정과 실제 정차시간을 구분하며 실제 승하차 지연을 분리해 측정했다고 주장하지 않습니다.

## 무엇이 달라졌나

아래는 피크 셔틀 배차 시나리오에서 **서울대입구 목적지의 같은 수업 종료 기준집단**을 비교한 모형 결과입니다. 경로를 바꾼 흐름도 누적 대기에 포함합니다. 숫자의 단위는 가중 이동 사건이며 고유 학생 수가 아닙니다. ‘총시간’은 수업 종료부터 모형의 서울대입구 목적지 도착까지이고 완료 집단 기준입니다. 실제 대기시간 개선이나 예측 정확도 향상을 입증하는 표는 아닙니다.

| 요일 | v7 누적 대기(분) | v8 누적 대기(분) | v7 총시간(분) | v8 총시간(분) |
|---|---:|---:|---:|---:|
{daily}

정류장별 그래프의 평균은 해당 정류장에서 탑승한 흐름 기준입니다. 운행을 바꾸면 다른 경로로 이동하는 흐름도 달라지므로 평균 대상이 바뀔 수 있습니다. 지도에는 정원 초과로 남는 흐름과 경로 변경을 다시 계산했고, 30분 집계도 새 계산에서 생성했습니다. 정류장 표식을 누르는 대기량 확인, 그래프 구간 시작시각 이동, 요일·시각 조회, 현재 한국 시각 시작·1초/초 재생은 유지했습니다.

## 기존 대기열 3건의 위치

이전 정문 접근 보정에 사용한 세 관측은 초를 특정하지 않고 해당 분 안의 임의 시각으로 비교합니다. 아래는 피크 시나리오의 분내 시간가중 평균이며 단위는 가중 대기량 상당입니다. 새 운행을 넣어 값이 바뀔 수 있지만 이 세 건을 맞추기 위해 수요를 다시 튜닝하지 않았습니다.

| 기존 관측 | 보고 인원 구간 | v7 분 평균 | v8 분 평균 |
|---|---:|---:|---:|
{fit_table}

이 세 건은 이미 사용한 보정자료이므로 독립 검증으로 재사용하지 않았습니다. 문화관은 문화관입구21297로 대응한 해석이며 정확한 초·노선별 의도는 미확인입니다. 서울대학교는 서울대입구 방향21128입니다.

## 교외 배경 승객과 혼잡등급

월요일 15~19시 교내 진입 직전의 5개 참조 구간은 유효 방문112회 중 보통(4)8회, 혼잡 이상(5·6)0회였습니다. ‘진입 버스 대부분이 만차’라는 결론은 지지되지 않습니다. 동시에 이미 승객이 있는 차량을 항상 빈 차로 간주할 근거도 없습니다.

교외 배경 재차인원·교내 하차는 여전히 보완 대상입니다. 이번에는 등급→명 환산의 실측 근거가 없어 임의 인원을 넣거나 정원을 일괄 줄이지 않았습니다. 따라서 화면의 재차량은 기존 수강 기반 가중 수요의 결과이며 실제 차량 여석이 아닙니다. 여유등급도 빈 차를 의미하지 않습니다. 마을버스 2개 노선의 혼잡등급은 이번 구간 방문4,112개 모두 정보 없음이며 빈 차로 처리하지 않았습니다. 만차 표지가 제공된115개 관측은 혼잡코드0과 함께 나타나 등급 결측과 만차 표지는 별도로 해석했습니다.

정원은 셔틀60명, 역순환25명, 시내50명·마을24명 참고 시나리오를 유지했습니다. 실제 투입 차종·차량별 등록 정원이 확인된 것은 아닙니다. 실제 차량 승하차·재차인원·줄·탑승 실패·이동시간을 함께 측정해야 다음 인원 보정이 가능합니다.

## 수집 자료와 검증

2026-11-09 월요일11:20~23:10 보관 자료입니다. 원시94,212행에서 제공키 중복16,278행을 제거하고 오래된2개와 제공 순번 충돌1개를 제외해77,931개의 제공관측을 분석했습니다. 승객 수나 독립적인 여행 횟수가 아닙니다. 수집된 위치·순번·정차 표지·등급·구간속도와, 보존된 공식 노선·도로 형상·가중 수요를 사용했습니다. 수집 간격은15~19시 중앙값16초, 나머지120초였습니다.

월~금×두 셔틀 배차, 총10개 계산의 수요 보존·승하차·정원·승차 순서·새 차량 시각·운동학적 속도 상한·대기열·30분 집계를 검산했습니다. 기존v3~v7와 원본 입력은 보존했습니다. 이 검산은 계산의 정합성 확인이며 실제 예측 정확도 검증이 아닙니다.

## 출처와 더 보기

- 기존 수집기의 서울시 공개 버스정보 보관본: [버스위치정보조회 서비스](https://www.data.go.kr/data/15000332/openapi.do), [노선정보조회 서비스](https://www.data.go.kr/data/15000193/openapi.do), [서울시 공식 모바일 버스정보](https://m.bus.go.kr/mBus/index.bms).
- 수업 종료·수강 기반 이동량, 목적지·보행·정원 가정은 [기존 가정·자료·출처](methodology.html)에 설명했습니다. 실제 개별 학생의 목적지를 조사한 자료로 해석하지 않습니다.
- [기존 정문 접근 보정의 근거](gate-access-methodology.html), [새 운행 보정의 집계 결과](weekday-operations-summary.json).
- [현재 지도](./), [이전v7 비교](./?dataset=gate_access_v1), [기존v5 비교](./?dataset=baseline_v5). 원시 차량 식별자료·세부 대기 입자 감사자료는 공개하지 않았습니다.
'''
    (public/'weekday-operations-methodology.md').write_text(md,encoding='utf-8')
    (o.WORK/'README.md').write_text(md,encoding='utf-8')
    def inline(t):
        t=html.escape(t);t=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',t)
        return re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<a href="\2">\1</a>',t)
    chunks=[];table=[]
    def flush():
        if not table:return
        h,*rs=table
        chunks.append('<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+inline(x)+'</th>' for x in h)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+inline(x)+'</td>' for x in r)+'</tr>' for r in rs)+'</tbody></table></div>');table.clear()
    for line in md.splitlines():
        if line.startswith('|'):
            if not re.fullmatch(r'[| :\-]+',line):table.append([x.strip() for x in line.strip('|').split('|')])
            continue
        flush()
        if line.startswith('# '):chunks.append('<h1>'+inline(line[2:])+'</h1>')
        elif line.startswith('## '):chunks.append('<h2>'+inline(line[3:])+'</h2>')
        elif line.strip():chunks.append('<p>'+inline(line)+'</p>')
    flush()
    page='<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>평일 운행 보정 · 가정과 출처</title><link rel="stylesheet" href="methodology.css"><link rel="stylesheet" href="campus-theme.css"><script defer src="campus-theme.js"></script><body><header class="doc-header"><a class="doc-brand" href="./">하교길 실험실</a><nav><a href="./">현재 지도</a><a href="weekday-operations-methodology.md">MD 원문</a></nav></header><main class="doc-layout" style="display:block;max-width:1000px"><article>'+''.join(chunks)+'</article></main></body></html>'
    (public/'weekday-operations-methodology.html').write_text(page,encoding='utf-8')
    o.save(o.WORK/'export_verification.json',{'status':'PASS','files':files,'aggregate_only':True,'source_vehicle_ids_published':False})
    print('EXPORTED capacity_v8',len(files),flush=True)


if __name__=='__main__':main()
