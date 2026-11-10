---
description: Regras permanentes e arquitetura consolidada do Sistema Stat-Arb WIN x WDO x DI (2026) e Dashboard Multi-Abas
---

# Contexto Permanente — Sistema Stat-Arb WIN × WDO × DI (2026)

Consulte sempre [`STATARB_2026_KNOWLEDGE.md`](../../STATARB_2026_KNOWLEDGE.md) na raiz do projeto para detalhes completos.

## 1. Portas e Serviços
- **Backend FastAPI (`server.py`)**: `http://localhost:8080` (protegido por `_single_mt5_executor = ThreadPoolExecutor(max_workers=1)` e `core.mt5_client.mt5_lock` para evitar segfaults na DLL C++ do MetaTrader 5).
- **Frontends Ativos**: `http://localhost:5174` e `http://localhost:5176` (`regime-dashboard`).
- **REGRA DE OURO**: **JAMAIS** encerrar, reiniciar ou interagir com a porta **`5175`**.

## 2. Separação Estrita das Abas no `regime-dashboard`
- **Aba 1 (`COCKPIT`)**: Bússola Intraday GEX (`IntradayCompassPanel.jsx`) + Calendário do Live Trading das 6 Estratégias Campeãs (`LiveTradingCalendar.jsx`).
- **Aba 2 (`RAIO_X`)**: Fluxo de Corretoras WIN (`FlowDeltaChart.jsx` + `BrokerFlowPanel.jsx`).
- **Aba 3 (`STAT_ARB`)**: **Exclusiva** para Arbitragem Estatística WIN × WDO × DI:
  - `ZScoreChart.jsx` + `SignalHistogram.jsx` (sinais congelados após fechamento da barra M5, sem repintura)
  - `IndexChart.jsx` (Candles M5 WINFUT + NWE + GEX Walls + **Caixas de Posição estilo TradingView** com início, degrau de Break-Even e fim exato do trade)
  - `StatArbLiveTradePanel.jsx` (Monitoramento ao vivo dos 3 setups + tabela de operações do dia + histórico completo 2026 clicável)
  - `StatArbBacktest2026Panel.jsx` (4 curvas de capital auditadas 2026, dias operados, correlação e calendário de 212 pregões).

## 3. Regras das 3 Estratégias Stat-Arb (Mantidas por Decisão Operacional)
- **`1. CONSENSO (WDO+DI)`**: `(±1.8 WDO e ±1.2 DI)` ou `(±2.2 DI e ±1.2 WDO)`, `nwe_prox = 0.15`, `BE = +150 pts → +15 pts`. (`+R$ 4.277` em 2026, `Ret/DD 9,23x`).
- **`2. DI_NWE (ISOLADO)`**: `|Z_DI| >= 2.2`, `nwe_prox = 0.10`, `BE = +200 pts → +15 pts`. (`+R$ 3.252` em 2026, `Ret/DD 5,49x`).
- **`3. WDO_NWE (ISOLADO)`**: `|Z_WDO| >= 1.4`, `nwe_prox = 0.15`, `BE = +150 pts → +15 pts`. (`+R$ 2.606` em 2026, `Ret/DD 6,79x`).
- **Stop Loss (`calc_wall_tp_sl`)**: Sempre posicionado **`30 pts` atrás da Wall anterior** (mínimo `200 pts`, máximo `300 pts` — se exigir `> 300 pts`, não entra; nunca colocar o stop antes da Wall).
- **Alvo**: `10 pts` antes da próxima Wall (`R/R >= 1.4x`) ou reversão de Z-Score (`Z-Rev`) com `>= 200 pts` de lucro.
- **Resultado Consolidado 2026 (212 pregões, 488 trades, 2 contratos)**:
  - Soma Bruta: **`+R$ 10.135`** (`+25.338 pts`), Max DD **`R$ 764`**, **`Ret/DD = 13,27x`**.
  - Deduplicado (1x p/ horário): **`+R$ 6.322`** (`+15.805 pts`), Max DD **`R$ 752`**, **`Ret/DD = 8,41x`**.
