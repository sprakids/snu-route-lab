**261116160639 초기 배차 기대시각 정렬: 정적 의견**

2026-11-16. 명목 환승 대기를 추가하는 수정 부분만 읽었습니다. 모델·함수·검사는 실행하지 않았고 소스·설정·운영을 변경하지 않았습니다.159검사 통과는 소유자 보고이며 독립 재실행 결과가 아닙니다.

읽은 소스 SHA-256:
- nominal_transfer.py: 01323ccf652e823eb93136aff3f6adc109f552948e5640fbb66118fe3afc2d84
- policy.py: f16fd15dbbde7319a9145e8fde33c85a89fd4440aa9da00722d681dbd8f1433d
- behavioral_policy.py: 7b048d100e4b05147ab76e15b6a335a693fdc619131b27cdd28e467c84b228b2

**발견한 시간 기준 불일치**

초기 선택에서는 기존 expected_boarding_score가 첫 차의 정확한 빈 줄 잔여 phase를 reference로 치환합니다. 인과적 첫 줄 지연은 유지합니다. 그러나 그 뒤 호출하는 primary_extension에는 치환한 첫 승차시각을 전달하지 않고 원래 physical Prediction을 넘깁니다.

nominal_transfer.intervals50행은 i=1에서 old_removed=nominal_added=0이므로 raw row.arrival을 그대로 후속 정상 대기의 시간대 결정에 씁니다.51–52행의 셀은 이 값으로 정합니다. 따라서 첫 대기 점수와 후속 배차 기준시각이 서로 다릅니다.

```text
정규화한 첫 승차시각 = now + access + preparation + reference + queue_delay
원래 첫 승차시각     = now + access + preparation + exact_phase + queue_delay
후속 도착 기준의 차이 = exact_phase - reference
```

두 도착 기준이 다른 시에 속하고 그 시간대의 배차 분포가 다르면, 초기 비용이 교체 전 정확한 첫 위상의 영향을 간접적으로 받을 수 있습니다. 보통 같은 시에 있으면 이 효과는 드러나지 않습니다. 실제 완료 시나리오에서 얼마나 발생하는지는 평가하지 않았습니다.

현재 줄의 실시간 첫 승차 예측을 사용하는 일반 재검토 경로는 같은 문제라고 단정하지 않습니다. 초기 점수에서 첫 위상을 평균으로 교체한 경우에만 그 평균 첫 승차시각을 후속 reference의 anchor와 맞추는 방안을 검토해야 합니다. physical Prediction/운행/FIFO를 수정할 필요는 없습니다.

**추가 경계 조건**

residual_reference는 달력상 서로 다른 출발이2개 미만이면 ValueError를 냅니다. 현재 동결 입력에서 이 경로가 실제 발생하는지는 검사하지 않았습니다. 적용 가능한 모든 후속 서비스 달력이2개 이상이라는 사전 조건을 확인하거나, 연결 가능한1회 운행에서 전체 계산이 중단되지 않는 명시적 정보 부족 처리가 필요할 수 있습니다. 이 사항은 조건부 견고성 검토이며 확인된 운영 장애로 보고하지 않습니다.

이번 수정의 전체 성과·모형 정확도·운영 채택 판정은 하지 않았습니다. 검토 결과는 소유 실험 채팅에 전달했습니다.

