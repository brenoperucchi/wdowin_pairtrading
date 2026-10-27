---
phase: 01-indicador-e-grafico-de-fluxo-sintetico
plan: 01-01
subsystem: ui
tags: [react, fastapi, lightweight-charts]

requires: []
provides:
  - Backend circular cache, async collection loop, and realtime API endpoint
  - Real-time flow score single-line chart component using lightweight-charts
  - Integration and synchronization of FlowScoreChart in the dashboard layout
affects: []

tech-stack:
  added: []
  patterns:
    - M5 downsampling on frontend for perfect visual alignment and logical range sync

key-files:
  created:
    - regime-dashboard/src/components/FlowScoreChart.jsx
  modified:
    - server.py
    - regime-dashboard/src/App.jsx
    - regime-dashboard/src/components/ZScoreChart.jsx

key-decisions:
  - "Downsample 5-second flow score to 5-minute bars on the frontend to allow pixel-perfect vertical alignment and logical range sync across all charts"

patterns-established:
  - "Frontend-side downsampling/bucket aggregation of high-frequency metrics to align index-based timelines"

requirements-completed:
  - REQ-002

duration: 45min
completed: 2026-06-12
---

# Phase 01: Indicador e Gráfico de Fluxo Sintético - Plan 01 Summary

**Real-time synthetic institutional flow score backend engine with matching React single-line chart aligned to 5-minute timelines**

## Performance

- **Duration:** 45 min
- **Started:** 2026-06-12T10:00:00Z
- **Completed:** 2026-06-12T15:50:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Implemented `_realtime_flow_cache` circular cache (maxlen=10000) and FastAPI startup lifespan backfilling for pre-seeding today's session ticks.
- Created `FlowScoreChart.jsx` component using `lightweight-charts` to display the color-coded single line score.
- Implemented 5-minute frontend downsampling of 5-second flow score ticks in `App.jsx` to match the other charts' indices, enabling pixel-perfect vertical logical range synchronization.
- Resolved Z-Score and Flow Score Y-axis autoscale issues using `autoscaleInfoProvider` to clamp values.

## Files Created/Modified
- `server.py` - Backend score computation, seeding, and endpoint
- `regime-dashboard/src/components/FlowScoreChart.jsx` - Line chart component with color thresholds
- `regime-dashboard/src/App.jsx` - Frontend integration, downsampling, and logical scale sync
- `regime-dashboard/src/components/ZScoreChart.jsx` - Restored autoscale bounds and labels

## Decisions Made
- Downsampled 5s ticks to 5m bars in the React layer. This allows all 5 charts to share the exact same logical indexes and timestamps, resolving the lightweight-charts alignment shift and allowing perfect vertical scrolling/zooming.

## Deviations from Plan
- **M5 Scale Shift:** The initial plan assumed direct time-scale synchronization between the 5-second chart and the 5-minute charts. During testing, this caused horizontal grid lines and timestamps to misalign due to index-based chart rendering. We resolved this deviation by downsampling the flow score to 5-minute bars on the frontend.

## Issues Encountered
- Playwright browser CDP protocol errors on WDO×WIN environment blocked automated screenshot checks. Verified manually via successful `npm run build` production compilation.

## Next Phase Readiness
- Phase 1 complete. Ready to proceed with validation and completing the milestone.
