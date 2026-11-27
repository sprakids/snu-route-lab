# Version 2 rendered verification — 2026-11-07

Inspected the served site in the Codex in-app browser using the same loopback origin as version 1. Temporary viewport and CDP device emulation were used for responsive checks.

Observed controls and data:

- The capacity-constrained dataset loaded without a remaining loading/error overlay.
- Monday, minimum-headway condition, Administration → SNU Entrance, 15:30:01: queue 219.6 and previously denied flow 215.9 weighted units. The departing bus badge showed 60/60 and red queue dots remained. See desktop-capacity.png and mobile-capacity.png.
- At 15:32:59 the same queue displayed 252; at 15:33:01 it displayed 192. The stop card recorded boarding 60 at 15:33:00 with 191.8 ready-but-denied units still left.
- A 1 second/second playback interval advanced 9.543 model seconds over 9.518 wall seconds. Pause restored the Play control.
- Time entry included seconds. Slider endpoints reached 11:20:00 and 23:10:00.
- Switching from minimum to regular dispatch changed the Monday 15:00 arrival-cohort mean from 5.9 to 8.9 minutes. This is an observed rendered-value check, not a claim of observed real-world improvement.
- Weekday selection changed the line chart and table to Friday. Stop selection changed the scope of the heatmap, line, and table.
- The current and previous heatmaps both rendered. The previous Administration Monday 12:00 value was 17.2 minutes, preserved from the earlier dataset. The different model definitions are stated beside the chart.
- Both comparison series rendered with a common zero-based y scale. Keyboard Right on the line advanced the selected time one minute, and the stop card/line readout updated together. See comparison-line.png and mobile-graphs.png.
- Activating the Wednesday 16:00 heatmap cell selected Wednesday 16:30:00 in the map.
- The help dialog opened and closed, with capacity, FIFO, transfer propagation, headway, night-pair, and evidence caveats visible.
- At CSS sizes 1360×900 and 390×844, the page body had no horizontal overflow. The mobile heatmap and detailed table intentionally scroll horizontally; the line chart adapts its viewBox to the narrow width. The mobile playback controls remained within the viewport.
- Captured console warning/error logs were empty at the final functional check.

Automation scope: control activation was verified through keyboard input and native form filling. Mouse automation did not reliably target controls under this in-app browser's zoom/emulation setup, so mouse and physical-device acceptance are not claimed. Temporary overrides are reset before handoff, and the completed tab is retained for the user.

Calculation evidence is separate: capacity_model/verification.json, independent_verification.json, and the six analytical fixture tests. This is not validation against measured passengers or actual bus operation.
