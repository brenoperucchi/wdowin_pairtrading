---
id: TASK-2.1.2
title: Slice 2 — live_only em _get_open_trades e propagação em evaluate
status: To Do
assignee: []
created_date: '2026-05-13 20:25'
labels:
  - backend
  - trade-engine
  - risk
  - tests
dependencies: []
references:
  - docs/plans/separar-risco-linear-umbrella.md
  - 'core/trade_engine.py:117'
  - 'core/trade_engine.py:157'
  - 'core/trade_engine.py:240'
  - tests/test_trade_engine.py
parent_task_id: TASK-2.1
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Contexto

Segundo slice da TASK-2.1. Continua sem impacto em runtime (defaults `False`). Depende do Slice 1 (precisa das 3 stats com kwarg `live_only`).

## Mudança

Em `core/trade_engine.py`:

1. `_get_open_trades(self, *, live_only: bool = False)` (linha 117): adicionar `AND live = 1` quando True. Docstring deve mencionar que paper-OPEN órfãos são omitidos em modo live e ficam "OPEN para sempre" no DB (decisão de design — ver plano).

2. `evaluate(..., live_only: bool = False)` (assinatura na linha 157): repassar `live_only` para:
   - `self._get_open_trades(live_only=live_only)` na linha 213
   - As três stats no refresh pós-Phase 1 (linhas 240-242):
     - `self.count_trades_today(today_str, live_only=live_only)`
     - `self.pnl_today(today_str, live_only=live_only)`
     - `self.minutes_since_last_loss(now=now_dt, live_only=live_only)`

3. Documentar em `CLAUDE.md` na seção "Critical Constraints" que paper-OPEN trades anteriores ao cutover ficarão eternamente OPEN no DB (não bloqueiam, não disparam exit).

## Testes

Novos em `tests/test_trade_engine.py`:

- `test_get_open_trades_live_only_hides_paper_open` — seed paper OPEN em CONS_BASE; `_get_open_trades(live_only=True)["CONS_BASE"]` é None.
- `test_evaluate_live_only_unblocks_after_paper_daily_loss` — replica o bug real: seed paper R$-494 CLOSED hoje; chama `evaluate(..., live_only=True)` com z sinal de entrada; assert `action == "BUY_WIN"`. Sem o fix, esse teste falha por DAILY_LOSS_LIMIT.
- `test_evaluate_default_live_only_false_preserves_legacy_blocking` — seed paper loss; `evaluate(...)` sem o kwarg → ainda bloqueia (back-compat para replay/paper).

## Fora de escopo

- `server.py` ainda não muda — defaults `False` preservam comportamento.
- Auditoria em /api/v2/regime: Slice 4.
- Timeline scope: Slice 5.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 _get_open_trades aceita live_only kwarg-only com default False; docstring documenta paper-OPEN órfãos
- [ ] #2 evaluate aceita live_only kwarg-only com default False; propaga para _get_open_trades e para count/pnl/cooldown na linha 240-242
- [ ] #3 Os 3 testes novos passam, incluindo test_evaluate_live_only_unblocks_after_paper_daily_loss que replica o bug real
- [ ] #4 CLAUDE.md atualizado em 'Critical Constraints' documentando comportamento dos paper-OPEN órfãos
- [ ] #5 Suite pytest tests/test_trade_engine.py + tests/test_trade_engine_live.py verde
- [ ] #6 Nenhuma chamada existente de evaluate ou _get_open_trades quebra (defaults preservam legado)
<!-- AC:END -->
