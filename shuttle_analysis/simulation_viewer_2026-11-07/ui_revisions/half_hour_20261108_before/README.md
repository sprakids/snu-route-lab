# 하교길 실험실 v5 · 시내버스 정원과 평일 운행계획

공개 지도: **https://snu-shuttle-simulation.vercel.app/** · 설명서: **https://snu-shuttle-simulation.vercel.app/methodology.html** · Markdown: **https://snu-shuttle-simulation.vercel.app/methodology.md**

2026-11-08 시내 8개 노선 차량·참고 정원·공동 대기열·만차 잔류·평일 첫차/막차/간격과 저장 구간속도를 적용했습니다. 5511·5513·5516·관악02-1·02-2는 저장 전체 정류장, 5515·5528·6515는 정문→입구역 5정류장 구간입니다. 일반50·마을24는 제조사 승객 제원 참고값이고 실제 배치 차종·등록정원은 미확인입니다. 외부 배경 승객은 미포함입니다.

기본 화면은 `capacity_v5`입니다. 차량 표시 필터로 시내·셔틀·개별 노선을 고르고, 시내 공동 승차지 55개와 기존 셔틀 승차지에서 대기열·그래프를 볼 수 있습니다. 이전 v4·v3도 선택할 수 있으며 원래 데이터는 보존했습니다. 로컬 서버 http://127.0.0.1:8786/ 도 계속 사용합니다.

지도에서 정류장 표식을 누르면 현재 시각의 대기량·만차 잔류를 팝업으로 확인할 수 있습니다. 가까운 승차지는 별도 항목으로 표시하며 항목 선택은 승차지 메뉴·그래프와 연결됩니다. 재생·시각 변경에 따라 갱신합니다. 기존 모델 결과를 재사용한 UI 변경입니다.

공식 정류장명으로 확인한 교내 정류장 간116개 시내 구간은 OSM 경계 밖 도로도 최고40km/h로 분류합니다. 공식 시내 평일 계획은 기점 시계이며 정확한 회차별 시간표나 정류장 통과시각 실측이 아닙니다. 과거 20개 평일의 시간당 구간 재차합은 비교값으로 따로 표시하고 개별 차량 여석이나 대기열로 바꾸지 않았습니다. 원본 입력·코드·검산 근거는 `city_bus_model_2026-11-08/README.md`, `documentation/methodology_source.md`, 배포 기록은 `deployment/README.md`에서 확인합니다.

2배차×5요일 전체 가중 흐름 재계산과 독립 검산 PASS, PC·모바일 공개 기능 검사 PASS입니다. 구현 검산은 현실 예측 정확도 검증과 구분합니다. v5는 시내 운행 시계·속도·정원·재판단을 함께 바꾸었으므로 이전 버전과의 차이를 정원만의 인과 효과로 해석하지 않습니다.

---

## 이전 v4·v3 설명 보존

아래는 이전 버전 당시의 기록입니다. 최신 화면·가정·배포 상태는 위 v5 안내와 통합 설명서를 따릅니다.

# 하교길 실험실 v4 — 대기줄 관찰 후 경로 변경

최신 통합 설명서: **https://snu-shuttle-simulation.vercel.app/methodology.html** — 시뮬레이션 v4와 경로 추천 v0.10의 가정·자료·출처·전후 비교 분모를 구분합니다. Markdown 다운로드와 근거·해시 JSON도 제공합니다. 원고는 `documentation/methodology_source.md`, 생성기는 `documentation/build_methodology.py`입니다.

공개 주소: **https://snu-shuttle-simulation.vercel.app/** — 2026-11-08 Vercel 운영 배포. 설치·로그인 없이 기존 v4 시뮬레이션을 재생할 수 있습니다. 배포와 재현 방법은 `deployment/README.md`를 참고합니다.

현재 기본 화면은 `capacity_v4`입니다. 로컬 주소 http://127.0.0.1:8786/ 도 계속 사용할 수 있습니다. [대기줄을 본 뒤]에서 경로 변경/기존 v3 유지 비교를 고를 수 있습니다. [경로 변경] 버튼은 실제 표시된 변경 흐름으로 이동하고, 변경 후 도보는 청록색입니다. 서울대학교 ARS21128에서 5511·5513·5515·5528·6515 공동 이용 대안도 포함합니다.

최신 가정과 출처: `팀공유_경로변경_가정과_자료출처.md`. 빌드: `prepare_adaptive.py`, `adaptive_capacity_model.py`. 검증: `test_adaptive_model.py`, `verify_adaptive.py`, `adaptive_model/independent_verification.json`. 아래 v3 설명과 원본 자료는 이전 조건의 기록으로 보존합니다.

---

# 하교길 실험실

로컬 주소: http://127.0.0.1:8786/

요일·초 단위 시각을 선택하거나 재생 버튼으로 흐름을 볼 수 있습니다. 속도는 1초/초부터 15분/초까지입니다. 지도 범위는 전체·윗공대·행정관으로 바꿀 수 있습니다.

- 버전 2 이동·대기열: 대표 반복(seed 20261106)의 경로 선택을 유지하고 전체 가중 입자를 공유 차량의 FIFO 정원 제약에 넣었습니다. 대형 60명·소형 역순환 25명 가정입니다. 못 탄 흐름은 빨간 점으로 남으며 다음 버스 탑승 뒤 이동합니다. 지연이 이후 보행·환승에도 전파됩니다. 점 1개는 약 2명 상당의 표시 표본이고, 정원·통계는 전체 가중 흐름으로 계산합니다.
- 피크 최소 간격: 15~19시 입구역 3분·교내 순환 5분입니다. 기준 4분·6분과 비교할 수 있습니다. 다른 시간대·대학동 10분·역순환 20분 조건은 같습니다. 실제 차량 회전이나 배차표를 검증한 실행 계획은 아닙니다.
- 최신 차량 속도 가정: 교내 최고40km/h, 교외 목표65km/h입니다. 도로 도형과 저장된 캠퍼스 경계, 가감속1m/s²·정류장15초 정차를 적용하고 이동시간·환승·대기열을 다시 계산했습니다. 화면의 재생 배율(1초/초 등)과 별개의 설정입니다.
- 그래프: 이번 모형의 요일·시간별 대기시간, 두 배차의 대기열 비교, 시간대별 만차 경험·미탑승량을 볼 수 있습니다. 표의 칸을 누르면 지도 시각으로 연결됩니다. 이전 평균 유입·20개 출발위상의 대기시간 표는 별도 탭에서 그대로 보존했습니다.
- 실제 학생 위치, 실시간 GPS, 실측 대기인원 자료가 아닙니다. 모형 대기량은 고유 학생 수와 구분합니다.
- 저장된 보행망·도로 도형과 공개 건물 위치를 사용합니다. 배경 지도는 OpenStreetMap이며 인터넷 연결이 필요합니다. 교통 API나 인증키는 사용하지 않습니다.

서버가 종료되었다면 이 폴더에서 실행합니다.

```powershell
& 'C:/Users/김예준/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' ./serve.py --port 8786
```

이 로컬 서버는 이 컴퓨터의 127.0.0.1에만 바인딩되며 public 폴더만 제공합니다. 같은 v3·v4 재생 자료를 제공하는 Vercel 정적 사이트가 별도로 배포되어 있습니다. 기존 경로 추천 앱과 별도 프로젝트입니다.

자료 검증과 정의: `capacity_model/model_notes.md`, `capacity_model/verification.json`, `capacity_model/independent_verification.json`을 참고합니다. 6개 해석적 사례는 `test_capacity_model.py`입니다. 이전 화면·자료는 `revisions/v1_before_capacity.zip`에 보존했습니다. 기존 `data_verification.json`과 `source_manifest.json`은 버전 1의 기록입니다.

최신 속도 재계산은 `speed_capacity_model.py`입니다. 공개 파일은 `public/data/capacity_v3/`, 작업 기록과 검증은 `capacity_model/speed_40_65/`에 있습니다. `verify_capacity.py --dataset capacity_v3 --work capacity_model/speed_40_65`와 `verify_speed.py`로 검산합니다. 기존 `capacity_model.py`와 `capacity_v2`는 이전 속도 조건으로 보존했습니다. 새로운 수강 자료·경로 선택·실제 출발표를 확보한 것으로 해석하지 않습니다.
