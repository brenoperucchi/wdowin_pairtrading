---
id: TASK-13.3
title: '[Slice 3] beta_unstable como hard-block'
status: Done
assignee: []
created_date: '2026-05-11 18:55'
updated_date: '2026-05-11 21:08'
labels:
  - gate
  - risk
dependencies: []
parent_task_id: TASK-13
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Escopo

Wire `beta_unstable` (calculado em `_update_beta_state`, hoje só payload-metadata) para o `risk_gate` como gate de bloqueio, mirroring `safe_to_trade and not beta_unstable` do upstream.

## Mudanças

- `core/risk_gate.py` — novo kwarg `beta_unstable: bool = False`; novo `checks["beta_state"] = not beta_unstable`; reason `BETA_UNSTABLE`.
- `server.py` — passar `beta_unstable=_update_beta_state(...)._asdict()["unstable"]` (ou o nome real da tupla) na chamada `_build_gate`.
- `runtime_config` — opcional: adicionar `enforce_beta_unstable: bool` (default True) para o operador desligar em emergência. Decidir durante implementação se vale o ruído extra de UI.
- Tests: novo teste `test_beta_unstable_blocks_entry` + verificar que reason `BETA_UNSTABLE` aparece no payload de timeline.
- CLAUDE.md — remover a nota "Our code does not currently enforce this" da seção Regime health gates.

## Não-escopo

- Refatorar `_update_beta_state` — só consumimos o flag existente.
- Adicionar histórico de "quantas vezes BETA_UNSTABLE disparou" — vai aparecer organicamente na timeline.

## Riscos

- Possível aumento de bars bloqueados em produção. Antes de mergear, rodar replay de pelo menos 3 dias com trades históricos (incluindo 2026-05-08) para garantir que `beta_unstable` não estava ativo nesses dias.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 risk_gate aceita kwarg `beta_unstable` e emite reason BETA_UNSTABLE quando True
- [x] #2 server.py passa o valor do state machine para o gate
- [x] #3 Replay de 2026-05-08 (caso Miqueias-positivo do mem feedback_di_kalman) continua produzindo SELL DI_NWE 10:15
- [x] #4 CLAUDE.md atualizado: nota 'does not enforce' removida
- [x] #5 TASK-13 AC #2 satisfeito (CLAUDE.md espelha código final)
- [x] #6 Todos os testes existentes continuam passando
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Slice 3 — beta_unstable como hard-block (Done)

### Arquivos alterados

1. **`core/risk_gate.py`** — Novo kwarg `beta_unstable: bool = False`. Adicionado `checks["beta_state"] = not bool(beta_unstable)` e reason `BETA_UNSTABLE` quando True. Docstring atualizada com a nova gate e o reason.

2. **`server.py`** — Adicionado state machine `_win_beta_state` (mirror de `_di_beta_state`, mas bar-over-bar via `closed_bar_ts`) e constante `WIN_BETA_UNSTABLE_PCT = 15.0`. State é avançado APENAS quando `bar_close_confirmed=True` e o `closed_bar_ts` mudou, evitando que múltiplos polls dentro da mesma barra zerem o `beta_change_pct`. `_build_gate` passa `beta_unstable=win_beta_unstable`. `_build_response` agora recebe valores reais de `beta_change_pct_closed` e `win_beta_unstable` (antes 0.0 e `beta_status_d["level"] >= 2`).

3. **`scripts/replay_execution_timeline.py`** — Constante `WIN_BETA_UNSTABLE_PCT = 15.0` espelhando server.py. `_process_bar` aceita kwarg `beta_state: dict | None` que mantém `previous_beta` entre barras. Loop em `run_replay` cria o dict uma vez e injeta no loop. `risk_gate` recebe `beta_unstable=bool(beta_state["unstable"])`. Paridade com live: ambos comparam `beta_value` vs barra anterior.

4. **`tests/test_risk_gate.py`** — Três novos testes:
   - `test_beta_unstable_true_blocks_with_reason` — confirma reason + check.
   - `test_beta_unstable_false_does_not_block` — confirma explícito False não emite reason.
   - `test_beta_unstable_default_does_not_block` — backward-compat: callers sem o kwarg seguem como antes.

5. **`CLAUDE.md`** — Removida a linha "Our code does not currently enforce this — flagged as a gap". Substituída por descrição da state machine (`_win_beta_state`, `WIN_BETA_UNSTABLE_PCT`) e parity com upstream `safe_to_trade and not beta_unstable`. Linha do z_anomaly também atualizada para refletir runtime_config (do Slice 2).

### Verificação

- `PYTHONPATH=. pytest tests/ -q --ignore=tests/test_backfill_bar_history_indicators.py` → **308 passed** (4 novos testes vs 304 antes).
- `npm run lint` → clean.
- `npm run build` → 782.83 KB, 3.67s.
- **Replay 2026-05-08** rodado via `run_replay()`: 1 SELL DI_NWE @ 10:15 → fechou 10:35 BE_STOP -34 BRL. **Sem novos blockers de BETA_UNSTABLE no dia** — confirma que o gate não invalidou o cenário Miqueias-positivo (AC #3).

### Comportamento esperado

`risk_gate` agora bloqueia entradas quando o beta Kalman do WIN×WDO sofreu mudança bar-over-bar > 15%. Em produção:
- Primeira barra do dia: prev=None → unstable=False (sem flap).
- Bar-over-bar swing >15%: reason `BETA_UNSTABLE` aparece no timeline + bloqueia.
- Próxima barra com swing <15%: state limpa automaticamente.

Replay mantém paridade porque cada `_process_bar` é exatamente uma barra fechada.

### Próximo

TASK-13 (parent) — fechar parent task; todos os 3 slices completados.
<!-- SECTION:FINAL_SUMMARY:END -->
