할루시네이션 방지 O

# Google 지도 API 키 확인 결과

확인일: 2026-11-04 KST. 사용자가 지정한 `sprakids06@gmail.com` 계정에 연결된 Chrome 프로필에서 Google Cloud Console의 로그인 계정과 프로젝트별 사용자 인증 정보를 직접 확인했다.

## 현재 확인된 상태

프로젝트 선택기의 ‘전체’에는 조직 없음 아래 두 프로젝트가 표시됐다.

| 프로젝트 | 프로젝트 ID | API 키 | OAuth 클라이언트 | 지도 API 활성화 |
|---|---|---:|---|---|
| Touchline Atlas | neon-opus-508616-i3 | 0개 | Touchline Atlas Web | 사용 설정된 API 22개에 지도 관련 서비스 없음 |
| multi-platform-game-site | multi-platform-game-site | 0개 | Mini Arcade Web | 사용 설정된 API 22개에 지도 관련 서비스 없음 |

두 프로젝트 모두 사용자 인증 정보의 API 키 표가 ‘표시할 API 키가 없습니다.’라고 표시했다. OAuth 클라이언트 ID의 존재만으로 지도용 API 키가 발급됐다고 판단하지 않았다. 계정에 접근 가능한 현재 프로젝트에서 확인한 결과이며, 다른 계정·지도 서비스의 키까지 없다고 단정하지 않는다.

공식 문서가 안내하는 Maps Demo Key 경로도 같은 계정으로 열었다. 현재는 ‘아래 약관에 동의하면 지도 데모 키가 생성됩니다’라는 신규 발급 화면이며, 국가 대한민국과 계정 이메일이 표시됐다. 약관 동의 및 키 생성은 하지 않았다.

검사 메타데이터와 표시된 API 이름은 [google_cloud_project_audit.json](google_cloud_project_audit.json)에 남겼다. [두 번째 프로젝트 인증 정보 화면](multi_platform_credentials.jpg), [데모 키 발급 대기 화면](maps_demo_terms_ready.jpg)도 보존했다. 키 원문을 회수하거나 저장한 것은 없다. 기존 프로젝트·키·결제 설정은 변경하지 않았다.

## 연결을 진행하는 방법

1. 시제품은 Google Maps Demo Key로 시작할 수 있다. 공식 문서상 결제정보 등록 없이 지도 표시, 마커, 이벤트, 도형 표시 등 제한된 기능을 시험할 수 있다. 사용량 한도가 있으며 시험·평가 용도이고 운영 서비스에는 사용할 수 없다.
2. 새 키 생성 및 Maps Demo Project 약관 동의에 대한 실행 시점 확인을 사용자에게 요청했다. 이는 기존 키 확인과 별개의 작업이다. 기존의 광범위한 권한 부여만으로 신규 키 생성과 약관 동의까지 완료했다고 간주하지 않는다.
3. 확인을 받으면 키를 생성·보관한 뒤, 관악캠퍼스 배경지도에 이미 확보한 버스 GPS와 정류소 좌표를 표시하는 연결부터 검증한다. 데모 키의 실제 제한·사용 가능 기능은 생성 후 화면과 실제 지도 로딩으로 확인한다.
4. Google 지도 키와 서울시 버스 키는 별개로 관리한다. Maps JavaScript API의 브라우저 키는 지도 로딩 요청에 사용되므로 서울시 수집 키와 동일한 비밀 관리 방식이라고 설명하지 않는다. 표준 지도 키에서는 Google의 권고에 따라 API·웹사이트 제한을 적용해야 하며, 데모 키의 설정 가능 범위는 확인 전이다.

현재 상태는 **기존 키 확인 완료 / 사용 가능한 키 확보 전 / 지도 연결 전**이다. 약관·신규 키 생성 확인을 기다리는 Google Cloud 탭은 다음 작업을 위해 열어뒀다. 유료 결제나 정기 작업은 시작하지 않았다.

근거:

- [Google Maps JavaScript API 설정](https://developers.google.com/maps/documentation/javascript/get-api-key)
- [Maps Demo Key 기능과 사용 방법](https://developers.google.com/maps/documentation/javascript/demo-key)
- [Maps Demo Project 서비스 약관](https://cloud.google.com/terms/maps-platform/demo-project-terms)
- 해당 계정의 Google Cloud Console에서 직접 확인한 프로젝트·인증 정보·사용 설정된 API 목록.
