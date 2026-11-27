# 병목·혼잡 근거 연구 산출물

기준: 2026-11-08, v5 `campus_stop_corridors_20261108` 동결 모형. 주 보고서는 **요일별_승차지_병목과_혼잡도_근거조사.md**입니다.

이 폴더는 조사·집계 산출물입니다. 원본 v5 시뮬레이션, 경로 앱, 수집기 정책, 운영 배포를 수정하지 않았습니다. 새로운 보행 4.8km/h 집단 시뮬레이션도 실행하지 않았습니다.

## 재현

프로젝트의 기존 보존 입력·감사 파일이 있는 환경에서 Python 3.12, numpy를 사용합니다. 그림·보고서 생성에는 matplotlib가 추가로 필요합니다. 작성 환경은 numpy 2.5.4, matplotlib 3.11.2, Windows Malgun Gothic입니다. 그림용 패키지는 시스템 Python을 변경하지 않고 작업용 임시 의존성 폴더에 설치했습니다.

```powershell
python analyze_baseline.py
python build_study.py
```

`analyze_baseline.py`는 동결된 10개 실행의 원장을 읽어 새 집계만 만듭니다. 원본 모형을 재실행하지 않습니다. `build_study.py`는 보고서·요약·도표를 생성하고 원본 해시 불변과 분모를 확인합니다. 명령은 이 연구 폴더에서 실행할 수 있습니다.

## 저장된 실측 기록

`read_saved_observations.py`는 Windows DPAPI로 보호된 기존 소유자 자격증명을 메모리에서만 읽어 이미 보존된 두 날짜의 `/export`를 내려받습니다. 원시 파일이 이미 있으면 재사용합니다. 새 서울시 버스 API나 수집기를 실행하지 않습니다. 이 단계는 소유자 분석 환경에서만 필요하며 공유받은 팀원의 필수 실행 단계가 아닙니다.

**공유하지 않을 파일**: `sources/collector-*.json.gz`, `sources/deduplicated_passages.private.json`. 원시 차량 식별자와 위치/시각 기록을 포함합니다. 외부 사이트나 공개 저장소에 올리지 않습니다. 차량 식별자를 제거한 `observed_grade_cells.json`, `observed_grade_summary.json`, `bottleneck_summary.json`을 공유용 집계로 사용합니다.

이번에 읽은 실측은 11월 7일 토요일 저녁·8일 일요일 낮의 일부 기록입니다. 이것이 전체 저장소의 모든 날짜를 조회했다는 뜻은 아니며, 평일 혼잡도를 검증한 표본이 아닙니다. 반복 조회를 제거한 차량·추정 운행·구간 최초 등급 단위입니다. 관악02의 등급0은 정보 없음입니다.

## 해석·연결 계약

- `queue_cells`: `scenario/weekday/node/start_seconds` 키. 시계 구간 대기 부담과 도착 코호트 지표가 함께 있으나 서로 다른 분모입니다.
- `physical_stop_cells`: 같은 교통수단·정류장 ID의 대기 인·분 합산. 서로 다른 줄의 최대값을 합산한 최대줄이 아닙니다.
- `modeled_occupancy_cells`: 학생 유래 모형 차내 점유. 실제 전체 차내 승객이나 서울시 혼잡 등급과 다릅니다.
- `historical_context_comparison`: 과거 평일 시간당 구간 재차합과 모형 맥락 비교. 일치 날짜의 예측 성능이나 차량 한 대의 점유율 검증이 아닙니다.
- `bottleneck_summary`: 우선순위·개선안·선정 사례의 소규모 집계. `weekday_top_*`는 peak 시나리오, `regular_weekday_top_physical_stops`는 regular입니다.
- v5 대기열을 새 보행 조건으로 단순 이동시켜 새 전체 실행으로 제시하지 않습니다. 보행 변경은 유입·만차·경로 변경에 피드백을 만듭니다.
- 공지의 역순환 증차와 첨부 PDF의 3대·20분 계획은 실제 배차명세로 확인해야 합니다. 특정 네 시각에 별도 차량이 추가 출발한다고 임의로 중복 편성하지 않습니다.

## 검산

`verification.json`: 10개 실행의 구간별 대기 적분이 원시 대기 노출과 일치합니다. `study_verification.json`: 원본 21개 파일의 해시 불변, 실제 등급 분모·합계 검산, 비공개 원시 파일 목록을 기록했습니다. `history_alias_check.json`: TAIMS 반환 키의 다른 철자까지 확인해 평균·최대·횟수 값이 비어 있음을 검증했습니다.
