# Simulation output schema

Execution is complete only when execution_provenance.json has status=complete and runner_validation.json has status=PASS.

- stop_inflow_5min_scenarios.csv: existing schema; scenario/weekday/stop_id/stop_name/direction/route_id/route_name/time_bin/bin_minute/boarding_stage/expected_trip_events/lat/lon. Ten-replication means, restricted to 680 <= bin_minute < 1390. Values are stop-arrival boarding-demand weights, not actual boardings or measured congestion.
- conditional_mean_bins.csv: destination_group and conditional_trip_events replace scenario weights. Each group assumes all eligible enrollment events select that destination and move immediately. Multiply dorm by dorm_share*immediate_trip_share, and each external group by (1-dorm_share)*external_mix*immediate_trip_share, then sum. Includes outside-window bins for conservation checks; filter before comparison.
- conditional_mean_modes.csv and conditional_mode_conservation_by_rep.csv: whole modeled day, not only collection window. walk/city_first/shuttle_first/unassigned sum to enrollment weight independently for each destination condition.
- scenario_mode_conservation_by_rep.csv: whole-day scenario generation and modes. Transfer boardings are not new generated trips.
- replicate_stop_peaks.csv: raw positive-arrival physical-stop groups, with all/afternoon windows. Each row has separate all_boarding/first_boarding/transfer_boarding maximum five-minute weights, peak bins and window totals. The maximum of replicate bins differs from the maximum of mean bins.
- replicate_stop_direction_peaks.csv: same, preserving provider direction labels. These labels are not standardized compass directions.
- *_zero_filled.csv: complete replicate/scenario grid over the union of observed-in-simulation window/day/stop groups. Missing groups in raw peak exports mean zero simulated arrival events, not missing observations. Their peak times remain empty because no peak exists. Use these files when averaging replicate peaks; do not average only positive-presence rows.
- execution_provenance.json, input_manifest.json, evidence_snapshot_manifest.json: seeds, versions, hashes and assumptions. Original source and historical evidence are retained under input_snapshot/. Culture Hall's corrected stop is snu-300, distinct from Administration snu-410.
- original_preservation_check.json: original engine/source/output files and the user's XLS were preserved. No live bus APIs or production deployment settings were used.

Historical Sillim including Daehak is mapped to the Daehak representative point as a reference assumption. The original historical percentage discrepancy and current observed destination shares remain unchanged/null. No capacity, crowding-feedback or background-passenger model is introduced.
