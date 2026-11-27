관측 속도 참고판261109162254(2026-11-09): 운영 기본v5와기존대기모델261109152540을보존하고, https://snu-shuttle-simulation.vercel.app/?dataset=empirical_speed_v1 에독립참고판을추가했습니다. 시내271구간새관측참고값·도로형상일치셔틀40모형구간proxy를적용해월~금×2배차10회공유정원/FIFO를재계산하고독립검산PASS를확인했습니다. 직접셔틀실측·평일예측정확도검증·외부배경승객인원포함이아닙니다. 자료52개·공개89파일이며원본117자료해시는불변입니다. 설명서는empirical-methodology.html, 검증/배포영수증은../empirical_speed_2026-11-09/deployment_receipt.json 및release.json을따릅니다.

요일·시간 조회(2026-11-09): 지도 왼쪽 위의 버튼에서 월~금·11:20:00~23:10:00·승차지를 지정하면 지도를 해당 시각으로 이동하고 정류장 팝업에 대기량·만차 잔류·다음 모형 차량까지 시간·같은30분 도착 구간의 평균/90백분위 대기를 표시합니다. 마지막23:10은 반열린 도착 구간 밖이므로 평균을 표시하지 않습니다. 구간 평균은 탑승 완료 흐름 기준이며 경로 변경·미탑승을 제외하고, 개인 시점 예측·실측과 구분합니다.

기존 HTML 진입점 두 개는 원문 그대로 유지하고 공용 snapshot-query.js가 조회 UI를 구성합니다. 기존 데이터39개·최신대기모델261109152540·알고리즘은 불변입니다. PC/모바일 공개 검증26항목, 경계 검산6그룹, 실패 후 재조회 검증과117개 자료 해시 보존을 통과했습니다. 배포와 증빙 경로는 release.json을 확인하세요.

최신 클릭 동작: 30분 구간의 시작 시각으로 이동합니다(15:30~16:00 →15:30). 공개 검증은 `public_verification_bin_start.json`, 단계 검증은 `stage_verification_bin_start.json`입니다. 데이터39개는 모두 불변이고 PC/모바일 클릭·요일·모형·안내 검증6개가 통과했습니다. 직전 파일은 `../ui_revisions/bin_start_20261108_before/`에 보존했습니다.



# 시뮬레이션 v5 공개 배포



운영 주소: https://snu-shuttle-simulation.vercel.app/ · 설명서: https://snu-shuttle-simulation.vercel.app/methodology.html



2026-11-08 `june-f3d1/snu-shuttle-simulation`의 production 배포 `dpl_422R8MRCSsYZX4caiBSa5VL4Xt9n`를 공개 주소로 승격했습니다. 정적 HTML·JavaScript·Leaflet 재생이며 교통 API를 호출하거나 새 시뮬레이션을 실행하지 않습니다. 별도 추천 앱 `snu-route-lab` 파일은 이번에 변경하지 않았습니다.



교내 정류장 사이116개 시내 구간을 최고40km/h로 보완하고 10개 조건을 다시 계산했습니다. 최종 속도 입력 식별은 `campus_stop_corridors_20261108`입니다. 수정 전 v5의 완료 결과·입력·감사기록은 `city_bus_model_2026-11-08/revisions/v5_polygon_only_release/`, 배포 영수증은 `releases/v5_polygon_only_20261108/`에 보존했습니다.



최신 UI 변경은 지도 정류장 클릭 대기량 팝업입니다. 기존 데이터36개는 바뀌지 않았고 모델을 다시 실행하지 않았습니다. 시내 정류장141개와 셔틀 승차지를 표시하고,99개 모형 대기열을 선택 메뉴·그래프와 연결합니다. 팝업은 시각·재생에 따라 갱신하고 유입 미배정 정류장은 모형0과 안내를 표시합니다. 같은 위치·가까운 승차지는 별도 항목으로 유지합니다. 변경 전 파일과 배포 식별은 `../ui_revisions/stop_click_20261108_before/`에 보존했습니다.



최신 차트 변경은30분 구간별 히트맵·상세 표입니다. 보존 v3/v4/v5 감사 기록30개를 `aggregate_half_hour.py`로 재집계했으며,46,750개30분 셀의 가중치·평균을 기존 시간 집계와 대조했습니다. 새 차트3개만 추가했고 기존36개 모델 데이터는 불변입니다. 경계·가중 평균·가중 분위수·미탑승 검열 단위검사4개와 PC/모바일 기능10항목을 통과했습니다. 검증은14개 열·25개 상세 구간·15:30 구간→15:30 지도·요일/배차/이전 모형 전환·모바일 스크롤·정류장 팝업·설명서·콘솔을 포함합니다. 증빙은 release.json의 새 QA 경로를 따릅니다. 변경 전 화면·문서는 `../ui_revisions/half_hour_20261108_before/`에 보존했습니다.



## 공개 범위



`prepare_static.py`의 허용 목록만 복사합니다. 공개 파일69개, 데이터39개(기존 v3·v4·v5 각12개와30분 집계3개), 합계51,682,121바이트입니다. 원본 JSON 합계352,022,844바이트와 gzip48,919,754바이트를 대조했습니다. `.json` 요청을 `.json.gz`로 연결하고 JSON 형식·gzip 인코딩을 제공합니다. 기존v3·v4 압축 데이터24개의 해시도 이전 배포 기록과 일치합니다.



원본 수강파일·전체 감사 이동기록·모형 코드·로컬 실행기·Windows ZIP·인증정보·`.env*`·`.vercel`은 배포하지 않습니다. 선택 시나리오에 필요한 자료만 내려받습니다. 파일별 SHA-256은 `source_manifest.json`에서 확인합니다. Git 커밋 배포가 아니라 이 파일 스냅샷으로 소스를 식별합니다.



## 검증 기록



- `stage_verification_half_hour.json`: 검증한 production 단계 배포의 진입 HTML·viewer/graphs JS·30분 v5 JSON·설명서 HTML의 원본 일치. CLI 관리 인증 우회 요청이며 익명 접근 증거와 구분합니다.

- `public_verification_half_hour.json`: 승격 후 운영 주소의69개 파일과39개 데이터 모두 인증 없이 HTTP200·내용 해시 일치. 모든 데이터 JSON은 gzip과 JSON 형식 확인.

- `release.json`: 최종 배포ID·대상·파일 수·검산·공개 기능 검사와 증빙 위치.

- `releases/pre_city_v5_20261108/`: 이전 문서·테마 배포 영수증과 README 보존. 원래 지도·문서 초기 기록도 기존 releases 아래 유지.

- 모델 근거는 `../city_bus_model_2026-11-08/independent_verification.json`·`results_summary.json`입니다. 10개 조건의 전체 원래 입자 가중치·차량 승하차/점유/정원·호환 FIFO·대기열·시간대 분모·출발계획·속도 상한을 검산했습니다.



공개 주소에서 Edge/Playwright, PC1440×1000·모바일390×844의10개 정류장 선택 기능 검사를 통과했습니다. 정류장 클릭 수치 대조, 시간·재생 갱신, 그래프 연결, 미배정0 안내, 키보드 Enter/Space, 다크 모드와 화면 배치를 확인했습니다. 페이지 식별·빈 화면/오류 패널·시내 차량과55개 승차지·필터·만차 잔류·1초/초 재생·8개 계획표·그래프→지도 이동·v4/v3 전환·모바일 넘침·콘솔 오류를 확인했습니다. 스크린샷·임시 검사 스크립트는 저장소 밖 `release.json`의 QA 폴더에 있습니다. Browser 플러그인이 제공되지 않아 설치된 Playwright를 사용했습니다.



직후5분 오류 로그 조회에는 기록0건이었으며 정적 사이트에는 서버 함수가 없습니다. 장기 안정성·모든 브라우저·네트워크·실제 평일 혼잡 예측 정확도를 검증한 것은 아닙니다. 배경 지도는 OpenStreetMap 인터넷 연결이 필요합니다. 새로운 상시 모니터링이나 예약 작업은 만들지 않았습니다.



## 같은 프로젝트에 배포



v5 계산·검산과 화면 검사를 끝낸 뒤 `python documentation/build_methodology.py`, `python deployment/prepare_static.py`를 실행합니다. 기존 인증과 연결된 `static_site`에서 Vercel CLI65.12.1의 `deploy --scope june-f3d1 --prod --skip-domain --yes`로 단계 production 배포를 만듭니다. 반환된 동일 배포의 파일을 확인한 뒤 `promote <검증한 주소> --scope june-f3d1 --yes`로 승격합니다. 로그인 없는 공개 주소도 다시 검사합니다. 키·토큰을 명령 인수나 소스에 넣지 않습니다.

