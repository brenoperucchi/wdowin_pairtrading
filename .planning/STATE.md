# Project State

## Project Reference

See: [`STATARB_2026_KNOWLEDGE.md`](../STATARB_2026_KNOWLEDGE.md) & [`.planning/PROJECT.md`](PROJECT.md) (updated 2026-11-09)

**Core value:** Painel analítico e operacional de Arbitragem Estatística (`WIN × WDO × DI`), Cockpit Intraday GEX (6 Estratégias Campeãs) e Raio-X de Fluxo Institucional de Corretoras em tempo real.
**Current focus:** Operação e monitoramento em tempo real das 3 abas do Dashboard (`5174` e `5176`) + Backend (`8080`).

## Current Position

Status: **Em Produção Local (`5174`, `5176`, `8080`)**
Last activity: **2026-11-09** — Consolidação da Aba 3 (`STAT_ARB`) com Caixas de Posição estilo TradingView em Candles M5, Painel de Acompanhamento Live Trade (`StatArbLiveTradePanel.jsx`), Backtest Auditado 2026 (`StatArbBacktest2026Panel.jsx`), correção do Stop atrás da Wall (`calc_wall_tp_sl`) e blindagem single-thread do MT5 (`_single_mt5_executor`).

## Key Decisions (Consolidated 2026-11-09)

- **Manutenção do Sistema Atual de Saída (`BE +150/200p → +15p` + Alvo Wall/Z-Rev):** Entregou `+R$ 10.135` (`+25.338 pts`), Max DD `R$ 764` e `Ret/DD = 13,27x` nos 212 pregões de 2026 (488 trades).
- **Stop Loss Sempre Atrás da Wall Anterior:** `calc_wall_tp_sl` posiciona o stop `30 pts` atrás da Wall anterior (mín. `200 pts`, máx. `300 pts`). Se a Wall exigir `> 300 pts`, o setup é abortado (nunca truncado para antes da Wall).
- **Sinais Sem Repintura:** Barras M5 fechadas têm seus sinais (`sig_wdo`, `sig_di`, `sig_cons`) congelados no SQLite (`bar_history`).
- **Isolamento de Abas:** Aba 1 exclusiva para Cockpit GEX + 6 Estratégias Campeãs (`LiveTradingCalendar.jsx`); Aba 3 exclusiva para Arbitragem `WIN × WDO × DI`.
- **Blindagem MT5:** Toda comunicação com a DLL do MetaTrader 5 roda em thread única de SO (`_single_mt5_executor` + `core.mt5_client.mt5_lock`).
