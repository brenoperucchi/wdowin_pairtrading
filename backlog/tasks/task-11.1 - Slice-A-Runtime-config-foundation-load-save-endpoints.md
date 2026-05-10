---
id: TASK-11.1
title: '[Slice A] Runtime config foundation (load/save/endpoints)'
status: Done
assignee: []
created_date: '2026-05-10 22:02'
updated_date: '2026-05-10 22:08'
labels:
  - config
  - backend
dependencies: []
parent_task_id: TASK-11
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Backend foundation antes da UI:

- `core/runtime_config.py`: load/save/defaults/validation, retorna {live, replay} sempre.
- `config/runtime.json` com defaults atuais (live: 250 bars, bar; replay: 500 bars, daily).
- `GET /api/runtime-config` e `POST /api/runtime-config` em server.py.
- Tests: defaults, persistência, validação de tipos e ranges.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 core/runtime_config.py expõe load_runtime_config(), save_runtime_config(payload), DEFAULTS
- [x] #2 GET /api/runtime-config 200 mesmo se config/runtime.json não existir (retorna defaults sem criar arquivo)
- [x] #3 POST /api/runtime-config valida tipos+ranges (bars >= 60, threshold em (0,1], recalc in {bar,daily}, rho_level 1..3, beta_delta 0..100), 400 em inválido
- [x] #4 POST persiste atomicamente (tmp + rename) pra não corromper em crash mid-write
- [x] #5 Tests cobrem: defaults sem arquivo, save+load roundtrip, validações de erro, atomic-write
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Slice A landed.

**Files**
- `core/runtime_config.py` — load_runtime_config(), save_runtime_config(), get_profile(), DEFAULTS, FIELDS, PROFILES, EG_RECALC_VALUES. Strict per-field validation raises ValueError; thread-safe via module Lock.
- `config/runtime.json` — defaults committed (live: 250 bars/bar/0.10/level 2/25%; replay: 500 bars/daily/0.10/level 2/25%).
- `server.py` — `from core import runtime_config`; new `GET /api/runtime-config` (returns defaults inline if file missing) and `POST /api/runtime-config` (whole-document replace, 400 on bad JSON or validation, 500 on corrupt-on-disk).
- `tests/test_runtime_config.py` — 30 tests: defaults shape, no-auto-create on first read, save+load roundtrip, atomic write (no leftover tmp), failed save preserves prior file, malformed-JSON rejection, parametrised invalid values per field, missing fields/profiles, get_profile happy + error path, int→float normalisation.
- `tests/test_execution_timeline_server.py` — 4 endpoint tests: GET defaults when missing; POST persists+normalises; POST validation 400 (no file written); POST rejects invalid JSON.

**Validation**
- Atomic write uses `tempfile.mkstemp(dir=parent)` + `os.replace` so the file lands in one syscall.
- `eg_bars` floor 60, ceiling 100k. `eg_threshold` strictly in (0, 1]. `rho_breakdown_level` int in [1,3]. `beta_delta_max` in (0, 100]. `eg_recalc` in {bar, daily}. Booleans rejected (treated as not-int / not-number).
- Loader does NOT auto-create file; defaults are returned in-memory so old checkouts behave identically.

**Test results**
- `pytest tests/test_runtime_config.py -v` → 30 passed.
- `pytest tests/test_execution_timeline_server.py` → 28 passed (4 new + 24 prior).
- Full suite `pytest tests/` → 268 passed (was 234, +34).

**Review follow-up**
- Codex review flagged that `POST /api/runtime-config` would be blocked when the UI calls the backend directly because CORS allowed only `GET`; fixed in `server.py` by allowing `["GET", "POST"]`.
- Codex review flagged a stale comment saying replay defaults were `2240 bars / daily`; fixed in `core/runtime_config.py` to match the committed default (`500 bars / daily`).
- Focused validation after the fixes: `python3 -m py_compile core/runtime_config.py server.py`; `python3 -m pytest tests/test_runtime_config.py tests/test_execution_timeline_server.py -q` → 58 passed; `git diff --check` clean.

**Next slice (TASK-11.2)**: Replay reads from runtime_config["replay"] and recomputes EG with the configured window before calling risk_gate (currently the replay reads precomputed eg_pvalue from bar_history).
<!-- SECTION:FINAL_SUMMARY:END -->
