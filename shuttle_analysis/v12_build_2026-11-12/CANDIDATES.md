# V12 후보 상태

- 현재 검증 후보: [261112111627](../261112111627/PLAN.md). 운영 교체 금지.
- 이전 미실행 후보: [261112111414](../261112111414/rejected_before_simulation.json). 시간대 경계의 역산 오차를 실행 전에 발견해 보존했다.
- 기반 R 실측 구간 후보: [261112104829](../prototype_observed_261112104829/PLAN.md). 구간시간만 연결한 비운영 비교본.
- 운영 기준: capacity_v11 / 261110162302.

숫자 식별자는 YYMMDDhhmmss이며 V12는 별도 메타데이터다. candidate.json은 최초 미실행 후보를 보존한 포인터이고, candidate_fifo.json이 현재 후보를 가리킨다. 공개 latest와 무관하다.
