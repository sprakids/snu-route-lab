# T-data 과거 버스 구간 자료와 예비 보정

이 폴더는 2026-11-07에 사용자가 승인한 API 활용신청·인증키 보관·과거 자료 수집·시뮬레이션 비교 작업입니다. 운영 앱과 별도의 로컬 연구 산출물입니다.

최종 설명은 `과거_재차합_수집과_예비보정_결과.md`, 검증 근거는 `artifact_verification.json`을 보십시오. 최종 파일이 없는 동안에는 작업 중인 상태입니다.

인증키는 저장소 밖의 `%LOCALAPPDATA%\SnuRouteLab\secrets\tdata\api-key_20261107.dpapi`에 현재 Windows 사용자용 DPAPI로 암호화했습니다. `local_secret.py`가 필요할 때 프로세스 안에서 복호화합니다. 값은 명령줄 인자·보고서·프런트엔드에 넣지 않습니다. 다른 Windows 계정이나 Vercel에서 이 파일을 그대로 사용할 수 있다는 뜻은 아닙니다.

수집에는 `collect_dates.py --dates YYYYMMDD ... --max-requests 150 --workers 2`를 사용합니다. Python 실행 파일을 앞에 붙여 실행합니다. 완료된 날짜는 캐시를 사용하며 호출 장부는 `api_request_ledger.json`입니다. 프로그램은 자동 재시도하지 않고, KST 날짜가 달라지면 기존 일일 장부를 조용히 재사용하지 않습니다. 이번 수집 결과를 보기 위해 다시 호출할 필요는 없습니다.

분석 순서는 `normalize_observations.py` → `review/segment_model/run_segment_features.py` → `calibrate_model.py --features review/segment_model/outputs/conditional_segment_hour.csv` → `build_report.py` → `verify_artifacts.py`입니다. 분석 프로그램은 완료된 출력 폴더를 덮어쓰지 않습니다. 재실험은 새 버전 폴더를 정해 원본과 이전 결과를 보존한 뒤 수행해야 합니다.

모형의 목적지 비중·기숙사 비중·즉시 이동률은 참고 가정입니다. API 재차합과 같은 단위로 맞춘 구간 통과 모형도 전체 승객의 일부만 설명합니다. 실측 전체 합에 맞춘 계수를 학생의 실제 귀가율로 사용하지 않습니다. 평균·최대·운행횟수의 결측과 공개 집계 정의의 한계는 최종 보고서에 기록합니다.

자료 제공: [서울특별시 서울교통 빅데이터 플랫폼 API1025](https://t-data.seoul.go.kr/dataprovide/trafficdataviewopenapi.do?data_id=1025), 교통정책지원시스템(TAIMS). 저작권자 표시(BY) 조건에 따라 출처를 표시했습니다.
