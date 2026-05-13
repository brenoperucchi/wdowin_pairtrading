---
id: TASK-2.1.4
title: Slice 4 — Campos risk_* em /api/v2/regime e flag em /health
status: To Do
assignee: []
created_date: '2026-05-13 20:25'
labels:
  - backend
  - server
  - api
  - observability
  - tests
dependencies: []
references:
  - docs/plans/separar-risco-linear-umbrella.md
  - 'server.py:1116'
  - 'server.py:1815'
  - tests/test_execution_timeline_server.py
parent_task_id: TASK-2.1
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Contexto

Slice de observabilidade. Não afeta a lógica de decisão — só expõe os números atuais para o dashboard e probes.

Depende dos Slices 1-3.

## Mudança

### `/api/v2/regime` (resposta de `_build_response`, server.py:1116-1179)

Adicionar quatro campos top-level (naming espelhando brief original):

```
"risk_stats_scope": "live" if LIVE_ORDERS else "all",
"risk_trades_today": <int>,
"risk_daily_pnl_brl": <float>,
"risk_minutes_since_last_loss": <float | None>,
```

Os valores numéricos devem vir do retorno de `evaluate()` (mais barato — sem query SQLite extra), recalculados pós-Phase 1 em linha 240-242 do `evaluate`. Decisão: estender o dict de retorno de `evaluate` para incluir esses três campos, ou recalcular em `regime_v2` com `live_only=bool(LIVE_ORDERS)`. **Preferência: estender retorno de `evaluate`** para evitar query duplicada.

### `/health` (server.py:1815-1869)

Adicionar somente `"risk_stats_scope": "live" if LIVE_ORDERS else "all"`. Não duplicar os números (evita query SQLite por probe).

## Testes

Novo em `tests/test_execution_timeline_server.py` (já tem padrão FastAPI TestClient):
- `test_api_v2_regime_includes_risk_stats_fields_live` — com LIVE_ORDERS=1 e seed paper + live, /api/v2/regime retorna risk_stats_scope="live" e os 3 campos numéricos refletindo só live.
- `test_health_includes_risk_stats_scope` — /health retorna risk_stats_scope correto.

## Nota de revisão

Optei por campos flat `risk_*` no top-level por casar com o brief. Antes do merge, validar com o consumidor real (dashboard front-end): se ficar feio crescer flat, refatorar para objeto aninhado `risk_audit: {scope, trades_today, daily_pnl_brl, minutes_since_last_loss}`. Não congelar sem ver no dashboard.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 /api/v2/regime retorna 4 campos top-level: risk_stats_scope, risk_trades_today, risk_daily_pnl_brl, risk_minutes_since_last_loss
- [ ] #2 /health retorna apenas risk_stats_scope
- [ ] #3 Valores numéricos vêm do retorno de evaluate (sem query SQLite duplicada)
- [ ] #4 Quando LIVE_ORDERS=1, scope='live'; quando LIVE_ORDERS=0, scope='all'
- [ ] #5 Testes novos em test_execution_timeline_server.py passam
- [ ] #6 Naming flat documentado como passível de revisão antes do merge (vide nota no plano)
<!-- AC:END -->
