---
id: TASK-17.18
title: Future — Investigar microestrutura MT5 para fidelidade de replay
status: To Do
assignee: []
created_date: '2026-05-13 12:00'
labels:
  - mt5
  - replay
  - simulation
  - microstructure
dependencies:
  - TASK-17.8
parent_task_id: TASK-17
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Objetivo

Investigar quais dados de microestrutura disponíveis no MetaTrader 5 podem aproximar o replay/backtest da realidade operacional sem alterar a regra de negócio do motor.

Esta slice é futura e **não bloqueia** a Fase A atual. A Fase A primeiro entrega a simulação parametrizável com OHLC, slippage fixo e custos configuráveis. Depois disso, esta investigação avalia se parte desses valores pode ser substituída ou calibrada por dados reais do MT5.

## Fontes MT5 a investigar

- `symbol_info(symbol)`:
  - `trade_tick_size`
  - `trade_tick_value`
  - `volume_min`, `volume_step`, `volume_max`
  - `spread`, `spread_float`
  - `filling_mode`
  - `trade_stops_level`
  - `trade_freeze_level`
  - `trade_mode`
  - `expiration_mode`
- `symbol_info_tick(symbol)`:
  - `bid`
  - `ask`
  - `last`
  - `time`
  - spread real no momento do poll
- `copy_ticks_range()` / `copy_ticks_from()`:
  - reconstrução tick-level de uma janela curta
  - validação se OHLC M5 é proxy suficiente para SL/TP
  - estimativa de slippage/spread por horário e símbolo

## Perguntas que esta investigação deve responder

1. Quais campos existem e são confiáveis para `WIN`, `WDO` e `DI` no terminal/broker usado?
2. `symbol_info_tick()` fornece bid/ask suficientes para capturar spread real no live?
3. `copy_ticks_range()` consegue reconstruir, para uma data histórica, a sequência necessária para validar se SL ou TP teria batido primeiro?
4. `trade_tick_size` e `trade_tick_value` batem com os valores usados no motor para PnL?
5. `volume_min`/`volume_step` e `filling_mode` indicam restrições que o replay deveria respeitar ao montar ordens?
6. Dá para calibrar `entry_slippage_pts` / `exit_slippage_pts` por horário em vez de usar valor fixo?

## Entregável esperado

- Script exploratório, por exemplo `scripts/probe_mt5_microstructure.py`, que coleta um JSON por símbolo com:
  - `symbol_info`
  - `symbol_info_tick`
  - amostra curta de ticks, quando disponível
  - classificação de campos úteis para replay
- Documento curto em `docs/` ou relatório JSON em `audits/` com recomendação:
  - manter slippage fixo
  - calibrar slippage por símbolo/horário
  - capturar bid/ask no live
  - evoluir para tick-level replay em tarefa separada

## Fora de escopo

- Não alterar `TradeEngine` nesta slice.
- Não substituir `simulation_profile` ainda.
- Não mudar regra de entrada/saída.
- Não ativar tick-level replay sem uma task própria.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Script exploratório coleta `symbol_info` e `symbol_info_tick` para WIN/WDO/DI e grava JSON
- [ ] #2 Script tenta coletar ticks históricos de uma janela curta e classifica disponibilidade/limitações
- [ ] #3 Relatório identifica quais campos podem alimentar replay e quais são apenas informacionais
- [ ] #4 Recomendação explícita sobre manter slippage fixo vs calibrar com dados reais
- [ ] #5 Nenhuma mudança no motor operacional (`TradeEngine`) é feita nesta slice
<!-- AC:END -->
