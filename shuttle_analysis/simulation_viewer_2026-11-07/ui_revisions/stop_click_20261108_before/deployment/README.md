# 시뮬레이션 v5 공개 배포

운영 주소: https://snu-shuttle-simulation.vercel.app/ · 설명서: https://snu-shuttle-simulation.vercel.app/methodology.html

2026-11-08 `june-f3d1/snu-shuttle-simulation`의 production 배포 `dpl_6TUfghCjLTbyHJ88UMc6MCVXP6Nz`를 공개 주소로 승격했습니다. 정적 HTML·JavaScript·Leaflet 재생이며 교통 API를 호출하거나 새 시뮬레이션을 실행하지 않습니다. 별도 추천 앱 `snu-route-lab` 파일은 이번에 변경하지 않았습니다.

교내 정류장 사이116개 시내 구간을 최고40km/h로 보완하고 10개 조건을 다시 계산했습니다. 최종 속도 입력 식별은 `campus_stop_corridors_20261108`입니다. 수정 전 v5의 완료 결과·입력·감사기록은 `city_bus_model_2026-11-08/revisions/v5_polygon_only_release/`, 배포 영수증은 `releases/v5_polygon_only_20261108/`에 보존했습니다.

## 공개 범위

`prepare_static.py`의 허용 목록만 복사합니다. 공개 파일66개, 데이터36개(v3·v4·v5 각12개), 합계50,837,495바이트입니다. 원본 JSON 합계341,301,226바이트와 gzip48,099,557바이트를 대조했습니다. `.json` 요청을 `.json.gz`로 연결하고 JSON 형식·gzip 인코딩을 제공합니다. 기존v3·v4 압축 데이터24개의 해시도 이전 배포 기록과 일치합니다.

원본 수강파일·전체 감사 이동기록·모형 코드·로컬 실행기·Windows ZIP·인증정보·`.env*`·`.vercel`은 배포하지 않습니다. 선택 시나리오에 필요한 자료만 내려받습니다. 파일별 SHA-256은 `source_manifest.json`에서 확인합니다. Git 커밋 배포가 아니라 이 파일 스냅샷으로 소스를 식별합니다.

## 검증 기록

- `stage_verification_city_v5.json`: 검증한 production 단계 배포의 진입 HTML·설명서 근거·v5 공통·월요일 자료 원본 일치. CLI 관리 인증 우회 요청이며 익명 접근 증거와 구분합니다.
- `public_verification_city_v5.json`: 승격 후 운영 주소의66개 파일과36개 데이터 모두 인증 없이 HTTP200·내용 해시 일치. 모든 데이터 JSON은 gzip과 JSON 형식 확인.
- `release.json`: 최종 배포ID·대상·파일 수·검산·공개 기능 검사와 증빙 위치.
- `releases/pre_city_v5_20261108/`: 이전 문서·테마 배포 영수증과 README 보존. 원래 지도·문서 초기 기록도 기존 releases 아래 유지.
- 모델 근거는 `../city_bus_model_2026-11-08/independent_verification.json`·`results_summary.json`입니다. 10개 조건의 전체 원래 입자 가중치·차량 승하차/점유/정원·호환 FIFO·대기열·시간대 분모·출발계획·속도 상한을 검산했습니다.

공개 주소에서 Edge/Playwright, PC1440×1000·모바일390×844의11개 기능 검사를 통과했습니다. 페이지 식별·빈 화면/오류 패널·시내 차량과55개 승차지·필터·만차 잔류·1초/초 재생·8개 계획표·그래프→지도 이동·v4/v3 전환·과거 자료 단위·설명서/Markdown/근거JSON·모바일 넘침·콘솔 오류를 확인했습니다. 스크린샷·임시 검사 스크립트는 저장소 밖 `release.json`의 QA 폴더에 있습니다. Browser 플러그인이 제공되지 않아 설치된 Playwright를 사용했습니다.

직후5분 오류 로그 조회에는 기록0건이었으며 정적 사이트에는 서버 함수가 없습니다. 장기 안정성·모든 브라우저·네트워크·실제 평일 혼잡 예측 정확도를 검증한 것은 아닙니다. 배경 지도는 OpenStreetMap 인터넷 연결이 필요합니다. 새로운 상시 모니터링이나 예약 작업은 만들지 않았습니다.

## 같은 프로젝트에 배포

v5 계산·검산과 화면 검사를 끝낸 뒤 `python documentation/build_methodology.py`, `python deployment/prepare_static.py`를 실행합니다. 기존 인증과 연결된 `static_site`에서 Vercel CLI65.12.1의 `deploy --scope june-f3d1 --prod --skip-domain --yes`로 단계 production 배포를 만듭니다. 반환된 동일 배포의 파일을 확인한 뒤 `promote <검증한 주소> --scope june-f3d1 --yes`로 승격합니다. 로그인 없는 공개 주소도 다시 검사합니다. 키·토큰을 명령 인수나 소스에 넣지 않습니다.
