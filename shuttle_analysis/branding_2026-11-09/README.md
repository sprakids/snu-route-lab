# 하교길 아이콘 시안

- 선택 파일: `hagyogil-snu-home-icon-v1.png`
- 제작: 내장 image_gen 도구. 남색 바탕·흰색 서울대 심볼 참고·집·이동 화살표를 조합한 시안.
- 서울대 심볼 참고: https://identity.snu.ac.kr/ui/1
- 공식 참고 이미지: https://identity.snu.ac.kr/webdata/uploads/identity/image/2021/06/page-1-01.png
- 정확한 생성 지시문: `snu-home-icon-prompt.txt`
- 생성 원본: `C:/Users/김예준/.codex/generated_images/01a1a1e8-54cf-7243-9ad9-0a31e6f31a06/exec-fc474f2a-ed41-47f1-b812-48adb32fcabe.png`
- 원본은 보존하고 이 폴더에 복사했다. 현재 운영 사이트의 아이콘 파일이나 연결 코드는 변경하지 않았다.

## v2: 아이콘 크기와 배치 개선

- 선택 파일: `hagyogil-snu-home-icon-v2.png`
- 생성 전 설계: `icon-v2-design-brief.md`
- 제작 방식: 내장 image_gen 편집. v1과 공식 서울대 심볼 참고 이미지를 입력했다.
- 구성: 큰 서울대 심볼을 위로, 큰 집을 아래로, 짧고 굵은 하향 화살표를 오른쪽에 배치했다.
- 정확한 생성 지시문: `snu-home-icon-v2-prompt.txt`
- 생성 원본: `C:/Users/김예준/.codex/generated_images/01a1a1e8-54cf-7243-9ad9-0a31e6f31a06/exec-fd2a5dac-94da-4ec2-aed9-0ddca8a2ab12.png`
- 검토: `icon-size-check-v2.html`을 브라우저에서 실제 CSS 32·48·64px로 표시했다. 밝고 어두운 바탕 모두에서 48·64px의 새 심볼과 집을 구분하고 하향 이동 방향을 확인했다. 작은 심볼 안의 문구 식별을 보장하는 것은 아니다.
- 검토 화면: `icon-size-check-v2-light.png`, `icon-size-check-v2-dark.png`. 이미지 크기·로딩 기록: `icon-v2-size-measurements.json`.
- v1 원본은 유지했다. 운영 사이트의 아이콘·코드·배포는 변경하지 않았다.

## 운영 사이트 적용

2026-11-09 사용자 적용 요청에 따라 v2를 https://snu-route-lab.vercel.app/ 에 반영했다. 상단 로고는 48px, 브라우저 탭과 홈 화면용 아이콘은 용도별 PNG·ICO로 내보냈다. 개인정보·접근성 안내 페이지에도 적용했다. 원본 시안은 유지했다.

검증한 운영 배포는 `dpl_E5xxkXDwJCPHjYGwju9dxFnNCzES`이다. 구체적인 파일 변경·검사·제한·화면 증거는 `deployment/receipt.json`에 기록했다. 기존 v1/v2 설명의 ‘운영 미적용’은 각 시안 제작 당시의 기록이며, 이 적용 기록이 최신 상태이다.
