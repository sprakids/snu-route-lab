# 월요일 모델 검토 분석 안내

이 폴더는 2026-11-09 월요일 보관자료를 이용한 **검토용 분석**입니다. 적용 모델은 capacity_v7 / 경로 모델 261109173153이며, 수집기·모델·사이트를 수정하지 않았습니다.

먼저 [검토 보고서](월요일_모델_수정_필요성_검토.md)를 읽으시면 됩니다. 모델 변경 우선순위와 판단 근거를 담았습니다.

## 입력과 단위

| 자료 | 뜻 | 해석 한계 |
|---|---|---|
| sources/collector-2026-11-09.json.gz | 11:20~23:10 보관 NDJSON 묶음, 8개 시내·마을 노선 | 사람 수, 탑승 횟수, 셔틀 운행 이력이 아님 |
| sources/route_stops.json / network.json | 노선별 정류장 순번·방향·위치 및 ARS 대응 | 순번은 노선 안에서만 유효 |
| sources/collector-snapshot.private.json | 확보 당시 수집기 상태 | 하루 전체 수집 성공을 증명하지 않음 |
| sources/collector-aggregate.private.json | 저장된 집계 응답 | 주 분석은 원시 관측에서 다시 계산 |
| sources/saved-manual-observations.private.json | 저장된 수기 이동 관측 목록 | 이번 목록은 0건 |
| manifest.json | 입력별 크기·해시·확보시각·출처 | 원문에는 차량 식별 자료가 있어 공개 사이트에 복사하지 않음 |

같은 차량의 같은 제공시각은 한 제공관측으로 묶고, 최초 조회를 신선도 기준으로 사용했습니다. 같은 구간에 머문 연속 관측은 구간 방문으로 묶었습니다. 혼잡 변화는 같은 차량의 인접 구간을 연결한 관측 비교입니다. 같은 등급은 승하차 0명을 뜻하지 않습니다.

## 결과 파일

| 파일 | 용도 |
|---|---|
| focused_headways.csv | 윗공대·서울대학교 참조 지점의 15~19시 차량 간격 비교 |
| focused_travel_times.csv | 동일 차량·방향·구간의 현 모델 시간과 월요일 관측 비교 |
| focused_crowd_grades.csv | 행정관·문화관의 시간대별 버스 내부 혼잡 분포 |
| focused_entry_grades.csv | 교내 진입 또는 교외 승차 전 참조 구간 분포 |
| model_review_decisions.csv | 모델 요소별 유지·수정 후보·보류 판정 |
| diagnostics/ | 운행시간·구간 속도·배차·모델 재차 분석 전체 표 |
| analysis/ | 중복·결측·충돌 제외, 구간 방문·등급 변화·좌표 점검 |
| verification.json | 원문·기존 보호 파일·모델 파일 해시와 집계 정합성 |
| live_model_check.json | 분석 종료 시 두 공개 사이트의 모델 ID 확인 |

## 재현 절차

프로젝트 루트에서 다음 분석을 순서대로 실행합니다. Python 표준 라이브러리만 사용합니다. 원자료를 새로 수집하는 단계는 포함하지 않았습니다.

```text
python shuttle_analysis/monday_model_review_2026-11-09/analysis/analyze_observations.py
python shuttle_analysis/monday_model_review_2026-11-09/analysis/audit_vehicle_positions.py
python shuttle_analysis/monday_model_review_2026-11-09/analysis/build_transport_observations.py
python shuttle_analysis/monday_model_review_2026-11-09/transport_diagnostics.py
python shuttle_analysis/monday_model_review_2026-11-09/finalize_review.py
```

Windows에서는 UTF-8 모드로 실행합니다. 마지막 단계는 현재 공개 모델 정보를 읽기 전용으로 조회하지만, 서울시 원천 API 호출·수집 작업·모델 변경·배포를 하지 않습니다. 관측창 민감도 표는 같은 순번 통과 비교를 45/120/300초로 독립 재계산한 저장 결과이며 기본 주 분석은 45초입니다.

## 불확실성과 보존

관측 통과 간격은 실제 정류장 도착 간격의 근사치입니다. 버스 미포착은 긴 간격을 만들 수 있습니다. 정류장 근방 정차 탐지 간 시간은 정차·승하차를 포함하며 실제 도착시각이 완벽하게 확인된 값은 아닙니다. 관측 경계 범위와 P10~P90은 통계적 신뢰구간이 아닙니다. 분석용 ±15초 판정과 대표간격의 70%/130% 기준도 공식 허용오차가 아닙니다.

자료는 월요일 한 날입니다. 121,655개의 원래 중첩 구간 연결과 31,355개의 엄격 조건을 통과한 모델 비교 연결을 각각 독립된 사람이나 완결 여행 횟수로 해석하지 않습니다. 최소 5회·2개 날짜를 요구하는 기존 검증 조건에서 두 날짜 요건을 만족하는 셀은 0개입니다.

`analysis/revisions/`에는 처음 발견된 제공키 충돌에 대한 중단 기록과, 과거 모델 승격 전 latest 포인터를 불변 파일로 오인해 발생한 검증 실패 기록을 보존했습니다. 포인터는 현재 v7 승격 상태를 따로 확인했으며, 나머지 기존 보호 파일 55개는 원래 해시와 일치합니다.
