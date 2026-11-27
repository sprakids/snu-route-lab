# 실측 자료 사용 장부 — 261112220847

원본 사용을 추적하는 읽기 전용 대조입니다. 새 수치 보정이나 동결 입력 수정은 하지 않았습니다. 식별 가능한 기존 관측 입력은 계승하고, 자료가 없는 항목은 미확보로 남겼습니다.

기존 목록53항목, 보존 스냅샷39개, 현재 동결 실측 관련 입력7개를 대조했습니다. [해시·소비 위치·제약 원장](observation_usage_ledger.json).

|자료|사용|반영 위치 / 한계|
|---|---|---|
|city-headways|inherited_runtime_input|frozen operations_v12_empirical.json route departures; operations.journeys; empirical_v12.Evidence.headways; Direction/stop sequence/hour retained; sample gaps15..3600s; inferred reference-stop crossings, not official dispatch or personal waits; reused overlapping passages are dependent.|
|city-segment-times|inherited_runtime_input|frozen operations_v12_empirical.json segment_profiles; time_profiles.values_at; Elapsed detected passages include signal/dwell/detection uncertainty; no second blanket dwell. FIFO interpolation and physical caps retained. Cannot identify pure moving speed independently.|
|city-categorical-grades-and-transitions|inherited_runtime_choice_risk|empirical_v12.Evidence.context; preferences crowd exposure; API0 is missing. Known API3..6 mapped to ordinal0..3; does not mean0..3 people. Same-vehicle transitions retain route/sequence/hour; risk coefficients remain a scenario.|
|city-full-flags|inherited_runtime_context|empirical_v12.Evidence.context full_flag_probability; Known flags only, not available seats. Does not physically inject a measured external passenger count.|
|old-nov09-bus-detector|provenance_and_legacy_context_only|inherited evidence snapshots and limitations; Midday detector logic changed; not current V12 headway/segment training. Operations JSON retains older source/retained_headway metadata in addition to explicit current training_dates; route departures use V12 Nov10 anchoring, not a newly observed Nov09 shuttle timetable.|
|nov11-date-split|already_explored_retrospective_diagnostic|ancestor evidence validation and bridge reconciliation; Not used for current training; already inspected, cannot be called pristine validation. Aggregate multi-date candidate summaries are not silently fitted.|
|three-monday-queue-snapshots|reused_comparison_and_historical_selection|grid-field-comparison.csv and inherited queue calibration lineage; Date inferred; culture direction uncertain; minute-uniform seconds are a comparison assumption, no best second. No new fitting of growth2.|
|tuesday-queue-and-capacity|inherited_supply_amendment_and_reused_comparison|capacity.py batch_size_at_clock; prepared_capacity44_pair; grid-field-comparison.csv; Earlier83/69 counts,46 capacity and15:23 bus arrival superseded. Arrival after15:24 is approximate, exact unknown.2x44 pair scenario daytime15..19 retained, not evidence every batch is exactly3min. Two photos are one episode.|
|tuesday-individual-wait|diagnostic_constraint_global_comparison_not_identifiable|ancestor individual_wait ledger + dwell.py micro model, not network global dwell fit; Network has coalesced arrival/boarding/departure, no observed exact arrival or matching unique synthetic passenger. Cannot report a measured personal-wait before/after error or fit global boarding service from this single episode.|
|shuttle-traffic-time-and-dispatch|partially_available_official_and_scenario|existing supply/offsets; capacity pair amendment; BUSIN overwritten cache/schematic coordinates are not continuous GPS. No observed shuttle traffic-dependent speed/dispatch distribution to fit; city segments cannot be relabeled shuttle observations.|
|external-numeric-occupancy-and-village-grades|unavailable_not_fitted|existing background occupancy scenarios and missing-grade fallback; No observed numeric external load, seat-count mapping or village grades. Ordinal grades inform risk only; unknown grade is not free capacity.|
|saved-individual-trips|unavailable_not_fitted|없음; Saved records list is empty; no empirical individual route/travel-time sample.|
|historical-and-class-demand|inherited_weighted_demand_or_context|prepared_capacity44_pair and historical_evidence_context; Not actual unique-student destinations; library delay/dorm/destination shares remain declared scenarios; aggregate boarding events are not unique students or offered stop arrivals.|
|new-date-validation|reserved_unopened|future_evaluation_plan.json; Earliest11/13 00:00KST for11/12; first check date/schema/coverage before outcomes; no new raw outcomes opened or automated job created.|

화요일 최종값은15:23 줄 합류,밖의 줄 본인 포함67명,정원44명,동행 두 대 중 두 번째 승차,순수대기189초+탑승 후30초입니다. 정확한 버스 도착시각은 없습니다. 개인 대기1건을 전체 정차시간 분포나 모든67명의 대기시간으로 복제하지 않았습니다.

새 규칙 전후 대기열과 가중 여정/차내시간은 모의 비교로 산출합니다. 실제 개인의189초 대기에 대한 전후 오차는 도착·승차·출발을 분리하지 못하는 현재 전역 모델에서 식별 불가이므로 숫자를 만들지 않았습니다. 이번 장부의 미확보 항목을 모두 보정했다고 표현하지 않습니다.
