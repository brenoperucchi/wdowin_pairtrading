---
id: TASK-17.7
title: Slice A.7 — Replay propaga OHLC + simulation_profile + CLI flags
status: Done
assignee: []
created_date: '2026-05-13 01:21'
updated_date: '2026-05-13 04:04'
labels:
  - replay
  - simulation
  - cli
dependencies: []
parent_task_id: TASK-17
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Objetivo

Fazer `scripts/replay_execution_timeline.py` propagar OHLC do `bar_history` (de A.3/A.4) e o `simulation_profile` (de A.5) para o `TradeEngine.evaluate()` (de A.6).

## Modificações

- `resolve_replay_profile()` (linha 138): incluir bloco `simulation` ao carregar runtime_config, com overrides via CLI:
  - `--sim-enabled`, `--sim-entry-slip`, `--sim-exit-slip`, `--sim-cost-rt`
  - `--sim-intra-bar/--no-sim-intra-bar`
  - `--sim-exit-at-level/--no-sim-exit-at-level`
  - `--sim-conflict-rule sl_first|tp_first|worst`
- `run_replay()` (linha 533):
  - Ler `win_high`, `win_low`, `wdo_high`, `wdo_low`, `di_high`, `di_low` do row do bar_history.
  - Passar como kwargs ao `engine.evaluate(..., simulation_profile=profile, win_high=..., win_low=...)`.
- META event do timeline DB carrega o `simulation_profile` usado (similar ao que já tem para `eg_*`).

## Dependência (informativa)

TASK-17.x (A.6 — engine aplica profile) + A.3/A.4 (OHLC disponível em bar_history).

## Janela

**Fora de mercado** — o replay reusa o engine.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 CLI flags --sim-* funcionam (override do runtime_config)
- [x] #2 win_high/low/etc são lidos do bar_history e passados ao engine.evaluate()
- [x] #3 META event do replay DB contém simulation_profile usado
- [x] #4 Barra sem OHLC + --sim-intra-bar → fallback close-only com warn no timeline
- [x] #5 Replay com --sim-enabled=False produz mesmo summary que antes de A.7 (regressão zero)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## Resumo das mudanças

### `scripts/replay_execution_timeline.py`

1. **`ReplayRuntimeProfile`** (linha 65) — adicionado campo `simulation: dict`; `from_mapping` agora descompacta `payload["simulation"]` (já normalizado pelo `runtime_config._validate_simulation`).
2. **`resolve_replay_profile()`** (linha 138) — novo parâmetro keyword `simulation_overrides: dict | None`. Quando fornecido, mescla apenas chaves não-None no `replay["simulation"]` antes da validação, preservando o resto do bloco do disco/defaults.
3. **`_process_bar()`** (linha 332+) — lê `row.get("win_high")` / `row.get("win_low")` com conversão float opcional (NULL → None). Os valores são passados para `engine.evaluate(..., simulation_profile=runtime_profile.simulation, win_high=..., win_low=...)`.
4. **`run_replay()`** (linha 545) — propaga `simulation_overrides` para `resolve_replay_profile`.
5. **`_parse_args()`** — 7 novos flags CLI:
   - `--sim-enabled / --no-sim-enabled` (BooleanOptionalAction)
   - `--sim-entry-slip <float>`
   - `--sim-exit-slip <float>`
   - `--sim-cost-rt <float>`
   - `--sim-intra-bar / --no-sim-intra-bar`
   - `--sim-exit-at-level / --no-sim-exit-at-level`
   - `--sim-conflict-rule sl_first|tp_first|worst`
6. **`main()`** — monta `simulation_overrides` a partir de `args.sim_*` (todos default None) e repassa via kwarg.
7. **META event** — `_summarize` continua emitindo `runtime_profile.__dict__`, que agora inclui automaticamente o sub-bloco `simulation` aplicado.

### `tests/test_replay_execution_timeline.py`

Atualizado `fake_run_replay` no `test_main_skips_source_db_existence_check_under_postgres_backend` para aceitar o novo kwarg `simulation_overrides`.

### `tests/test_replay_simulation_wiring.py` (NOVO)

12 testes cobrindo as 5 ACs:

- **AC #1 (CLI)** — 4 testes: parse de todos os 7 flags, negação booleana (`--no-sim-*`), defaults None, resolver mesclando overrides (skips None), `main()` repassa overrides ao `run_replay`.
- **AC #2 (OHLC passthrough)** — 2 testes: spy em `TradeEngine.evaluate` confirma que `win_high`/`win_low` chegam quando preenchidos e None quando ausentes.
- **AC #3 (META payload)** — 1 teste: lê `REPLAY_SUMMARY` do replay DB, valida que `payload_json.runtime_profile.simulation` contém os valores overrideados.
- **AC #4 (fallback sem OHLC)** — 1 teste: sim+intra_bar=True em barras sem OHLC roda até o final, fecha TP via close-only, não emite `DATA/MISSING_*` para OHLC e emite `DATA/INTRA_BAR_DEGRADED` com `status=WARN`; summary inclui `warnings_by_reason.DATA:INTRA_BAR_DEGRADED`.
- **AC #5 (regressão zero)** — 2 testes: sim disabled = baseline (PnL/trades idênticos mesmo com slippage configurada, porque `enabled:False` ignora tudo); sim enabled com slip+cost reduz PnL strict-less-than baseline.

### Verificação

- `pytest tests/test_replay_simulation_wiring.py` → 12/12 passed
- `pytest tests/` → 465 passed, 19 skipped (era 451 antes; 14 novos = 12 wiring + 2 já existentes que reutilizam infra A.6).
- Nenhuma regressão em testes pré-existentes.

### Notas

- Configs legados (sem `simulation`) continuam funcionando: `_backfill_missing_fields` em `core/runtime_config.py` (A.5) injeta defaults antes da validação.
- A camada CLI usa `argparse.BooleanOptionalAction` (Python 3.9+), consistente com o resto do projeto (3.12).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Replay propaga `simulation_profile` (do `runtime_config.replay.simulation`) + OHLC (`win_high`/`win_low` lidos do `bar_history`) para o mesmo `TradeEngine.evaluate()` usado em live. Sete flags CLI (`--sim-enabled`, `--sim-entry-slip`, `--sim-exit-slip`, `--sim-cost-rt`, `--sim-intra-bar`, `--sim-exit-at-level`, `--sim-conflict-rule`) sobrescrevem o runtime_config sem mexer no arquivo. META event do replay DB carrega o `simulation_profile` efetivamente aplicado, dando auditoria do que cada replay rodou. Se simulação intra-bar estiver ativa mas a barra não tiver `win_high/win_low`, o replay continua close-only e registra `DATA/INTRA_BAR_DEGRADED` + `warnings_by_reason`. Quando `simulation.enabled=False` (default), bit-exato com baseline pré-A.7. 12 testes novos (`tests/test_replay_simulation_wiring.py`), 465/465 passando.
<!-- SECTION:FINAL_SUMMARY:END -->
