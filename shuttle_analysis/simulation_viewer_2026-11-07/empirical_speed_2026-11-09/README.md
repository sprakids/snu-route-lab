# 관측 도로속도 참고판 261109162254

이 폴더는 원본 v5를 보존한 별도 속도 조건 재계산입니다. 알고리즘은 empirical_road_reference_20261109_v1이며, 공개 기술 데이터명은 capacity_v6입니다. 기존 /routing-model/latest.json과 추천 앱의 기본 대기모델은 그대로입니다.

- 입력: ../city_bus_model_2026-11-08/prepared.json.gz 및 협업 폴더 transport_observations/empirical_transport_candidates.json.
- 준비/계산: ../empirical_speed_replay.py. 준비된 기존 원본 캐시의 해시 변경을 허용하지 않습니다. 원본은 수정하지 않습니다.
- 10개 배치: run-regular-mon.json, batch-regular_remaining.json, batch-peak_all.json. prepared.json.gz와 audit-{scenario}-{day}.json.gz에 계산 근거를 보존합니다.
- 독립 검산/30분 집계: ../finish_empirical_speed_replay.py → independent_verification.json, public_data/charts.json, public_data/half_hour.json. 이 스크립트의 대기는 현재 실행 중인 유한 배치를 위한 것이며 예약 작업이 아닙니다.
- UI 내보내기: ../export_empirical_replay.py. city_route_stops는 준비 자료에서 파생한 UI 항목이며 계산값을 바꾸지 않습니다. ui_export_fix.json과 common_before_ui_export_fix.json에 초기 내보내기 수정 흔적을 보존했습니다.
- 설명서: ../build_empirical_documentation.py → public/empirical-methodology.html 및 md/그림, 협업 폴더의 비공개 설명서.
- 공개 준비: ../deployment/prepare_static.py. 기존 v3/v4/v5와 추가 v6, 최신 기존 대기모델을 함께 보존합니다.

참고판은 주말과 월요일 일부의 관측 소통속도에서 날짜별 중앙값을 만든 뒤 통합한 민감도 실험입니다. 실제 완료 운행시간 적합·평일 요일별 예측 검증·직접 셔틀 실측이 아닙니다. 셔틀에는 도로 형상이 맞는 경우에만 시내버스 공통도로 참고값을 썼습니다. 상한40/65 및 관측되지 않은 구간/모형 진입 전 시계 가정은 남아 있습니다.

교외에서 이미 탑승한 승객은 진입 혼잡등급 분포와 별도 용량 경계조건 계약으로 정리했습니다. 인원 환산 계수가 없어 숫자를 이 속도 참고판에 더하지 않았습니다. 관측된 총재차에 교내 모형 재차를 다시 더하는 중복 계산을 피해야 합니다.
