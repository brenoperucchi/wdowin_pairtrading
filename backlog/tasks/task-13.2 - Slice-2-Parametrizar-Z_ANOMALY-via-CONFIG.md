---
id: TASK-13.2
title: '[Slice 2] Parametrizar Z_ANOMALY via /CONFIG'
status: Done
assignee: []
created_date: '2026-05-11 18:55'
updated_date: '2026-05-11 19:13'
labels:
  - gate
  - config
  - ui
dependencies: []
parent_task_id: TASK-13
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Escopo

Expor `z_anomaly` como 7º campo do runtime_config (live/replay), com fallback para `core/config.Z_ANOMALY=4.0` quando ausente. Habilita o operador a apertar (ex.: 3.5 em dias de news) ou afrouxar pelo slideover.

## Mudanças

- `core/runtime_config.py` — adicionar `z_anomaly` em VALID_KEYS, DEFAULTS.live e DEFAULTS.replay (default 4.0); validação `(0, 10]`.
- `core/risk_gate.py:168-187` — novo kwarg `z_anomaly: Optional[float]`; fallback `Z_ANOMALY` quando None; usar em `checks["z_anomaly"]`.
- `server.py:1159-1161` — passar `z_anomaly=live_profile["z_anomaly"]` para `risk_gate`.
- `regime-dashboard/src/components/RuntimeConfigSlideover.jsx` — adicionar campo `z_anomaly` no FIELD_LABELS / FIELD_HINTS / render (NumberInput).
- Tests: novo teste `test_z_anomaly_runtime_config_overrides_default` + atualizar `test_live_engine_falls_back_to_defaults_when_runtime_config_invalid`.

## Não-escopo

- Mudar a constante `Z_ANOMALY` em `core/config.py` (segue como fallback estático).
- Histórico/replay scripts (`scripts/replay_execution_timeline.py`) — só puxam do runtime profile, automaticamente herdam.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 DEFAULTS.{live,replay}.z_anomaly == 4.0
- [x] #2 Slideover renderiza campo 'Z anomaly' com hint 'Block when max(|z_wdo|,|z_di|) ≥ this'
- [x] #3 Validation rejeita valores fora de (0, 10]
- [x] #4 risk_gate respeita `z_anomaly` do live_profile via hot-reload
- [x] #5 Teste cobre cenário: live_profile.z_anomaly=3.5, |z|=3.7 → Z_ANOMALY block
- [x] #6 npm run lint + npm run build clean
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Slice 2 — Parametrizar Z_ANOMALY via /CONFIG (Done)

### Arquivos alterados

1. **`core/runtime_config.py`** — `z_anomaly` virou o 7º campo do FIELDS tuple. DEFAULTS.live e .replay agora carregam `z_anomaly: 4.0` (espelha `core.config.Z_ANOMALY`). Validação `(0, 10]` em `_validate_profile`. Docstring atualizada para "Seven tunables per profile".

2. **`core/risk_gate.py`** — Novo kwarg `z_anomaly: Optional[float] = None`. Fallback `z_anomaly_threshold = Z_ANOMALY if z_anomaly is None else z_anomaly`. Substitui o check estático: `abs(z_wdo) < z_anomaly_threshold and abs(z_di) < z_anomaly_threshold`.

3. **`server.py`** — `_build_gate` passa `z_anomaly=live_profile["z_anomaly"]` em ambas as chamadas a `risk_gate`. Hot-reload sem state.

4. **`scripts/replay_execution_timeline.py`** — `ReplayRuntimeProfile` ganhou campo `z_anomaly: float`; `from_mapping` parseia; `risk_gate` recebe o valor. Replay agora respeita o profile gravado.

5. **`regime-dashboard/src/components/RuntimeConfigSlideover.jsx`** — Adicionado `z_anomaly: "Z anomaly"` em FIELD_LABELS, hint `Block when max(|z_wdo|, |z_di|) ≥ this (0–10].`, NumberInput com step="0.01".

6. **`tests/test_runtime_config.py`** — Novo `test_defaults_z_anomaly_matches_core_config`; +5 cases parametrizados de validação (0.0, -1.0, 10.5, "4.0", True).

7. **`tests/test_risk_gate.py`** — `test_z_anomaly_kwarg_overrides_default` (z_wdo=3.7 + z_anomaly=3.5 bloqueia; sem override passa) e `test_z_anomaly_kwarg_can_loosen_threshold` (z_wdo=4.5 + z_anomaly=5.0 passa).

8. **`tests/test_execution_timeline_server.py`** — payloads POST `/api/runtime-config` e helper `_live_profile` ganharam `z_anomaly: 4.0` para passar validação estrita.

### Verificação

- `PYTHONPATH=. pytest tests/ -q --ignore=tests/test_backfill_bar_history_indicators.py` → **304 passed**.
- `npm run lint` → clean.
- `npm run build` → 782.83 KB, 4.16s.

### Comportamento esperado

Operador pode apertar `z_anomaly` para 3.5 antes de payroll/copom pelo slideover; sem override, segue `core.config.Z_ANOMALY=4.0` (compat reverso). Slot reason `Z_ANOMALY` continua sendo o sinal canônico de bloqueio.

### Próximo

TASK-13.3 — `beta_unstable` como hard-block (Δβ% state machine no risk gate).
<!-- SECTION:FINAL_SUMMARY:END -->
