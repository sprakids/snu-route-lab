# 과거 평균·수업·배경 패턴 결합 예측

결과는 [검증 보고서](과거평균_수업_배경_결합모형_검증.md)에 있습니다. 결합형의 새 날짜 오차는 평균보다 소폭 줄었지만, 요일별 역사 평균보다 나빴습니다. 이 실험은 운영 앱을 교체하거나 재배포하지 않았습니다.

`predictor.py`는 표준 Python만 사용합니다. `frozen_models.json`과 같은 폴더에서 다음처럼 호출할 수 있습니다.

```python
from predictor import FrozenPredictor

model = FrozenPredictor("frozen_models.json")
estimates = model.predict(
    date="20261102", route_id="100100250", sta_sn=11,
    from_stop_id="110000654", to_stop_id="120000173", hour=12,
)
# estimates에는 동일한 입력에 대한 과거 평균·요일 평균·수업/배경 모형의 예측이 있습니다.
```

값의 단위는 **시간별 버스 구간 재차합**입니다. 버스 한 대의 탑승 인원·고유 승객 수·혼잡률이 아닙니다. API 키나 대상일 승객 수를 입력하지 않습니다. 월~금 12~22시와 학습된 정확한 노선/순서/끝점 키만 지원하며, 주말이나 미확인 정류장에 임의 예측을 붙이지 않습니다. 같은 요일이면 같은 역사 패턴을 쓰므로 당일 사건·날씨·배차 변화를 반영하지 않습니다.

`experiment_plan.json`은 학습·튜닝·평가 분리 계획, `selection_frozen.json`은 새 목표 자료 수집 전 생성한 모형·예측 해시입니다. `development/`는 개발 후보와 선택, `evaluation/`은 고정 모형의 새 날짜 평가, `verification.json`은 원 JSON·전처리·지표의 독립 대조 결과입니다. 이전 실험의 자료·보고서는 보존했습니다.

수정이나 후속 튜닝을 하려면 새 버전 폴더를 만드십시오. 이번 6일을 개발에 쓰면 그 날짜는 새 미사용 평가가 될 수 없습니다. 기존 실행 폴더를 덮어쓰는 명령은 거부합니다.

그래프의 로컬 재현 의존성은 `.taskdeps`에만 설치했습니다. 예측 코드에는 pandas·NumPy·Matplotlib도 필요하지 않습니다. 수집용 키는 저장소 밖 기존 Windows DPAPI 보관을 사용하며 이 폴더에 포함하지 않습니다.

자료 제공: [서울특별시 서울교통 빅데이터 플랫폼 API1025](https://t-data.seoul.go.kr/dataprovide/trafficdataviewopenapi.do?data_id=1025) / 교통정책지원시스템(TAIMS). 저작권자 표시(BY) 조건에 따라 출처를 표시했습니다.
