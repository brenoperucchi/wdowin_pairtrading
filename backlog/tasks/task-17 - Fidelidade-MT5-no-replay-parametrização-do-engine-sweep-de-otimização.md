---
id: TASK-17
title: Fidelidade MT5 no replay + parametrização do engine + sweep de otimização
status: To Do
assignee: []
created_date: '2026-05-13 01:18'
updated_date: '2026-05-13 01:41'
labels:
  - engine
  - simulation
  - optimization
  - replay
  - refactor
dependencies: []
references:
  - docs/plans/primeiro-vamos-criar-essas-playful-aho.md
  - TASK-16
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Objetivo

Tornar replay/backtest fiel ao que MT5 cobraria na live (slippage, intra-bar SL/TP, custos round-trip) e habilitar sweep paralelo de otimização — tudo respeitando o princípio inegociável de que **replay/backtest e live rodam o MESMO código de engine** (`core/trade_engine.py` + `core/signals.py` + `core/risk_gate.py`).

`SimulationProfile` e `engine_params` são **inputs** do `TradeEngine.evaluate()`, nunca paths paralelos. Live: profile=None → no-op (recebe condição real do mercado). Replay/sweep: profile dict → modela slippage/intra-bar/custos.

## Plano completo

Ver `docs/plans/primeiro-vamos-criar-essas-playful-aho.md`.

## Estrutura em 3 fases (17 subtasks)

- **Fase A** (A.1-A.8): Fidelidade MT5 — fetch_rates OHLC, schema migration, captura live, backfill, simulation profile no runtime_config (dentro de live/replay), aplicação no engine, propagação no replay, testes.
- **Fase A'** (A'.1-A'.4): Parametrização — TradeEngine consome params via input (não via global). Absorve TASK-16. Pré-requisito do sweep.
- **Fase B** (B.1-B.5): Sweep otimização paralelo (ThreadPool seguro após A'), grid v1 (sem WINDOW por enquanto), reporter, testes, reality check.
- **Future** (TASK-17.18): investigar microestrutura MT5 (`symbol_info`, `symbol_info_tick`, ticks históricos) para calibrar replay depois que a simulação OHLC estiver estável.

## Decisões de design já tomadas

1. **OHLC**: estender `bar_history` (canonical) + `fetch_rates()` novo (preserva `fetch_bars`).
2. **Migração**: ALTER TABLE explícito para SQLite + Postgres (não confiar em CREATE IF NOT EXISTS).
3. **simulation block**: DENTRO de cada perfil (live/replay), default `enabled=false` em ambos.
4. **TP+SL no mesmo candle**: regra conservadora `sl_first` (configurável).
5. **WINDOW**: removido do sweep v1 — z's já materializados em `bar_history`; variar window sem recomputar Kalman/OLS é placebo.
6. **Sweep**: ThreadPool seguro APÓS A' (sem global mutável); fallback opcional `--isolation subprocess`.

## Robustez futura (notes, não fazer agora)

- Walk-forward / OOS holdout
- Bayesian (optuna/skopt) quando espaço > 10k combos
- K-fold de regimes HMM
- Slippage probabilístico (requer captura bid/ask no live)
- WINDOW no sweep com recomputação de indicadores
- Multi-objective Pareto
- Tick-level fidelity
- Captura de condição real (bid/ask/spread) no live = "saber" (ver TASK-17.18)

## Constraints operacionais

- Slices que mexem em engine usado pelo `trade_eval_loop` (A.3, A.6, A.7, A'.2, A'.3, B.5) → executar fora de mercado (após 17:40 BRT, posições fechadas).
- Demais slices safe durante mercado.
- TASK-16 (migração de params operacionais para runtime.json) está absorvida pela Fase A'.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Replay e live continuam usando o mesmo TradeEngine.evaluate() — zero código duplicado de regra de negócio
- [ ] #2 simulation.enabled=False em replay produz output bit-exato ao baseline pré-mudanças (regressão zero)
- [ ] #3 Com simulation.enabled=True: slippage entrada/saída aplicado, exit no nível do SL/TP (não no win_price), intra-bar SL/TP via win_high/win_low, custo round-trip descontado, regra sl_first para conflito TP+SL no mesmo candle
- [ ] #4 bar_history schema migrado com OHLC em SQLite + Postgres; live captura OHLC para novas barras; backfill cobre dados históricos
- [ ] #5 TradeEngine consome buy_sl/tp/be_*, z_entry, etc via engine_params (input) — sem importar global de core/config.py
- [ ] #6 Mudança de buy_sl via POST /api/runtime-config não afeta posições já abertas (snapshot no _open_trade)
- [ ] #7 Sweep paralelo com ThreadPoolExecutor: 2+ trials com params diferentes rodando em paralelo não contaminam estado (test cross-trial leakage)
- [ ] #8 Relatório consolidado (trials.csv + top_k_by_pnl.md + report.md) gerado após sweep com manifest íntegro
- [ ] #9 Reality check: top-1 config do sweep aplicada via runtime-config em 1 dia paper live diverge < 5% do replay do mesmo dia
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## ⚠️ REVISITAR ANTES DE CRIAR SUBTASKS DA FASE B (2026-05-13)

Revisão dos docs `docs/GUIA_OTIMIZACAO.md` e `docs/GUIA_ESTRATEGIAS.md` revelou que o desenho original da Fase B (um único grid `B.2` misturando `z_entry` + SL/TP/BE + `eg_threshold`) **viola** a regra-mestra do guia interno: "NUNCA otimize tudo ao mesmo tempo" (GUIA_OTIMIZACAO §28-36).

### Princípios do guia que valem manter e ainda NÃO estão no plano:

1. **Stages isolados com travamento** — otimizar uma família de parâmetros por vez, travando vencedor antes de ir para a próxima.
2. **Ret/DD como métrica primária**, não PnL bruto (GUIA_OTIMIZACAO §139-148).
3. **Platô, não pico** — flag de overfitting quando vizinhos no grid são ≥30% piores (§379-387).
4. **WFA/OOS obrigatório** ao final, hoje em "Robustez Futura" — promover para slice principal.
5. **Checklist de sanidade pré-prod** (§593-605) — incorporar ao B.5 reality check.

### Reestruturação proposta da Fase B (aplicar quando criarmos os subtasks):

| Slice | Conteúdo | Varia | Trava |
|---|---|---|---|
| B.1 | Runner + reporter (infra reutilizável) | — | — |
| B.2a | Stage Z | `z_entry`, `z_attention` | SL/TP altos (neutro), gates atuais |
| B.2b | Stage Saídas | `buy_sl/tp/be_act`, `sell_*` | `z_*` vencedor de B.2a |
| B.2c | Stage Gates (opcional) | `eg_threshold`, `rho_breakdown_level` | tudo anterior |
| B.3 | WFA/OOS sobre combinação final | janelas walk-forward | params travados |
| B.4 | Tests (inclui cross-trial leakage) | — | — |
| B.5 | Reality check + checklist de sanidade | — | — |

### O que NÃO seguir do guia (já validado):

- **Etapas 2 (Kalman) e 4 (NWE)** do guia — z's já materializados em `bar_history`, recomputar Kalman/NWE por trial exige reconstruir pipeline desde barras raw (5-10× mais lento). **Travar Kalman/NWE de fábrica** no sweep v1; re-otimizar em ciclo offline separado se preciso.
- **Pipeline `research/ols_v2_*.py`** — não usa `TradeEngine.evaluate()`, viola [[feedback_replay_same_engine_as_live]]. Referência conceitual apenas.

### Tarefas separadas a criar depois:

- **Atualização dos guias** (`GUIA_ESTRATEGIAS.md` desatualizado: ENTRY_END=15:00 vs 17:25, "signal-only" vs LIVE_ORDERS scaffold, "pair trading" vs WIN-only direcional). Tarefa doc-only, posterior a A+A'.

**Lembrete operacional:** quando A+A' estiverem verdes e formos criar os subtasks B.x, **reler este note antes** — não cair na tentação do grid único.
<!-- SECTION:NOTES:END -->
