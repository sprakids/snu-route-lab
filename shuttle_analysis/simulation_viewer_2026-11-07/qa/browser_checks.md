# Browser verification — 2026-11-07

Target: http://127.0.0.1:8786/ in the Codex in-app browser.

Observed:

- Data loaded into the real Leaflet map; no initialization error overlay remained.
- Monday 15:25 showed 1,269 active movement sample dots; Monday 12:25 showed 1,357; Friday 12:25 showed 125.
- Entering a time updated the clock, slider, and plotted data.
- Keyboard activation of Play changed the control to Pause and advanced the model clock from 12:25 to 14:05. Pausing stopped playback.
- Day selection changed the loaded data and weekday label.
- Switching to the separate queue model showed the capacity assumptions, six stop summaries, and queue dots. Monday 12:25 total modeled queue was 160.8 weighted units.
- Upper engineering and Administration focus controls changed map extent.
- The help dialog opened and closed; the two model semantics and limitations were visible.
- Slider Home and End reached 11:20 and 23:10.
- At emulated CSS sizes 1280×800 and 390×844, body scroll width equaled viewport width. Screenshots were inspected and saved as desktop.png and mobile.png.
- Captured console warning/error log was empty.

Automation limit: mouse input did not activate controls reliably while the in-app browser was under temporary mobile emulation and existing browser zoom. Functional control checks used normal keyboard activation and native form filling. This does not establish testing on physical mobile devices or every browser.

Temporary emulation and viewport overrides were reset after the checks. The local demo tab was kept for the user. The separate static verification covers exported path geometry, time ordering, queue nonnegativity, and compressed HTTP delivery.
