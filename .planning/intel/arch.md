---
_meta:
  updated_at: "2026-05-02T12:22:00-03:00"
---
# Architectural Decisions

- **ADR-001**: PM2 is used to run both the FastAPI server and Vite frontend concurrently.
- **ADR-002**: React frontend uses polling (every 2.5s) instead of WebSockets to fetch from `/api/v2/regime` to maintain robust disconnection handling.
- **ADR-003**: NWE calculation strictly uses causal mode to prevent lookahead bias in the pair trading charts.
