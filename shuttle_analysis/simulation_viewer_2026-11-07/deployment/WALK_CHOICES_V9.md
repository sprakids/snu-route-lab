# v9의 보존 자료와 배포

이번 릴리스는 기존 자료·릴리스의 경로를 유지합니다. 기존 보존 파일만 약 99.85MB라 새 10개 시나리오까지 하나의 업로드에 넣지 않습니다. 유료 플랜 변경 없이 같은 팀의 `snu-shuttle-v9-data` 정적 프로젝트에 새 불변 데이터만 배포하고 기존 시뮬레이션 주소에서 재작성으로 제공합니다. 사용자가 들어가는 주소는 같습니다.

1. `crowding_walk_choices_2026-11-10/selected_candidate.json`의 선택·해시와 10개 내부 검증 PASS를 확인합니다. 동일 관측 재사용이므로 독립 경험적 검증으로 부르지 않습니다.
2. `export_walk_choices.py`, `build_walk_choice_documentation.py`를 실행하고 검토된 UI를 복사합니다. 수강 원본·감사 궤적·모형 소스·키는 공개하지 않습니다.
3. `deployment/queue_source.json`의 선택 원문에서 `deployment/publish_queue_model.py`로 새 불변 경로 입력을 생성합니다. 준비 전에 취소된 방문을 준비완료 수요로 세지 않는 어댑터 검사를 먼저 통과해야 합니다. 검증기를 완화하지 않습니다.
4. `build_walk_choice_deployment.py cache`는 검증된 새 JSON의 Brotli 캐시만 만듭니다. 모델을 다시 실행하거나 포인터를 발행하지 않습니다.
5. `build_walk_choice_deployment.py data`는 공개 자료·새 경로 payload·990행 집계 CSV만 복사합니다. 복호화 내용 일치를 검사합니다. 전용 프로젝트에 배포한 뒤 익명 JSON·경로 입력 해시·압축 헤더를 확인합니다.
6. 실제 배포 주소를 `walk_choice_data_host.json`에 기록합니다. `build_walk_choice_deployment.py ui`는 `loading_perf_v7_261110`의 기존 보존 파일을 복제하고 새 UI·문서·최신 포인터·외부 데이터 경로만 추가합니다. 기존 모든 불변 파일은 바이트 단위로 비교합니다.
7. 단계 배포 확인 후 기존 주소로 승격합니다. 공개 PC/모바일 기능, 날짜·1x재생·정류장·30분 클릭·신규 문서·과거 데이터 전환·새 경로 payload를 다시 검사하고 구현 에이전트에 확정 모델ID/해시를 보냅니다.

기존 `prepare_static.py`는 v9 소스를 보면 위 UI 준비 함수로 위임합니다. v9를 빠뜨리고 v7까지만 발행하지 않게 한 것입니다. 기존 로딩 개선의 병렬 데이터 요청·캐시·작은 역사 차트 참조·지연 폰트는 유지합니다.

개별 단계의 영수증은 선택 후보의 `data-stage.json`, `ui-stage.json`, 발행·공개 검증 JSON에 남깁니다. 로컬 서버와 브라우저 테스트 증거는 임시 QA 폴더에 보존합니다. 보호된 단계 주소는 기존 CLI 권한으로 검사하며 보호 설정을 바꾸지 않습니다.
