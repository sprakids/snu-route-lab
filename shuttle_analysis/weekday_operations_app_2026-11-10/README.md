# 평일 운행 보정과 경로 앱의 연결 — 운영 반영 완료

사용자가 실험실 에이전트에 지시한 월~금 적용 작업의 경로 앱 담당 산출물이다. 실험실은 `capacity_v8` 시뮬레이션·검산·발행을 맡고, 이 작업은 앱의 데이터 읽기·대기/이동 계산 연결을 맡았다. 앱은 0.22.1로 운영 배포했고, 실험실 담당자가 승격한 모델 `261110002926`과 동기화를 확인했다. 실험실 latest 포인터는 앱 담당이 변경하지 않았다.

최종 앱 배포: `dpl_Cn7ezPkPqBjGwv6U8ZbyBdqt77Bv` / https://snu-route-lab.vercel.app. 모델 SHA-256은 `6bada3eec9fa0c89386e3cbac2e3e7e90adfa2ce10f0c969c54cafd43c53fe8d`이다. 마지막 실제 관측 요일 우선순위 보완은 `weekday-priority-note.md`, 최종 공개 검증은 `deployment/final-receipt.json`에 있다.

## 변경 이유와 계산 순서

기존 최신 모델 동기화는 FIFO 대기곡선만 교체했다. `TravelTime`의 도로 주행과 도착정보 공백 시 대표 배차는 로컬 v5 입력에 남아 있었다. 이를 유지한 채 새 대기곡선만 적용하면 서로 다른 운행시계를 결합하게 되므로, 같은 발행 payload의 `city_operations`를 함께 읽는다.

1. `LatestQueueModel`이 무결성·방향·정류장·알고리즘을 검증한 모델을 선택한다. 한 경로 비교에는 같은 모델 객체가 고정된다.
2. 새 운행시계는 공식 정류장 순번과 ID가 일치하는 시내·마을버스 구간에만 연결한다. 불규칙 출발시각에 각 구간 진입시각의 총 소요초를 더한다. 이미 포함된 도착지 정차시간은 다시 더하지 않는다.
3. 충분한 과거 완료시간, 같은 차량의 신선한 도착예정 차이, 신선한 구간속도를 우선한다. 같은 요일의 2일 이상 저장 구간속도도 전이 모형보다 우선한다. 그 외 해당 구간에는 새 평일 운행시간을 사용하고, 범위 밖 구간은 기존 모형으로 보완한다.
4. 신선한 실제 도착예정이 없으면 새 운행시계에서 다음 기회를 찾는다. 실시간 검색은 마지막 도착예정으로 위상을 조정할 수 있지만, 시간 지정 검색은 현재 도착정보를 읽지 않는다. 실제 차량 ID나 제공시각을 만들어 넣지 않는다.
5. FIFO 추가대기는 새 운행으로 이미 산출된 초 단위를 사용한다. 배차비율을 다시 곱하지 않는다. 기존 만차 표지 기반 위험과는 최대값으로 결합해 중복 가산을 피한다. 등급을 승객 수나 빈 좌석 수로 바꾸지 않는다.
6. 정문 공동노선도 새 모형상 먼저 탑승할 수 있는 후보로 비교한다. 불규칙 시계를 다시 균등 잔여대기로 대체하지 않는다.

## 데이터 계약

- payload: `city_operations.schema = snu_city_operations_v1`
- `revision`: `weekday_transfer_operations_20261110_v1`
- `network_sha256`: 앱 `data/network.json`의 정확한 SHA-256
- `weekdays`: `[0,1,2,3,4]`, `source_dates`: `["2026-11-09"]`, `transfer_estimate`: `true`
- `coverage_start_seconds`: 40800, `coverage_end_seconds`: 83400. KST 자정 이후 초의 적용 범위다. 학기 날짜 필드와 구별한다.
- `includes_destination_dwell`: `true`, `dwell_added_separately`: `false`
- `routes[rid].stops`: 공식 노선 방향의 연속 `{id,seq}`. 일부 노선은 모델에 있는 부분 구간만 포함한다.
- `routes[rid].departures[weekday]`: 첫 포함 정류장 기준 자정 이후 출발초의 오름차순 배열
- `routes[rid].segment_profiles[weekday]`: `[시작초,종료초,[인접구간별 총초,...]]`. 반열린 구간이며 진입시각으로 선택한다.
- `city_wait.delay_scale_policy`: `absolute_audited_clock`, `operation_revision`: 같은 운행 revision
- `city_wait.services[*].reference_headway_by_weekday`: 요일별 참조 간격. 마지막으로 읽은 금요일 값을 다른 요일에 덮어쓰지 않는다.

평일 운행시계가 포함된 발행의 알고리즘은 `latest-v5-all-shuttle-clock-fifo-v4`이다. 새 앱은 v3/v4를 모두 읽고, 구형 앱은 v4를 거부해 기존 정상 모델을 유지한다. 셔틀과 기본 topology 호환성에 쓰는 `travel_clock_model` 및 기존 compatibility 해시는 유지한다. 운행 내용은 payload 해시와 v4 검증으로 보호한다.

## 범위와 검증

새 시내버스 배차 변동은 15~19시를 중심으로 한 월요일 관측의 평일 전이다. 주말·학기 범위 밖·23:10 뒤를 새 시계의 운행 종료로 판정하지 않으며 기존 일반 운행 추정을 사용한다. 셔틀 시간표, 학생 총수요·목적지 비율·정원·기존 게이트 전환 계수를 이 코드에서 변경하지 않는다.

`verify_operation_clocks.py`는 공급자가 생성한 사전 운행시각과 앱 reader를 별도로 대조한다. 현재 8노선 × 5요일의 정류장 시각 **190,946개 모두 차이 0초**다. 이는 구현 일치 검증이며 다른 날짜의 예측 정확도 검증은 아니다. 결과는 `operation-clock-verification.json`에 있다.

핵심 회귀 68개와 전체 Python 회귀 237개가 모두 통과했다. 소스 이식 후 새 reader 시험 13개도 통과했다. 별도 합성 경로 시험에서는 실제 `/api/plan` 흐름으로 최신 ETA 우선, 정문 공동노선 불규칙시계 유지, 대기·이동 동일 모델 및 시간합계 일치를 확인했다. 이후 독립검산이 끝난 실제 v8 payload로 5요일×2출발지×4목적지의 old/new 80개 계산도 통과했다. 마지막 요일 우선순위 보완 관련 61개 회귀가 통과했고, 공개 클라우드 경로에서 새 운행시간과 충분한 과거 완료시간이 각 우선순위대로 적용되는지 확인했다.

이는 구현·정합성 검증이다. 실험실 담당자가 공유한 기존 정문 17:03 관측과의 잔차는 v8에서 커졌으며 공개 설명서에도 기록돼 있다. 이 세 보정용 관측을 독립 검증으로 재사용하거나 이를 맞추기 위해 게이트 계수·수요를 다시 조정하지 않았다.

## 파일과 보존

- `app_candidate/`: 원본 앱에서 인증·환경·런타임·node_modules를 제외한 별도 작업본
- `source-preservation.json`: 변경 전 원본 앱 260개 파일의 SHA-256
- `candidate-tests.txt`, `candidate-all-tests.txt`: 회귀 결과
- `operation-clock-verification.json`: 새 운행시계 일치 검증
- `route-bridge-verification.json`: 공급자 호출 없이 수행한 합성 경로 연결 시험
- `source-apply-receipt.json`: 로컬 앱 13개 소스 이식, 기존 250개 파일 보존, 운영 배포 없음
- `installed-smoke-tests.txt`: 이식 후 13개 시험 통과
- 원본 앱 이식 시 변경하는 파일만 `before_apply/`에 보관하고 이식 영수증에 파일별 해시를 남긴다.

API 키, 환경변수, 수집기 호출 한도, 기존 모델 데이터, 공개 UI는 변경 대상이 아니다.
