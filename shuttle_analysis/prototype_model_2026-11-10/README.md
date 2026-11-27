# 분리형 하교길 프로토타입

[첫9파일럿 결과와 근거](RESULTS.md)를 먼저 확인해 주세요. NOT_EVALUABLE·운영 미채택이며, 사용자의 새 지시에 따라 후속 개발을 계속합니다. 운영 V11을 바꾸려면 명시 승인이 필요합니다.

실행: experiment_lock.json의9개 유한 파일럿은 runs/<case>/attempt_04에 완료했습니다. 같은 시도를 덮어쓰지 마세요. analyze.py --resume는 감사·런타임 소스 해시를 확인해 수치 검산 결과를 재사용하고 비교표만 재생성합니다. 새 조건 실행은 새 후보 디렉터리에서 사전 실험표를 만든 뒤 진행합니다. run_remaining.py를 무작정 반복 실행하지 마세요.

build_engine.py는 초기 1회 생성용입니다. 현재engine.py의 후속 FIFO 수정이 검토된 소스이므로 재생성하지 않도록 방어 코드를 넣었습니다. 원래 source_snapshot과 중단·실패 기록은 보존합니다.

prepare.py는 원래 수요 질량·출발·목적지를 보존합니다. physics.py는 물리 시간, preferences.py/fares.py는 선호와 추가요금, capacity.py는 유한 여석, hazard.py는 사건시간, policy.py는 순차선택, engine.py는 실제 차량·여행자 장부, analyze.py는 독립 검산/비교, dwell.py는 별도 승차처리 작은 모형입니다. 내부 숫자를 실측으로 표시하지 마세요.
