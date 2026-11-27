# 수단 자유와 현재 정류장의 변경 사유 분리

112731의 재검토 인지 일치와 기존 비선형 대기 효용을 유지한다.120358의 비용함수 민감도는월화평균+6.34/+5.03분으로실패해종료했으며이를수치조정으로구제하지않는다. 새로 확인한 것은 retain_released_mode_flexibility가한번true면현재 줄이짧아도stressed=True로만드는별개 상태 가정이다. 기존 단위시험에도 의도적으로 고정되어 있었으므로 우연한 코딩오류라고 단정하지 않는다.

사용자의 ‘기다리는데 만차가 반복되고 줄이 길면 다시 변경’과 수단을 자유롭게 고르는 상태를 분리한다. student_flexible는초기수단충성을다시걸지않는영구자유상태로유지한다. 새정류장에서는현재예상총대기·실제만차/추가통과·운행부재중기존기준으로변경사유가있을때만물리경로를재검토한다. 현재줄의시계·P·만차는원래대로이고현재줄이문제인동안에는재검토를계속한다. 제한/쿨다운/새숫자는없다. 초기·이후 모두 후속환승대기를미예견한다.

Monday/Tuesday regular main plus Monday pressure-separation-disabled diagnostic, once each. Compare the request baseline261116010854: physical/user behavior pass, zero unserved, nonworsening all-recorded over20 sum, four-reused-observation error sum, maximum wait, and each weekday mean journey; at least one strict improvement. Only then execute remaining eight main cases. Direct parent D and intermediate C reported separately. No demand/capacity/clock/patience/taste fit. All failures retained. No operating replacement.

모형선택과내부결과는새날짜실측정확도검증이아니다. 공개V11은유지한다.
