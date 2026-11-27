# 시뮬레이션 공개 배포

- 운영 주소: https://snu-shuttle-simulation.vercel.app/
- 배포일: 2026-11-08, Asia/Seoul
- 프로젝트: `june-f3d1/snu-shuttle-simulation`
- 최신 배포 ID: `dpl_HUqCYwau7rJFRf9TbN1xsnsZgBz4` (설명서·연결 UI 추가)
- 대상 / 상태: production / READY
- 프레임워크: 없음. 정적 HTML·JavaScript·Leaflet 사이트
- 빌드: 2초, 후처리: 5초
- 소스 식별: Git 커밋 배포가 아닌 `source_manifest.json`의 파일별 SHA-256 스냅샷

기존 `snu-route-lab` 개인화 경로 추천 앱과 별도 프로젝트입니다. 서버에서 교통 API를 조회하거나 시뮬레이션을 다시 실행하지 않습니다. 저장된 v4 경로 변경 결과와 v3 경로 유지 결과를 브라우저에서 재생합니다. 실제 학생 위치·실측 줄 인원·현재 운행 자료가 아닙니다.

## 배포 범위와 데이터 보존

`prepare_static.py`는 UI 파일 6개, Leaflet 파일 8개, v3·v4 압축 JSON 24개, 설명서 파일 4개를 `static_site/public/`으로 복사합니다. 각 압축본을 원본 JSON과 바이트 단위로 대조하고 파일별 해시를 기록합니다. 원본 계산·시뮬레이션 입력·Windows ZIP·로컬 실행기를 변경하지 않습니다. 설명서 HTML·Markdown·CSS·근거 JSON은 `documentation/build_methodology.py`로 생성합니다.

최신 공개 파일 42개의 총 크기는 19,941,158바이트입니다. 데이터 24개의 원본 JSON 합계는 141,429,364바이트, 압축본 합계는 19,610,839바이트입니다. Vercel은 `.json` 요청을 저장된 `.json.gz` 파일로 연결하고 `Content-Encoding: gzip`과 JSON 형식을 지정하므로 기존 브라우저 코드를 그대로 사용할 수 있습니다. 현재 시나리오에 필요한 파일만 불러오며 24개를 처음부터 모두 다운로드하지 않습니다.

원본 모델 파일·자격증명·`runtime`·`.env*`·`.vercel`·이전 버전의 사용하지 않는 대용량 자료는 공개 파일 목록에 포함하지 않습니다. 파일 이름이 고정되어 있으므로 캐시는 재검증하도록 설정했습니다.

## 검증

- `source_manifest.json`: 최신 공개 대상 42개 파일, 압축본과 원본 일치, SHA-256.
- `stage_verification_docs.json`: 최신 단계 배포의 설명서 HTML 원본 일치, 설명서 4개 추가·기존 진입 HTML/CSS 변경과 데이터 24개 불변 확인.
- `public_verification_docs.json`: 최신 운영 주소의 HTML·CSS·설명서·Markdown·근거 JSON 7개 모두 로그인 없는 HTTP 200·원본 일치.
- `releases/2026-11-08_initial/`: 최초 지도 배포의 manifest·단계/공개 검증·release 보존. 최초 공개 검증은 JSON 24개 모두 gzip 전달·압축 해제·원본 SHA-256 일치를 확인했습니다. 이 데이터는 최신 배포에서도 바뀌지 않았습니다.
- `release.json`: 최종 배포 상태와 검증 증빙 위치.

실제 Edge / Playwright에서 PC 1440×1000·모바일 390×844를 검사했습니다. Browser 플러그인이 제공되지 않아 설치된 Playwright를 사용했습니다. 최초 지도 배포에서는 재생·만차 잔류·경로 변경·그래프 등의 검증 10개가 통과했습니다. 최신 배포는 설명서 새 탭 열기·기존 요일/시각 보존·12절 본문·목차·출처 이동·전후 수치·Markdown 다운로드·근거 JSON·모바일 배치 검증을 추가합니다. 스크린샷·테스트 스크립트·결과는 저장소 밖의 `release.json`에 표시한 QA 폴더에 보존합니다.

이는 배포와 화면 작동 검증입니다. 실제 통학시간의 예측 정확도, 실제 평일 운행, 모든 브라우저·네트워크 환경을 검증한 결과는 아닙니다. 배경 지도는 OpenStreetMap 인터넷 연결이 필요합니다. 새 상시 모니터링·드레인·예약 작업은 구성하지 않았습니다. 이후 앱 안에서 화면 검증을 편하게 반복하려면 Browser 플러그인을 사용할 수 있습니다.

## 같은 프로젝트에 다시 배포하기

이 시뮬레이션 폴더에서 실행합니다. Python은 표준 라이브러리만 사용합니다. Vercel CLI 65.12.1과 `june-f3d1` 접근 권한이 있는 기존 인증을 사용합니다. 키·토큰을 명령 인수나 소스에 넣지 않습니다.

```powershell
python documentation/build_methodology.py
python deployment/prepare_static.py
Set-Location deployment/static_site
npx --yes vercel@65.12.1 deploy --scope june-f3d1 --project snu-shuttle-simulation --prod --skip-domain --yes
```

반환된 배포 주소의 HTML·JSON 압축 전달·지도 동작을 확인한 뒤, 확인한 동일 배포를 운영 주소로 승격합니다.

```powershell
npx --yes vercel@65.12.1 promote <검증한-배포-주소> --scope june-f3d1 --yes
```

배포 설정은 `prepare_static.py`에서 생성합니다. `static_site/`는 생성된 파일·로컬 Vercel 연결정보를 담으므로 Git 추적에서 제외합니다. 팀원에게는 운영 URL만 공유하면 됩니다.
